# 100-word summary

**Risk Radar** is an AI workflow that turns the daily noise of project updates —
standups, status emails, ticket comments — into early warnings. Each messy
update is classified into one structured signal — blocker, risk, dependency, or
on-track — with a severity, the reason it was flagged, and a recommended next
step. Signals roll up into a 🔴🟠🟢 health per project and a one-glance status
digest (covering the Status-Summarizer challenge too). It's built on Claude with
structured outputs and prompt caching, and ships with a free rule-based fallback
so the live demo runs with no API key. The dataset is synthetic, Careem-themed
mock data with hidden ground-truth labels to measure accuracy.
