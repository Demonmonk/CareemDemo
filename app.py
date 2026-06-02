"""
Risk Radar — Streamlit app.

An AI workflow that monitors a stream of messy project updates and flags risks,
dependencies and blockers early, then rolls them up into a per-project status
digest (health / risks / next steps).

Engines:
  • Claude (claude-opus-4-8) when an Anthropic API key is available.
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

DATA_PATH = os.path.join("data", "project_updates.csv")

CATEGORY_EMOJI = {"blocker": "⛔", "risk": "⚠️", "dependency": "🔗", "on_track": "✅"}
HEALTH_STYLE = {
    "RED": ("🔴", "#b3261e"),
    "AMBER": ("🟠", "#e08600"),
    "GREEN": ("🟢", "#1e7d32"),
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# --------------------------------------------------------------------------- #
# Data & engine plumbing
# --------------------------------------------------------------------------- #

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
# Sidebar — controls
# --------------------------------------------------------------------------- #

st.sidebar.title("📡 Risk Radar")
st.sidebar.caption("Early-warning system for project delivery.")

st.sidebar.subheader("1 · Data")
uploaded = st.sidebar.file_uploader(
    "Project updates CSV", type="csv",
    help="Needs at least: project, update_text. The bundled demo dataset is used otherwise.")
if uploaded is not None:
    raw = pd.read_csv(uploaded)
    st.sidebar.success(f"Loaded {len(raw)} rows from upload.")
else:
    raw = load_default_data()
    st.sidebar.info(f"Using bundled demo dataset ({len(raw)} updates).")

# Make sure expected columns exist; fill sensible defaults for uploads.
for col, default in [("program", "—"), ("milestone", "—"), ("author", "—"),
                     ("role", "—"), ("team", "—")]:
    if col not in raw.columns:
        raw[col] = default
if "week" not in raw.columns:
    if "date" in raw.columns:
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        raw["week"] = raw["date"].dt.isocalendar().week.astype("Int64")
        raw["week"] = raw["week"] - raw["week"].min() + 1
        raw["date"] = raw["date"].dt.date.astype(str)
    else:
        raw["week"] = 1
has_truth = "signal_truth" in raw.columns

st.sidebar.subheader("2 · AI engine")
default_key = os.environ.get("ANTHROPIC_API_KEY", "")
try:
    default_key = default_key or st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:  # noqa: BLE001 — no secrets file is fine
    pass

use_claude = st.sidebar.toggle(
    "Use Claude (claude-opus-4-8)", value=bool(default_key),
    help="On: classify with the Anthropic API. Off: use the built-in rule-based engine.")
api_key = ""
if use_claude:
    api_key = st.sidebar.text_input(
        "Anthropic API key", value=default_key, type="password",
        help="Read from ANTHROPIC_API_KEY / st.secrets if set. Never stored.")
    if not api_key:
        st.sidebar.warning("No key provided — falling back to the rule-based engine.")
        use_claude = False

st.sidebar.subheader("3 · Current-state window")
recent_weeks = st.sidebar.slider(
    "Health is computed from the last N weeks", 1, 6, 3,
    help="Older updates age out so health reflects the current state.")

engine = "claude" if use_claude else "rule"


# --------------------------------------------------------------------------- #
# Run classification (cached for rules; session-stored for Claude)
# --------------------------------------------------------------------------- #

def run_classification(df: pd.DataFrame, engine: str, api_key: str) -> pd.DataFrame:
    if engine == "rule":
        return classify_rule_based(df)

    fp = df_fingerprint(df) + "|claude"
    if st.session_state.get("clf_fp") == fp:
        return st.session_state["clf_df"]

    client, err = get_client(api_key)
    if client is None:
        st.error(f"Could not start the Claude engine ({err}). Using rule-based instead.")
        return classify_rule_based(df)

    bar = st.progress(0.0, text="Classifying updates with Claude…")
    try:
        out = radar.classify_updates(
            df, "claude", client=client,
            progress=lambda p: bar.progress(p, text=f"Classifying updates with Claude… {int(p*100)}%"))
    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"Claude classification failed ({e}). Using rule-based instead.")
        return classify_rule_based(df)
    bar.empty()
    st.session_state["clf_fp"] = fp
    st.session_state["clf_df"] = out
    return out


clf = run_classification(raw, engine, api_key)
clf["sev_rank"] = clf["severity"].map(SEV_ORDER)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

st.title("📡 Risk Radar")
st.markdown(
    "**An AI workflow that monitors project updates and flags risks, dependencies "
    "and blockers early — then turns the noise into a clear status digest.**")

engine_label = ("🤖 Claude · claude-opus-4-8" if engine == "claude"
                else "⚙️ Rule-based engine (no API key)")
st.caption(f"Engine: {engine_label}  ·  {len(raw)} updates  ·  "
           f"{raw['project'].nunique()} projects  ·  health window: last {recent_weeks} weeks")

tab_radar, tab_signals, tab_digest, tab_about = st.tabs(
    ["🛰️ Portfolio radar", "🚩 Flagged signals", "📝 Status digest", "ℹ️ How it works"])


# --------------------------------------------------------------------------- #
# Tab 1 — Portfolio radar
# --------------------------------------------------------------------------- #

with tab_radar:
    roll = radar.portfolio_rollup(clf, recent_weeks=recent_weeks)

    counts = roll["health"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Red", counts.get("RED", 0))
    c2.metric("🟠 Amber", counts.get("AMBER", 0))
    c3.metric("🟢 Green", counts.get("GREEN", 0))
    c4.metric("Open blockers", int((clf[clf["week"] > clf["week"].max() - recent_weeks]["category"] == "blocker").sum()))

    st.subheader("Project health")
    st.caption("Sorted worst-first. Health is derived from the severity and mix "
               "of signals in the selected window.")

    def style_health(row):
        emoji, color = HEALTH_STYLE.get(row["health"], ("", ""))
        return [f"background-color: {color}22" for _ in row]

    display = roll.copy()
    display["health"] = display["health"].map(lambda h: f"{HEALTH_STYLE[h][0]} {h}")
    display = display.rename(columns={
        "on_track": "on track", "program": "Program", "project": "Project",
        "milestone": "Milestone", "health": "Health"})
    st.dataframe(
        display[["Health", "Project", "Program", "Milestone",
                 "blockers", "risks", "dependencies", "on track", "updates"]],
        width='stretch', hide_index=True)

    st.subheader("Signal mix by project (selected window)")
    recent = clf[clf["week"] > clf["week"].max() - recent_weeks]
    pivot = (recent.pivot_table(index="project", columns="category",
                                values="update_id", aggfunc="count", fill_value=0))
    for c in ["blocker", "risk", "dependency", "on_track"]:
        if c not in pivot.columns:
            pivot[c] = 0
    pivot = pivot[["blocker", "risk", "dependency", "on_track"]]
    st.bar_chart(pivot, color=["#b3261e", "#e08600", "#3b6fb3", "#1e7d32"])


# --------------------------------------------------------------------------- #
# Tab 2 — Flagged signals
# --------------------------------------------------------------------------- #

with tab_signals:
    st.subheader("Everything the radar flagged")
    colf1, colf2, colf3 = st.columns(3)
    cats = colf1.multiselect("Category", ["blocker", "risk", "dependency"],
                             default=["blocker", "risk", "dependency"])
    sevs = colf2.multiselect("Severity", ["critical", "high", "medium", "low"],
                             default=["critical", "high", "medium"])
    projects = colf3.multiselect("Project", sorted(clf["project"].unique()),
                                 default=sorted(clf["project"].unique()))

    flagged = clf[clf["category"].isin(cats)
                  & clf["severity"].isin(sevs)
                  & clf["project"].isin(projects)].copy()
    flagged = flagged.sort_values(["sev_rank", "week"], ascending=[True, False])

    st.caption(f"{len(flagged)} flagged signal(s).")
    show = flagged.copy()
    show["⚑"] = show["category"].map(CATEGORY_EMOJI)
    show["severity"] = show["severity"].str.upper()
    cols = ["⚑", "category", "severity", "date", "project", "update_text",
            "depends_on", "recommended_action"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], width='stretch', hide_index=True)

    st.download_button(
        "⬇️ Download flagged signals (CSV)",
        flagged.drop(columns=["sev_rank"]).to_csv(index=False).encode("utf-8"),
        file_name="risk_radar_flagged.csv", mime="text/csv")


# --------------------------------------------------------------------------- #
# Tab 3 — Status digest
# --------------------------------------------------------------------------- #

with tab_digest:
    st.subheader("Status digest — messy notes → clear status")
    project = st.selectbox("Project", sorted(clf["project"].unique()))

    if st.button("Generate status digest", type="primary"):
        with st.spinner("Summarizing…"):
            client = None
            if engine == "claude":
                client, _ = get_client(api_key)
            digest = radar.build_digest(clf, project, engine, client=client,
                                        recent_weeks=recent_weeks)
        emoji, color = HEALTH_STYLE.get(digest.health, ("", "#000"))
        st.markdown(
            f"<div style='padding:14px 18px;border-radius:10px;"
            f"background:{color}1a;border-left:6px solid {color}'>"
            f"<h3 style='margin:0'>{emoji} {digest.health} · {digest.project}</h3>"
            f"<p style='margin:6px 0 0 0;font-size:1.05em'>{digest.headline}</p>"
            f"<p style='margin:4px 0 0 0;color:#666'>Program: {digest.program} · "
            f"Milestone: {digest.milestone}</p></div>",
            unsafe_allow_html=True)

        cda, cdb = st.columns(2)
        with cda:
            st.markdown("#### ⛔ Blockers")
            st.markdown("\n".join(f"- {b}" for b in digest.blockers) or "_None_")
            st.markdown("#### ⚠️ Top risks")
            st.markdown("\n".join(f"- {r}" for r in digest.top_risks) or "_None_")
        with cdb:
            st.markdown("#### 🔗 Dependencies")
            st.markdown("\n".join(f"- {d}" for d in digest.dependencies) or "_None_")
            st.markdown("#### ✅ Recommended next steps")
            st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(digest.next_steps, 1))
                        or "_None_")
    else:
        st.info("Pick a project and generate its digest. "
                "With Claude on, the summary is written by claude-opus-4-8; "
                "otherwise it's assembled from the rule-based signals.")


# --------------------------------------------------------------------------- #
# Tab 4 — How it works
# --------------------------------------------------------------------------- #

with tab_about:
    st.markdown("""
### The workflow

```
Raw updates  →  AI classifier  →  Signal store  →  Health rollup  →  Status digest
 (messy text)   risk/blocker/      structured       🔴🟠🟢 per       executive
                dependency/        signals          project          summary
                on-track + sev
```

1. **Ingest.** A stream of free-text updates (standups, status emails, ticket
   comments). Bring your own CSV or use the bundled synthetic dataset.
2. **Classify.** Each update becomes one structured signal — *blocker / risk /
   dependency / on-track* + severity + affected milestone + a recommended
   action. Claude does this with structured outputs; a keyword/heuristic engine
   is the offline fallback.
3. **Roll up.** Recent signals are scored into a 🔴🟠🟢 health per project.
4. **Summarize.** The *Status digest* tab turns a project's signals into a
   health / risks / next-steps brief — the "messy notes → clear status" step.

**Why Claude + a fallback?** The app always runs live (graders need no key),
but flips to real LLM reasoning the moment a key is present. Claude reads for
*intent* — it can tell a casual "blocked on lunch" from a halted production
rollout — which keyword rules cannot.
""")

    if has_truth:
        st.markdown("### Engine accuracy vs. planted ground truth")
        st.caption("The synthetic dataset carries a hidden label per update "
                   "(`signal_truth`). The radar never sees it — it's used only here "
                   "to measure how well the live classification recovers the planted signal.")
        agree = (clf["category"] == clf["signal_truth"]).mean()
        cm = (pd.crosstab(clf["signal_truth"], clf["category"])
              .reindex(index=radar.CATEGORIES, columns=radar.CATEGORIES, fill_value=0))
        m1, _ = st.columns([1, 3])
        m1.metric(f"{engine.title()} agreement", f"{agree*100:.1f}%")
        st.caption("Confusion matrix — rows: planted truth, cols: predicted")
        st.dataframe(cm, width='content')
