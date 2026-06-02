"""
Risk Radar — Streamlit app.

Reads a stream of messy project updates, uses AI to flag risks, blockers and
dependencies, and turns the noise into a clear, human-readable status — per
project and across the portfolio.

Engines:
  • Claude (Haiku 4.5 by default; Sonnet/Opus selectable) when a key is present.
  • A transparent rule-based fallback so the app runs live with no key.

Run:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading

import pandas as pd
import streamlit as st

import radar

st.set_page_config(page_title="Risk Radar", page_icon="📡", layout="wide")

# --------------------------------------------------------------------------- #
# Look-up tables
# --------------------------------------------------------------------------- #

CAT_BADGE = {
    "blocker":    ("⛔ Blocker",    "#b3261e"),
    "risk":       ("⚠️ Risk",       "#e08600"),
    "dependency": ("🔗 Dependency", "#3b6fb3"),
    "on_track":   ("✅ On track",   "#1e7d32"),
}
HEALTH_STYLE = {
    "RED":   ("🔴", "#b3261e", "At risk"),
    "AMBER": ("🟠", "#e08600", "Needs attention"),
    "GREEN": ("🟢", "#1e7d32", "Healthy"),
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Plain-language descriptions so a viewer knows what each project actually is.
PROJECT_INFO = {
    "Wallet Top-up & Cards": "Careem Pay wallet — top-ups, card issuance, KYC and refunds.",
    "Send & Request Money": "Peer-to-peer money transfers inside Careem Pay.",
    "Captain App 4.0": "Redesigned Captain (driver) app — navigation, earnings, trip flow.",
    "Surge Pricing Engine v2": "Dynamic ride pricing — demand prediction and surge zones.",
    "Restaurant Onboarding Portal": "Self-serve sign-up for restaurants joining Careem Food.",
    "Live Order Tracking": "Real-time courier tracking and ETAs for Careem Food orders.",
    "15-min Grocery Fulfilment": "Quik dark-store picking, inventory and routing for 15-min grocery.",
    "Super-App Kubernetes Migration": "Re-platforming Careem services onto Kubernetes.",
    "API Gateway Consolidation": "One gateway for auth, rate limiting and routing across services.",
    "PCI-DSS Compliance (Careem Pay)": "Payment-security audit — controls, evidence and runbooks.",
    "Captain Earnings & Payouts": "Captain earnings ledger, payouts and instant cashout.",
    "Careem Plus Revamp": "Careem Plus subscription — benefits, billing and experiments.",
}


def project_desc(name: str) -> str:
    return PROJECT_INFO.get(name, "")


# --------------------------------------------------------------------------- #
# Data & engine plumbing
# --------------------------------------------------------------------------- #

DATA_PATH = os.path.join("data", "project_updates.csv")


@st.cache_data(show_spinner=False)
def load_default_data() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH)


@st.cache_data(show_spinner=False)
def classify_rule_based(df: pd.DataFrame) -> pd.DataFrame:
    return radar.classify_updates(df, "rule")


def df_fingerprint(df: pd.DataFrame) -> str:
    return hashlib.md5(
        pd.util.hash_pandas_object(df[["update_id", "update_text"]], index=False).values
    ).hexdigest()


def get_client(api_key: str):
    try:
        import anthropic
    except ImportError:
        return None, "The `anthropic` package is not installed."
    try:
        return anthropic.Anthropic(api_key=api_key), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


# --------------------------------------------------------------------------- #
# Budget guard — a hard, shared spend cap so a public bot can't drain credit.
# Spend is tracked from real token usage and shared across ALL visitors of this
# app instance (not per-session), so opening many tabs can't bypass it.
# --------------------------------------------------------------------------- #

def _secret(name: str, default: str = "") -> str:
    v = os.environ.get(name, "")
    if not v:
        try:
            v = st.secrets.get(name, "")
        except Exception:  # noqa: BLE001
            v = ""
    return v or default


BUDGET_CAP = float(_secret("AI_BUDGET_USD", "0.50") or "0.50")
PER_SESSION_RUNS = int(_secret("AI_MAX_RUNS_PER_SESSION", "5") or "5")
_LEDGER_PATH = os.path.join(tempfile.gettempdir(), "risk_radar_usage.json")
PRICES = {  # ($/1M input, $/1M output)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}


@st.cache_resource
def _ledger():
    led = {"spend": 0.0, "lock": threading.Lock()}
    try:
        if os.path.exists(_LEDGER_PATH):
            with open(_LEDGER_PATH) as f:
                led["spend"] = float(json.load(f).get("spend", 0.0))
    except Exception:  # noqa: BLE001
        pass
    return led


def cost_of(usage, model: str) -> float:
    pin, pout = PRICES.get(model, (1.0, 5.0))
    g = lambda a: getattr(usage, a, 0) or 0  # noqa: E731
    return (g("input_tokens") * pin
            + g("output_tokens") * pout
            + g("cache_creation_input_tokens") * pin * 1.25
            + g("cache_read_input_tokens") * pin * 0.1) / 1_000_000


def add_usage(usage, model: str) -> None:
    led = _ledger()
    with led["lock"]:
        led["spend"] += cost_of(usage, model)
        try:
            with open(_LEDGER_PATH, "w") as f:
                json.dump({"spend": led["spend"]}, f)
        except Exception:  # noqa: BLE001
            pass


def budget_used() -> float:
    return _ledger()["spend"]


def budget_ok() -> bool:
    return budget_used() < BUDGET_CAP


def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color};color:#fff;padding:2px 9px;"
            f"border-radius:999px;font-size:0.78em;font-weight:600;white-space:nowrap'>"
            f"{text}</span>")


def health_pill(health: str) -> str:
    emoji, color, label = HEALTH_STYLE[health]
    return (f"<span style='background:{color}22;color:{color};padding:3px 12px;"
            f"border-radius:999px;font-weight:700'>{emoji} {health} · {label}</span>")


# --------------------------------------------------------------------------- #
# Sidebar — controls
# --------------------------------------------------------------------------- #

st.sidebar.title("📡 Risk Radar")
st.sidebar.caption("Turns messy project updates into a clear status.")

st.sidebar.subheader("1 · Data")
uploaded = st.sidebar.file_uploader(
    "Use your own updates (CSV)", type="csv",
    help="Needs at least: project, update_text. Otherwise the demo dataset is used.")
if uploaded is not None:
    raw = pd.read_csv(uploaded)
    st.sidebar.success(f"Loaded {len(raw)} rows from your file.")
else:
    raw = load_default_data()
    st.sidebar.caption(f"Demo dataset loaded · {len(raw)} updates.")

# Backfill expected columns so uploads with fewer columns still work.
for col, default in [("program", "—"), ("milestone", "—"), ("author", "—"),
                     ("role", "—"), ("team", "—")]:
    if col not in raw.columns:
        raw[col] = default
if "update_id" not in raw.columns:
    raw["update_id"] = [f"U{i:04d}" for i in range(1, len(raw) + 1)]
if "week" not in raw.columns:
    if "date" in raw.columns:
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        wk = raw["date"].dt.isocalendar().week.astype("Int64")
        raw["week"] = (wk - wk.min() + 1).astype(int)
        raw["date"] = raw["date"].dt.date.astype(str)
    else:
        raw["week"] = 1
has_truth = "signal_truth" in raw.columns

st.sidebar.subheader("2 · AI analysis")
# The API key is read ONLY from the server-side environment / Streamlit secrets.
# It is never shown in the UI and there is no input box — nothing to reveal.
default_key = _secret("ANTHROPIC_API_KEY", "")

# Fixed, low-cost model under the hood — not user-selectable.
MODEL_ID = "claude-haiku-4-5"
api_key, model_id = default_key, MODEL_ID
have_key = bool(default_key)

run_ai = False
if have_key:
    used = budget_used()
    exhausted = used >= BUDGET_CAP
    runs = st.session_state.get("ai_runs", 0)
    session_capped = runs >= PER_SESSION_RUNS
    run_ai = st.sidebar.button(
        "⚡ Run AI analysis",
        disabled=exhausted or session_capped,
        help="Reads every update with AI. Free engine shows until you click; "
             "results are cached so it won't re-run or re-charge.")
    st.sidebar.progress(min(used / BUDGET_CAP, 1.0) if BUDGET_CAP else 0,
                        text=f"AI budget: ${used:.2f} / ${BUDGET_CAP:.2f}")
    if exhausted:
        st.sidebar.error("AI paused — shared budget cap reached. Everyone gets the "
                         "free engine now.")
    elif session_capped:
        st.sidebar.warning(f"AI run limit reached for this session "
                           f"({PER_SESSION_RUNS}). The free engine still works.")
else:
    st.sidebar.caption("Showing the free built-in engine. Deeper AI analysis can be "
                       "enabled by the app owner via a key in the app's secrets.")

st.sidebar.subheader("3 · Current-state window")
recent_weeks = st.sidebar.slider("Health uses the last N weeks", 1, 6, 3,
                                 help="Older updates age out so health reflects the present.")

engine = "claude" if have_key else "rule"


# --------------------------------------------------------------------------- #
# Classification (never spends tokens unless the user clicks Run Claude)
# --------------------------------------------------------------------------- #

def run_classification(df, engine, api_key, model_id, run_ai):
    rule = classify_rule_based(df)
    if engine != "claude":
        return rule, "rule"
    fp = df_fingerprint(df) + "|" + model_id
    if st.session_state.get("clf_fp") == fp:
        return st.session_state["clf_df"], "claude"
    if not run_ai:
        return rule, "rule-pending"
    if not budget_ok():
        st.warning("AI budget cap reached — showing the free rule-based engine.")
        return rule, "rule"
    client, err = get_client(api_key)
    if client is None:
        st.error(f"Could not start AI analysis ({err}). Showing free results.")
        return rule, "rule"
    bar = st.progress(0.0, text="Reading updates with AI…")
    try:
        out = radar.classify_updates(
            df, "claude", client=client, model=model_id,
            progress=lambda p: bar.progress(p, text=f"Reading updates with AI… {int(p*100)}%"),
            on_usage=lambda u: add_usage(u, model_id),
            should_continue=budget_ok)
    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"AI analysis failed ({e}). Showing free results.")
        return rule, "rule"
    bar.empty()
    st.session_state["ai_runs"] = st.session_state.get("ai_runs", 0) + 1
    st.session_state["clf_fp"] = fp
    st.session_state["clf_df"] = out
    return out, "claude"


clf, active_engine = run_classification(raw, engine, api_key, MODEL_ID, run_ai)
clf["sev_rank"] = clf["severity"].map(SEV_ORDER)
roll = radar.portfolio_rollup(clf, recent_weeks=recent_weeks)
max_week = int(clf["week"].max())
window_mask = clf["week"] > max_week - recent_weeks


# --------------------------------------------------------------------------- #
# Small derived helpers
# --------------------------------------------------------------------------- #

def project_reason(project: str) -> tuple[str, str]:
    """A plain-English 'what's wrong right now' line + its colour."""
    sub = clf[(clf["project"] == project) & window_mask]
    for cat in ("blocker", "risk", "dependency"):
        hits = sub[sub["category"] == cat].sort_values("sev_rank")
        if len(hits):
            top = hits.iloc[0]
            lead = {"blocker": "Blocked", "risk": "Risk", "dependency": "Waiting on"}[cat]
            return f"{lead}: {top['update_text']}", CAT_BADGE[cat][1]
    return "All recent updates are on track.", CAT_BADGE["on_track"][1]


def project_trend(project: str) -> pd.DataFrame:
    sub = clf[clf["project"] == project]
    pivot = sub.pivot_table(index="week", columns="category", values="update_id",
                            aggfunc="count", fill_value=0)
    for c in ("blocker", "risk", "dependency"):
        if c not in pivot.columns:
            pivot[c] = 0
    pivot = pivot.reindex(range(1, max_week + 1), fill_value=0)
    return pivot[["blocker", "risk", "dependency"]].rename(
        columns={"blocker": "Blockers", "risk": "Risks", "dependency": "Dependencies"})


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

st.title("📡 Risk Radar")
st.markdown("#### Every team writes messy status updates. Risk Radar reads them all "
            "and tells you — in plain English — which projects are in trouble and why.")

if active_engine == "claude":
    eng = "🤖 AI analysis active"
elif active_engine == "rule-pending":
    eng = "⚙️ Free built-in engine — click **⚡ Run AI analysis** in the sidebar for sharper reading"
else:
    eng = "⚙️ Free built-in engine (no setup needed)"
st.caption(f"{eng}  ·  {len(raw)} updates  ·  {raw['project'].nunique()} projects  ·  "
           f"health based on the last {recent_weeks} weeks")

tab_overview, tab_project, tab_data, tab_about = st.tabs(
    ["📊 Overview", "🔍 Project view", "📥 The data", "ℹ️ How it works"])


# --------------------------------------------------------------------------- #
# Tab 1 — Overview (scannable, human-readable)
# --------------------------------------------------------------------------- #

with tab_overview:
    counts = roll["health"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 At risk", counts.get("RED", 0))
    c2.metric("🟠 Needs attention", counts.get("AMBER", 0))
    c3.metric("🟢 Healthy", counts.get("GREEN", 0))
    c4.metric("⛔ Open blockers", int((clf[window_mask]["category"] == "blocker").sum()))

    st.markdown("**Bird's-eye view — sorted worst-first.** "
                "Click any project to drill in and see *why* the AI flagged what it did.")

    for _, r in roll.iterrows():
        emoji, _, label = HEALTH_STYLE[r["health"]]
        title = (f"{emoji}  {r['project']}  ·  {label}"
                 f"      ⛔ {r['blockers']}   ⚠️ {r['risks']}   🔗 {r['dependencies']}")
        with st.expander(title):
            st.markdown(
                f"{health_pill(r['health'])} &nbsp;"
                f"<span style='color:#888'>{r['program']} · Milestone: {r['milestone']}</span>",
                unsafe_allow_html=True)
            st.caption(project_desc(r["project"]) or "—")

            reason, rcolor = project_reason(r["project"])
            st.markdown(f"**Bottom line:** <span style='color:{rcolor}'>{reason}</span>",
                        unsafe_allow_html=True)

            sub = clf[(clf["project"] == r["project"]) & window_mask]
            flagged = sub[sub["category"] != "on_track"].sort_values("sev_rank")
            if len(flagged):
                st.markdown("**What the AI flagged, and why** (most urgent first):")
                for _, u in flagged.iterrows():
                    lab, col = CAT_BADGE[u["category"]]
                    st.markdown(
                        f"<div style='border-left:3px solid {col};background:{col}10;"
                        f"padding:8px 11px;border-radius:5px;margin-bottom:8px'>"
                        f"{badge(lab, col)} &nbsp;{badge(u['severity'].upper(), '#555')}"
                        f"<div style='margin:5px 0;font-size:0.92em'>“{u['update_text']}”</div>"
                        f"<div style='font-size:0.83em;color:#555'>"
                        f"<b>🤖 Why flagged:</b> {u['rationale']}</div>"
                        f"<div style='font-size:0.83em;color:#555'>"
                        f"<b>✅ Suggested action:</b> {u['recommended_action']}</div></div>",
                        unsafe_allow_html=True)
            else:
                st.success("No open blockers, risks or dependencies in this window — healthy.")
            st.caption("→ Open the **Project view** tab for the full timeline, trend chart and digest.")


# --------------------------------------------------------------------------- #
# Tab 2 — Project view (the before → after hero)
# --------------------------------------------------------------------------- #

with tab_project:
    worst_first = list(roll["project"])
    project = st.selectbox("Choose a project", worst_first,
                           help="Ordered worst-first. Start at the top to see the radar working.")

    prow = roll[roll["project"] == project].iloc[0]
    st.markdown(f"## {project}")
    st.markdown(health_pill(prow["health"]) +
                f" &nbsp;<span style='color:#888'>{prow['program']} · Milestone: {prow['milestone']}</span>",
                unsafe_allow_html=True)
    st.write(project_desc(project) or "")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("⛔ Blockers", int(prow["blockers"]))
    m2.metric("⚠️ Risks", int(prow["risks"]))
    m3.metric("🔗 Dependencies", int(prow["dependencies"]))
    m4.metric("✅ On track", int(prow["on_track"]))

    st.markdown("##### 📈 How it's trending")
    st.caption("Weekly count of problems the radar flagged — watch them build (or clear).")
    st.line_chart(project_trend(project), color=["#b3261e", "#e08600", "#3b6fb3"])

    st.divider()
    st.markdown("### What Risk Radar makes of each update")
    st.markdown(
        "**“Risk Radar” is the AI.** It reads every update this team wrote and, for "
        "each one, decides what it really is and how urgent — so you don't have to. "
        "Each card below shows the **raw update** with the radar's **read** stapled "
        "underneath it. Newest first.")
    st.markdown(
        badge("⛔ Blocker", CAT_BADGE["blocker"][1]) + " work is stopped &nbsp; " +
        badge("⚠️ Risk", CAT_BADGE["risk"][1]) + " threatens the deadline &nbsp; " +
        badge("🔗 Dependency", CAT_BADGE["dependency"][1]) + " waiting on someone &nbsp; " +
        badge("✅ On track", CAT_BADGE["on_track"][1]) + " all good",
        unsafe_allow_html=True)

    pdata = clf[clf["project"] == project].sort_values("date", ascending=False)
    with st.container(height=460):
        for _, u in pdata.iterrows():
            label, color = CAT_BADGE[u["category"]]
            if u["category"] == "on_track":
                read = f"{badge(label, color)} &nbsp;<span style='color:#666'>no action needed</span>"
            else:
                read = (f"{badge(label, color)} &nbsp;{badge(u['severity'].upper(), '#555')} "
                        f"&nbsp;<span style='color:#444'>→ {u['recommended_action']}</span>")
            why = (f"<div style='font-size:0.8em;color:#777;margin-top:5px'>"
                   f"<b>Why:</b> {u['rationale']}</div>")
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;border-radius:8px;"
                f"padding:10px 12px;margin-bottom:10px'>"
                f"<div style='color:#888;font-size:0.8em'>🗒️ {u['date']} · {u['author']}</div>"
                f"<div style='margin:3px 0 7px 0'>“{u['update_text']}”</div>"
                f"<div style='background:{color}14;border-left:3px solid {color};"
                f"padding:7px 10px;border-radius:5px'>"
                f"<span style='font-size:0.82em;color:#888'>🤖 RADAR READ</span><br>{read}{why}</div>"
                f"</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📝 Status digest")
    st.caption("The one-paragraph brief a director could read in 20 seconds.")

    dg_key = f"dg|{project}|{df_fingerprint(raw)}|{recent_weeks}"
    rewrite = False
    if active_engine == "claude":
        rewrite = st.button("✨ Re-write this digest with AI", disabled=not budget_ok(),
                            help="Uses AI to write the summary. Cached afterwards — "
                                 "re-opening this project won't re-charge.")
    with st.spinner("Writing digest…"):
        if rewrite and budget_ok():
            client, _ = get_client(api_key)
            digest = radar.build_digest(clf, project, "claude", client=client,
                                        model=MODEL_ID, recent_weeks=recent_weeks,
                                        on_usage=lambda u: add_usage(u, MODEL_ID))
            st.session_state[dg_key] = digest
        elif st.session_state.get(dg_key) is not None:
            digest = st.session_state[dg_key]  # cached AI digest — no new spend
        else:
            digest = radar.build_digest(clf, project, "rule", recent_weeks=recent_weeks)

    emoji, color, _ = HEALTH_STYLE[digest.health]
    st.markdown(
        f"<div style='padding:14px 18px;border-radius:10px;background:{color}1a;"
        f"border-left:6px solid {color}'><h4 style='margin:0'>{emoji} {digest.health}</h4>"
        f"<p style='margin:6px 0 0 0;font-size:1.05em'>{digest.headline}</p></div>",
        unsafe_allow_html=True)
    da, db = st.columns(2)
    with da:
        st.markdown("**⛔ Blockers**")
        st.markdown("\n".join(f"- {b}" for b in digest.blockers) or "_None_")
        st.markdown("**⚠️ Top risks**")
        st.markdown("\n".join(f"- {r}" for r in digest.top_risks) or "_None_")
    with db:
        st.markdown("**🔗 Dependencies**")
        st.markdown("\n".join(f"- {d}" for d in digest.dependencies) or "_None_")
        st.markdown("**✅ Recommended next steps**")
        st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(digest.next_steps, 1)) or "_None_")


# --------------------------------------------------------------------------- #
# Tab 3 — The data
# --------------------------------------------------------------------------- #

with tab_data:
    st.markdown("### The dataset behind the radar")
    st.markdown(
        f"**{len(raw)} project updates** across **{raw['project'].nunique()} projects** spanning "
        "Careem-style lines of business — Careem Pay, Rides, Careem Food, Quik, platform and "
        "compliance — over ~10 weeks. It's deliberately messy, seeded with risks, blockers and "
        "cross-team dependencies so you can watch the radar catch them.")
    st.caption("⚠️ Illustrative mock data — hand-generated for this demo. It is **not** real "
               "Careem data and is not affiliated with, endorsed by, or sourced from Careem.")

    q = st.text_input("🔎 Search the updates", placeholder="e.g. KYC, blocked, payments…")
    view = clf.copy()
    proj_filter = st.multiselect("Filter by project", sorted(view["project"].unique()))
    if proj_filter:
        view = view[view["project"].isin(proj_filter)]
    if q:
        view = view[view["update_text"].str.contains(q, case=False, na=False)]

    cols = [c for c in ["date", "project", "author", "update_text",
                        "category", "severity", "rationale", "recommended_action"]
            if c in view.columns]
    st.caption(f"Showing {len(view)} of {len(clf)} updates.")
    st.dataframe(view[cols], width='stretch', hide_index=True)

    st.download_button("⬇️ Download the full dataset (CSV)",
                       raw.to_csv(index=False).encode("utf-8"),
                       file_name="project_updates.csv", mime="text/csv")
    st.info("📎 **Sharing it publicly:** this same file lives in the repo at "
            "`data/project_updates.csv`. Make the GitHub repo public and link directly "
            "to that file for your submission's 'public dataset link'.")

    with st.expander("What each column means"):
        st.markdown("""
| Column | Meaning |
|---|---|
| `date`, `week` | When the update was written |
| `program`, `project`, `milestone` | What it's about and the deadline it affects |
| `author`, `role`, `team` | Who wrote it |
| `update_text` | **The raw, messy update — the only thing the AI reads** |
| `category`, `severity`, … | **Added by Risk Radar** (the AI's output) |
| `signal_truth`, `severity_truth` | Hidden "correct answer" planted in the data — used only to score accuracy; the AI never sees it |
""")


# --------------------------------------------------------------------------- #
# Tab 4 — How it works
# --------------------------------------------------------------------------- #

with tab_about:
    st.markdown("""
### The idea in one line
Status updates pile up faster than anyone can read them. Risk Radar reads every
one, classifies it, and surfaces the trouble **before** it hits the deadline.

### The workflow
```
Raw updates  →  AI reads each one  →  Structured signal  →  Health rollup  →  Status digest
 (messy text)   risk / blocker /      + severity +          🔴🟠🟢 per        plain-English
                dependency / ok       next action           project          brief
```

1. **Ingest** free-text updates (standups, status emails, ticket comments).
2. **Classify** each into one signal — blocker / risk / dependency / on-track —
   with a severity and a recommended next step.
3. **Roll up** recent signals into a 🔴🟠🟢 health per project.
4. **Summarize** any project into a director-ready digest.

### Why AI *and* a free fallback
The app always runs live so anyone can try it with no setup. With AI analysis
enabled it reads for *intent* — telling a casual "blocked on lunch" from a
halted production rollout, which keyword rules can't. It runs on a fast,
low-cost model under the hood, because classification is a simple task — the
right-sized tool, not the priciest.
""")
    if has_truth:
        st.markdown("### Does it actually work? (accuracy vs. planted answers)")
        st.caption("The synthetic data carries a hidden 'correct' label per update. The radar "
                   "never sees it — it's used only here to measure how often the AI agrees.")
        agree = (clf["category"] == clf["signal_truth"]).mean()
        eng_name = "AI engine" if active_engine == "claude" else "Rule-based engine"
        st.metric(f"{eng_name} agreement with the planted answer", f"{agree*100:.1f}%")
        cm = (pd.crosstab(clf["signal_truth"], clf["category"])
              .reindex(index=radar.CATEGORIES, columns=radar.CATEGORIES, fill_value=0))
        st.caption("Rows = correct answer · Columns = what the radar predicted")
        st.dataframe(cm, width='content')
