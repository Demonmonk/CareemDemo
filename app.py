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
import os

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
    "Wallet 2.0": "Next-gen digital wallet — tokenized cards, KYC, top-ups & refunds.",
    "Settlement Engine": "Back-office engine that reconciles ledgers and settles transactions.",
    "Mobile App Revamp": "Full redesign of the consumer app — navigation, offline mode, checkout.",
    "Loyalty Program": "Points, tiers and rewards — the earn-and-burn loyalty system.",
    "Lakehouse Migration": "Moving analytics off the legacy warehouse onto a modern lakehouse.",
    "Exec Analytics Dashboard": "Executive KPI dashboard — revenue, retention and cohort views.",
    "Kubernetes Migration": "Re-platforming services onto Kubernetes with autoscaling.",
    "API Gateway Rollout": "New gateway — rate limiting, auth and canary routing for all services.",
    "SOC 2 Type II": "Security compliance audit — evidence, controls and runbooks.",
    "Merchant Onboarding Portal": "Self-serve portal for merchants to sign up and get risk-scored.",
    "Payouts Reconciliation": "Matching merchant payouts to bank statements and handling exceptions.",
    "Marketing Automation": "Segmentation, email templates and campaign scheduling for growth.",
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
default_key = os.environ.get("ANTHROPIC_API_KEY", "")
try:
    default_key = default_key or st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:  # noqa: BLE001 — no secrets file is fine
    pass

# Fixed, low-cost model under the hood — not user-selectable.
MODEL_ID = "claude-haiku-4-5"
api_key, model_id = default_key, MODEL_ID
have_key = bool(default_key)

run_ai = False
if have_key:
    run_ai = st.sidebar.button(
        "⚡ Run AI analysis",
        help="Reads every update with AI for sharper results. The free built-in "
             "engine shows until you click; results are cached so it won't re-run.")
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

def run_classification(df, engine, api_key, model_id, run_claude):
    rule = classify_rule_based(df)
    if engine != "claude":
        return rule, "rule"
    fp = df_fingerprint(df) + "|" + model_id
    if st.session_state.get("clf_fp") == fp:
        return st.session_state["clf_df"], "claude"
    if not run_claude:
        return rule, "rule-pending"
    client, err = get_client(api_key)
    if client is None:
        st.error(f"Could not start the Claude engine ({err}). Showing rule-based results.")
        return rule, "rule"
    bar = st.progress(0.0, text=f"Reading updates with {model_id}…")
    try:
        out = radar.classify_updates(df, "claude", client=client, model=model_id,
                                     progress=lambda p: bar.progress(p, text=f"Reading updates with {model_id}… {int(p*100)}%"))
    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"Claude classification failed ({e}). Showing rule-based results.")
        return rule, "rule"
    bar.empty()
    st.session_state["clf_fp"] = fp
    st.session_state["clf_df"] = out
    return out, "claude"


clf, active_engine = run_classification(raw, engine, api_key, model_id, run_ai)
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

    st.markdown("Projects sorted **worst-first**. Each line is the AI's read of the "
                "latest updates — no spreadsheet-reading required.")

    for _, r in roll.iterrows():
        emoji, color, label = HEALTH_STYLE[r["health"]]
        reason, rcolor = project_reason(r["project"])
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(
                    f"{health_pill(r['health'])}  &nbsp; **{r['project']}** "
                    f"<span style='color:#888'>· {r['program']}</span>",
                    unsafe_allow_html=True)
                st.caption(project_desc(r["project"]) or "—")
                st.markdown(
                    f"<span style='color:{rcolor}'>▸ {reason}</span>",
                    unsafe_allow_html=True)
            with right:
                st.markdown(
                    f"<div style='text-align:right;line-height:1.6'>"
                    f"⛔ <b>{r['blockers']}</b> blockers<br>"
                    f"⚠️ <b>{r['risks']}</b> risks<br>"
                    f"🔗 <b>{r['dependencies']}</b> dependencies<br>"
                    f"<span style='color:#888'>Milestone: {r['milestone']}</span></div>",
                    unsafe_allow_html=True)


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
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;border-radius:8px;"
                f"padding:10px 12px;margin-bottom:10px'>"
                f"<div style='color:#888;font-size:0.8em'>🗒️ {u['date']} · {u['author']}</div>"
                f"<div style='margin:3px 0 7px 0'>“{u['update_text']}”</div>"
                f"<div style='background:{color}14;border-left:3px solid {color};"
                f"padding:7px 10px;border-radius:5px'>"
                f"<span style='font-size:0.82em;color:#888'>🤖 RADAR READ</span><br>{read}</div>"
                f"</div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📝 Status digest")
    st.caption("The one-paragraph brief a director could read in 20 seconds.")

    digest_engine = "claude" if active_engine == "claude" else "rule"
    rewrite = False
    if active_engine == "claude":
        rewrite = st.button("✨ Re-write this digest with AI")
    with st.spinner("Writing digest…"):
        client = None
        if digest_engine == "claude" and (rewrite or st.session_state.get(f"dg_{project}")):
            client, _ = get_client(api_key)
            st.session_state[f"dg_{project}"] = True
        digest = radar.build_digest(clf, project, "claude" if client else "rule",
                                    client=client, model=model_id, recent_weeks=recent_weeks)

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
        f"**{len(raw)} project updates** across **{raw['project'].nunique()} projects** at a "
        "fictional company, spanning ~10 weeks. It's fully synthetic — no real or confidential "
        "data — and deliberately messy, seeded with real risks, blockers and cross-team "
        "dependencies so you can watch the radar catch them.")

    q = st.text_input("🔎 Search the updates", placeholder="e.g. KYC, blocked, payments…")
    view = clf.copy()
    proj_filter = st.multiselect("Filter by project", sorted(view["project"].unique()))
    if proj_filter:
        view = view[view["project"].isin(proj_filter)]
    if q:
        view = view[view["update_text"].str.contains(q, case=False, na=False)]

    cols = [c for c in ["date", "project", "author", "update_text",
                        "category", "severity", "recommended_action"] if c in view.columns]
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
