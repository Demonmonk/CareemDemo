"""
Risk Radar — core workflow.

Two interchangeable engines:

  • Claude engine — uses the Anthropic API (claude-opus-4-8) with structured
    outputs and prompt caching to classify updates and write status digests.
  • Rule-based engine — a transparent keyword/heuristic fallback so the whole
    app runs live with no API key (useful for graders).

The public surface is engine-agnostic:
    classify_updates(df, engine) -> df with signal columns
    build_digests(df_classified, engine) -> {project: StatusDigest}
    portfolio_rollup(df_classified) -> df of per-project health
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

import prompts

MODEL = "claude-opus-4-8"

CATEGORIES = ["blocker", "risk", "dependency", "on_track"]
SEVERITIES = ["critical", "high", "medium", "low"]
SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


# --------------------------------------------------------------------------- #
# Data shapes
# --------------------------------------------------------------------------- #

@dataclass
class StatusDigest:
    project: str
    program: str
    milestone: str
    health: str  # RED / AMBER / GREEN
    headline: str
    top_risks: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Rule-based engine (no API key required)
# --------------------------------------------------------------------------- #

_BLOCKER_PAT = re.compile(
    r"\b(blocked|blocker|cannot proceed|can't proceed|halt|stuck|untestable|"
    r"not granted|down for|stopped|serialized behind)\b", re.I)
_DEP_PAT = re.compile(
    r"\b(depends on|dependency|waiting on|waiting for|needs .* from|"
    r"before we can|upstream|hand[- ]?off|slipped to)\b", re.I)
_RISK_PAT = re.compile(
    r"\b(risk|concern|slip|behind|scope (grew|creep)|latency|flaky|"
    r"bus[- ]?factor|optimistic|overrun|out on leave|findings)\b", re.I)
_CRIT_PAT = re.compile(r"\b(critical|corrupt|halt|completely|entirely|down for \d+ days)\b", re.I)
_HIGH_PAT = re.compile(r"\b(escalat|at risk|cannot|can't|blocked|hard blocker|critical path)\b", re.I)

_WAIT_ON_PAT = re.compile(
    r"(?:waiting on|waiting for|depends on|from|by)\s+([A-Z][\w& ]+?)"
    r"(?:\s+for|\s+to|\s+before|,|\.|$)")


def _detect_milestone(text: str) -> str:
    m = re.search(r"\(([A-Z][a-z]{2} \d{1,2})\)", text)
    return m.group(1) if m else ""


def _detect_depends_on(text: str) -> str:
    m = _WAIT_ON_PAT.search(text)
    return m.group(1).strip() if m else ""


def rule_classify_one(text: str) -> dict:
    is_blocker = bool(_BLOCKER_PAT.search(text))
    is_dep = bool(_DEP_PAT.search(text))
    is_risk = bool(_RISK_PAT.search(text))

    if is_blocker:
        category = "blocker"
    elif is_dep and not is_risk:
        category = "dependency"
    elif is_risk:
        category = "risk"
    elif is_dep:
        category = "dependency"
    else:
        category = "on_track"

    if category == "on_track":
        severity = "low"
    elif _CRIT_PAT.search(text):
        severity = "critical"
    elif _HIGH_PAT.search(text) or category == "blocker":
        severity = "high"
    else:
        severity = "medium"

    rationale = {
        "blocker": "Work appears stopped pending external action.",
        "risk": "Progress continues but a threat to timeline/quality is noted.",
        "dependency": "Progress hinges on another team or vendor deliverable.",
        "on_track": "Healthy progress with no concern raised.",
    }[category]
    action = {
        "blocker": "Escalate to the PMO and identify the owner to unblock.",
        "risk": "Add to the risk log and agree a mitigation this week.",
        "dependency": "Confirm the upstream ETA and align the critical path.",
        "on_track": "No action — keep monitoring.",
    }[category]

    return {
        "category": category,
        "severity": severity,
        "affected_milestone": _detect_milestone(text),
        "depends_on": _detect_depends_on(text) if category in ("blocker", "dependency") else "",
        "rationale": rationale,
        "recommended_action": action,
    }


def _rule_classify_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    recs = [rule_classify_one(t) for t in out["update_text"]]
    for key in ("category", "severity", "affected_milestone", "depends_on",
                "rationale", "recommended_action"):
        out[key] = [r[key] for r in recs]
    return out


# --------------------------------------------------------------------------- #
# Claude engine (structured outputs + prompt caching)
# --------------------------------------------------------------------------- #

def _claude_classify_df(df: pd.DataFrame, client, progress=None) -> pd.DataFrame:
    from pydantic import BaseModel

    class UpdateClassification(BaseModel):
        update_id: str
        category: Literal["blocker", "risk", "dependency", "on_track"]
        severity: Literal["critical", "high", "medium", "low"]
        affected_milestone: str
        depends_on: str
        rationale: str
        recommended_action: str

    class ClassificationBatch(BaseModel):
        items: list[UpdateClassification]

    out = df.copy()
    by_id: dict[str, dict] = {}

    chunk_size = 25
    rows = out.to_dict("records")
    chunks = [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]

    for ci, chunk in enumerate(chunks):
        payload = [{"update_id": r["update_id"],
                    "project": r["project"],
                    "update_text": r["update_text"]} for r in chunk]
        user = prompts.CLASSIFIER_USER_TEMPLATE.format(
            n=len(payload), updates_json=json.dumps(payload, indent=2))

        resp = client.messages.parse(
            model=MODEL,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": prompts.CLASSIFIER_SYSTEM,
                "cache_control": {"type": "ephemeral"},  # static prefix → cached
            }],
            messages=[{"role": "user", "content": user}],
            output_format=ClassificationBatch,
        )
        parsed = resp.parsed_output
        if parsed:
            for item in parsed.items:
                by_id[item.update_id] = item.model_dump()
        if progress:
            progress((ci + 1) / len(chunks))

    def pick(uid, key, default=""):
        return by_id.get(uid, {}).get(key, default)

    for key in ("category", "severity", "affected_milestone", "depends_on",
                "rationale", "recommended_action"):
        out[key] = [pick(uid, key) for uid in out["update_id"]]
    # Any update the model skipped → fall back to rules so nothing is lost.
    missing = out["category"] == ""
    if missing.any():
        for idx in out[missing].index:
            r = rule_classify_one(out.at[idx, "update_text"])
            for key, val in r.items():
                out.at[idx, key] = val
    return out


# --------------------------------------------------------------------------- #
# Public classification entry point
# --------------------------------------------------------------------------- #

def classify_updates(df: pd.DataFrame, engine: str, client=None, progress=None) -> pd.DataFrame:
    if engine == "claude":
        if client is None:
            raise ValueError("Claude engine requires an Anthropic client.")
        return _claude_classify_df(df, client, progress=progress)
    return _rule_classify_df(df)


# --------------------------------------------------------------------------- #
# Health rollup
# --------------------------------------------------------------------------- #

def _health_from_signals(sub: pd.DataFrame) -> str:
    blockers = sub[sub["category"] == "blocker"]
    crit_blockers = blockers[blockers["severity"] == "critical"]
    high_blockers = blockers[blockers["severity"].isin(["critical", "high"])]
    risks = sub[sub["category"] == "risk"]
    high_risks = risks[risks["severity"].isin(["critical", "high"])]
    deps = sub[sub["category"] == "dependency"]

    # RED — a milestone is genuinely in jeopardy: a critical blocker, several
    # serious blockers, multiple high risks, or a blocker stacked on a high risk.
    if (len(crit_blockers) >= 1
            or len(high_blockers) >= 2
            or len(high_risks) >= 2
            or (len(blockers) >= 1 and len(high_risks) >= 1)):
        return "RED"
    # AMBER — real watch-items, but recoverable with normal effort.
    if (len(blockers) >= 1
            or len(high_risks) >= 1
            or len(risks) >= 2
            or len(deps) >= 3):
        return "AMBER"
    return "GREEN"


def portfolio_rollup(df: pd.DataFrame, recent_weeks: int = 3) -> pd.DataFrame:
    """Per-project health using the most recent `recent_weeks` of signals."""
    max_week = df["week"].max()
    recent = df[df["week"] > max_week - recent_weeks]
    records = []
    for (program, project), sub in recent.groupby(["program", "project"]):
        full = df[(df["program"] == program) & (df["project"] == project)]
        records.append({
            "program": program,
            "project": project,
            "milestone": full["milestone"].iloc[0],
            "health": _health_from_signals(sub),
            "blockers": int((sub["category"] == "blocker").sum()),
            "risks": int((sub["category"] == "risk").sum()),
            "dependencies": int((sub["category"] == "dependency").sum()),
            "on_track": int((sub["category"] == "on_track").sum()),
            "updates": int(len(sub)),
        })
    order = {"RED": 0, "AMBER": 1, "GREEN": 2}
    out = pd.DataFrame(records).sort_values(
        by=["health", "blockers", "risks"],
        key=lambda c: c.map(order) if c.name == "health" else c,
        ascending=[True, False, False])
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Digests
# --------------------------------------------------------------------------- #

def _rule_digest(project: str, program: str, milestone: str, sub: pd.DataFrame) -> StatusDigest:
    health = _health_from_signals(sub)
    blockers = sub[sub["category"] == "blocker"].sort_values(
        "severity", key=lambda c: c.map(SEVERITY_WEIGHT), ascending=False)
    risks = sub[sub["category"] == "risk"].sort_values(
        "severity", key=lambda c: c.map(SEVERITY_WEIGHT), ascending=False)
    deps = sub[sub["category"] == "dependency"]

    def line(row):
        return f"[{row['severity'].upper()}] {row['update_text']}"

    headline = {
        "RED": f"{project} is at risk — {len(blockers)} blocker(s) and {len(risks)} open risk(s) against {milestone}.",
        "AMBER": f"{project} is progressing with watch-items — {len(risks)} risk(s), {len(deps)} dependency(ies).",
        "GREEN": f"{project} is healthy and tracking to {milestone}.",
    }[health]

    next_steps = []
    for _, r in blockers.head(3).iterrows():
        next_steps.append(r["recommended_action"])
    for _, r in risks.head(2).iterrows():
        next_steps.append(r["recommended_action"])
    if not next_steps:
        next_steps = ["No action required — continue monitoring."]

    return StatusDigest(
        project=project, program=program, milestone=milestone, health=health,
        headline=headline,
        top_risks=[line(r) for _, r in risks.head(4).iterrows()],
        blockers=[line(r) for _, r in blockers.head(4).iterrows()],
        dependencies=[line(r) for _, r in deps.head(4).iterrows()],
        next_steps=list(dict.fromkeys(next_steps))[:5],
    )


def _claude_digest(project, program, milestone, sub, client) -> StatusDigest:
    from pydantic import BaseModel

    class Digest(BaseModel):
        health: Literal["RED", "AMBER", "GREEN"]
        headline: str
        top_risks: list[str]
        blockers: list[str]
        dependencies: list[str]
        next_steps: list[str]

    lines = []
    for _, r in sub.sort_values("date").iterrows():
        lines.append(
            f"- [{r['category']}/{r['severity']}] ({r['date']}, {r['author']}): {r['update_text']}")
    signals_block = "\n".join(lines)
    window = f"weeks {int(sub['week'].min())}–{int(sub['week'].max())}"

    user = prompts.DIGEST_USER_TEMPLATE.format(
        project=project, program=program, milestone=milestone,
        window=window, signals_block=signals_block)

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=2000,
        system=[{
            "type": "text",
            "text": prompts.DIGEST_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user}],
        output_format=Digest,
    )
    d = resp.parsed_output
    if not d:
        return _rule_digest(project, program, milestone, sub)
    return StatusDigest(
        project=project, program=program, milestone=milestone,
        health=d.health, headline=d.headline, top_risks=d.top_risks,
        blockers=d.blockers, dependencies=d.dependencies, next_steps=d.next_steps)


def build_digest(df_classified: pd.DataFrame, project: str, engine: str,
                 client=None, recent_weeks: int = 3) -> StatusDigest:
    full = df_classified[df_classified["project"] == project]
    program = full["program"].iloc[0]
    milestone = full["milestone"].iloc[0]
    max_week = df_classified["week"].max()
    sub = full[full["week"] > max_week - recent_weeks]
    if engine == "claude" and client is not None:
        return _claude_digest(project, program, milestone, sub, client)
    return _rule_digest(project, program, milestone, sub)
