# 100-word summary

**Risk Radar** is an AI workflow that turns the daily noise of project
updates — standups, status emails, ticket comments — into early warnings.
Each free-text update is classified into one structured signal (blocker, risk,
dependency, or on-track) with a severity, affected milestone, and recommended
action; signals roll up into a 🔴🟠🟢 health per project and a one-glance status
digest (the "Status Summarizer" prompt). It runs on `claude-opus-4-8` with
structured outputs and prompt caching, and ships with a rule-based fallback so
the live Streamlit demo works without an API key. Data is a self-generated,
fully synthetic dataset of 218 updates — with hidden ground-truth labels to
measure accuracy.
