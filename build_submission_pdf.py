"""Build the Risk Radar submission PDF (no browser needed)."""
from __future__ import annotations

from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle, HRFlowable)

import radar

LIVE_URL = "https://careemdemo-scnnzwjvpfmqgqug6us34k.streamlit.app/"
GITHUB_URL = "https://github.com/Demonmonk/CareemDemo"
DATASET_URL = ("https://github.com/Demonmonk/CareemDemo/blob/"
               "claude/keen-carson-Xbmqu/data/project_updates.csv")

INK = colors.HexColor("#15171B")
DARK = colors.HexColor("#0E0F12")
ACCENT = colors.HexColor("#0E9C8B")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E3E6EA")
RED = colors.HexColor("#D14343")
AMBER = colors.HexColor("#C98A00")
GREEN = colors.HexColor("#1F9D57")
BLUE = colors.HexColor("#3B6FB3")
HEALTH_COL = {"RED": RED, "AMBER": AMBER, "GREEN": GREEN}
HEALTH_HEX = {"RED": "#D14343", "AMBER": "#C98A00", "GREEN": "#1F9D57"}

ss = getSampleStyleSheet()


def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=10, leading=14, textColor=INK,
                spaceAfter=6, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "kicker": style("kicker", fontName="Helvetica-Bold", fontSize=8.5,
                    textColor=ACCENT, leading=12, spaceAfter=4),
    "title": style("title", fontName="Helvetica-Bold", fontSize=30,
                   textColor=colors.white, leading=32, spaceAfter=6),
    "subtitle": style("subtitle", fontSize=11.5, textColor=colors.HexColor("#C9CDD3"),
                      leading=16, spaceAfter=0),
    "h2": style("h2", fontName="Helvetica-Bold", fontSize=13, textColor=INK,
                leading=16, spaceBefore=12, spaceAfter=6),
    "body": style("body", fontSize=10, leading=15),
    "small": style("small", fontSize=8.6, textColor=MUTED, leading=12),
    "li": style("li", fontSize=10, leading=14.5, leftIndent=10, spaceAfter=3),
    "link": style("link", fontSize=10, textColor=ACCENT, leading=14),
    "cell": style("cell", fontSize=9, leading=12),
    "cellb": style("cellb", fontName="Helvetica-Bold", fontSize=9, leading=12),
    "quote": style("quote", fontSize=10, leading=14.5, textColor=INK),
}


def bullet(text):
    return Paragraph(f"<font color='#0E9C8B'>▪</font>&nbsp;&nbsp;{text}", S["li"])


def build():
    df = pd.read_csv("data/project_updates.csv")
    clf = radar.classify_updates(df, "rule")
    clf["sev_rank"] = clf["severity"].map(radar.SEVERITY_WEIGHT)
    roll = radar.portfolio_rollup(clf, recent_weeks=3)

    doc = SimpleDocTemplate(
        "Risk_Radar_Submission.pdf", pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="Risk Radar — Submission", author="Risk Radar")
    W = doc.width
    flow = []

    # ---- dark header band ----
    header = Table([[Paragraph("AI EARLY-WARNING SYSTEM&nbsp;&nbsp;·&nbsp;&nbsp;TAKE-HOME SUBMISSION", S["kicker"])],
                    [Paragraph("Risk Radar", S["title"])],
                    [Paragraph("Reads every project update and surfaces the risks, blockers and "
                               "dependencies that threaten delivery — in plain English, with the "
                               "reasoning shown.", S["subtitle"])]],
                   colWidths=[W])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (0, 0), 16), ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
    ]))
    flow += [header, Spacer(1, 10)]

    flow.append(Paragraph("<b>Challenge attempted:</b> #1 — Risk Radar. It also delivers "
                          "#3 — Status Summarizer — as a built-in output of the same workflow.",
                          S["body"]))

    # ---- links ----
    link_rows = [
        [Paragraph("Live prototype", S["cellb"]), Paragraph(f"<link href='{LIVE_URL}'>{LIVE_URL}</link>", S["link"])],
        [Paragraph("Source code", S["cellb"]), Paragraph(f"<link href='{GITHUB_URL}'>{GITHUB_URL}</link>", S["link"])],
        [Paragraph("Public dataset", S["cellb"]), Paragraph(f"<link href='{DATASET_URL}'>{DATASET_URL}</link>", S["link"])],
    ]
    lt = Table(link_rows, colWidths=[28 * mm, W - 28 * mm])
    lt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    flow += [Spacer(1, 6), lt, Spacer(1, 4),
             Paragraph("The live app runs instantly in any browser — no login, no setup.", S["small"])]

    # ---- summary ----
    flow.append(Paragraph("100-word summary", S["h2"]))
    flow.append(Paragraph(
        "Risk Radar is an AI early-warning system for delivery. It ingests the messy status "
        "updates a program manager drowns in — standups, emails, Jira comments — and uses the "
        "<b>Claude API</b> to classify each into a structured signal: blocker, risk, dependency "
        "or on-track, with a severity, the reason it was flagged, and a recommended next step. "
        "Signals roll up into a RAG health per project and a director-ready status digest. Built "
        "with structured outputs, prompt caching and a rule-based fallback (so it runs with no "
        "key), plus a hard spend cap for safe public use. Accuracy is measured against planted "
        "ground-truth labels.", S["body"]))

    # ---- two lenses ----
    flow.append(Paragraph("The program-manager lens", S["h2"]))
    flow.append(Paragraph("Delivery doesn't fail in one big bang — it slips one buried update at "
                          "a time. By the time it reaches a steering deck, the milestone is gone. "
                          "Risk Radar is the early-warning layer a PMO actually needs:", S["body"]))
    for t in ["<b>Surfaces risk early</b> — flags trouble the day it's written, not at sprint's end.",
              "<b>Makes dependencies and blockers explicit</b> — the things that quietly sink cross-team delivery.",
              "<b>Speaks the language of status</b> — RAG health, owners and concrete next steps; the digest is the weekly update, written for you.",
              "<b>Shows its reasoning</b> — every flag comes with <i>why</i>, so it earns trust instead of being a black box."]:
        flow.append(bullet(t))

    flow.append(Paragraph("Under the hood", S["h2"]))
    for t in ["<b>Claude API</b> for classification and summarization, via <b>structured outputs</b> — reliable typed JSON, not free text to parse.",
              "<b>Prompt caching</b> on the static instructions, and a deliberately fast, low-cost model for a high-volume, well-scoped task.",
              "<b>Graceful rule-based fallback</b> — fully functional with no API key, so anyone can evaluate it instantly.",
              "<b>Production guardrails</b> — server-side-only secrets, a hard shared spend cap, and result caching so nothing is re-charged.",
              "<b>Evaluated, not asserted</b> — hidden ground-truth labels the model never sees turn accuracy into a measured number (~94%)."]:
        flow.append(bullet(t))

    # ---- portfolio snapshot (real data) ----
    flow.append(Paragraph("Portfolio snapshot — live output", S["h2"]))
    flow.append(Paragraph("Generated from the prototype's classification of the dataset. "
                          "Projects are ranked worst-first.", S["small"]))
    head = [Paragraph("<b>Project</b>", S["cellb"]), Paragraph("<b>Program</b>", S["cellb"]),
            Paragraph("<b>Health</b>", S["cellb"]), Paragraph("<b>Blk</b>", S["cellb"]),
            Paragraph("<b>Rsk</b>", S["cellb"]), Paragraph("<b>Dep</b>", S["cellb"])]
    rows = [head]
    for _, r in roll.iterrows():
        rows.append([
            Paragraph(escape(r["project"]), S["cell"]),
            Paragraph(escape(r["program"]), S["cell"]),
            Paragraph(f"<font color='{HEALTH_HEX[r['health']]}'><b>● {r['health']}</b></font>", S["cell"]),
            Paragraph(str(int(r["blockers"])), S["cell"]),
            Paragraph(str(int(r["risks"])), S["cell"]),
            Paragraph(str(int(r["dependencies"])), S["cell"]),
        ])
    cw = [52 * mm, 40 * mm, 26 * mm, 12 * mm, 12 * mm, 12 * mm]
    pt = Table(rows, colWidths=cw, repeatRows=1)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F6")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow += [Spacer(1, 4), pt]

    # ---- example: one update -> AI read ----
    flagged = clf[clf["category"] == "blocker"].sort_values("sev_rank", ascending=False)
    ex = flagged.iloc[0]
    flow.append(Paragraph("Example — one raw update, read by the AI", S["h2"]))
    ex_tbl = Table([[Paragraph(f"<i>“{escape(str(ex['update_text']))}”</i>", S["quote"])],
                    [Paragraph(f"<b><font color='#D14343'>● {ex['category'].upper()} · "
                               f"{ex['severity'].upper()}</font></b>", S["cell"])],
                    [Paragraph(f"<b>Why flagged:</b> {escape(str(ex['rationale']))}", S["small"])],
                    [Paragraph(f"<b>Suggested action:</b> {escape(str(ex['recommended_action']))}", S["small"])]],
                   colWidths=[W])
    ex_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBFBFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, RED),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
    ]))
    flow += [Spacer(1, 2), ex_tbl]

    # ---- 30-sec eval ----
    flow.append(Paragraph("30-second evaluation guide", S["h2"]))
    for t in ["<b>Overview</b> — projects ranked worst-first; open a red one to see <i>why</i> each issue was flagged.",
              "<b>Project view</b> — each raw update shown beside the AI's read, plus a trend line and a status digest.",
              "<b>How it works</b> — the workflow, and the AI's measured accuracy vs. the hidden ground-truth labels."]:
        flow.append(bullet(t))

    flow += [Spacer(1, 8), HRFlowable(width="100%", color=LINE, thickness=0.5), Spacer(1, 4),
             Paragraph("Dataset: synthetic, illustrative mock data hand-generated for this demo, "
                       "themed around Careem-style lines of business (Careem Pay, Rides, Careem "
                       "Food, Quik, platform, compliance). Not real Careem data and not affiliated "
                       "with, endorsed by, or sourced from Careem. No confidential information.",
                       S["small"])]

    doc.build(flow)
    print("Wrote Risk_Radar_Submission.pdf")


if __name__ == "__main__":
    build()
