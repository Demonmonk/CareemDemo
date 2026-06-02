# 100-word summary

**Risk Radar** is an AI early-warning system for delivery. It ingests the messy
status updates a program manager drowns in — standups, emails, Jira comments —
and uses the **Claude API** to classify each into a structured signal: blocker,
risk, dependency or on-track, with a severity, the reason it was flagged, and a
recommended next step. Signals roll up into a RAG health per project and a
director-ready status digest. Built with structured outputs, prompt caching and
a rule-based fallback (so it runs with no key), plus a hard spend cap for safe
public use. Accuracy is measured against planted ground-truth labels.
