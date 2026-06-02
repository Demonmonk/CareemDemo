# Risk Radar — Submission Cover Sheet

> **An AI early-warning system that turns the messy flood of project updates
> into a clear, decision-ready status — flagging risks, blockers and
> dependencies before they hit the deadline.**

**Challenge attempted:** #1 — Risk Radar. It also delivers #3 — Status
Summarizer — as a built-in output of the same workflow.

---

## Links

| | |
|---|---|
| ▶ **Live prototype** | _paste your Streamlit URL_ |
| ⌥ **Source code (GitHub)** | _paste your repo URL_ |
| ⛁ **Public dataset (CSV)** | _paste the link to `data/project_updates.csv`_ |

*The live app runs instantly in any browser — no login, no setup.*

---

## 100-word summary

Risk Radar is an AI early-warning system for delivery. It ingests the messy
status updates a program manager drowns in — standups, emails, Jira comments —
and uses the **Claude API** to classify each into a structured signal: blocker,
risk, dependency or on-track, with a severity, the reason it was flagged, and a
recommended next step. Signals roll up into a RAG health per project and a
director-ready status digest. Built with structured outputs, prompt caching and
a rule-based fallback (so it runs with no key), plus a hard spend cap for safe
public use. Accuracy is measured against planted ground-truth labels.

---

## The program-manager lens (the problem it solves)

Delivery doesn't fail in one big bang — it slips one buried update at a time:
*"still waiting on the Maps team," "KYC vendor's been down three days," "scope
grew after review."* By the time it surfaces in a steering deck, the milestone
is already gone. Risk Radar is the **early-warning layer a PMO actually needs**:

- **Surfaces risk early** — reads every update and flags the trouble the day
  it's written, not at sprint's end.
- **Makes dependencies and blockers explicit** — the things that quietly sink
  cross-team delivery.
- **Speaks the language of status** — RAG health, owners, and concrete next
  steps; the status digest is the weekly update, written for you.
- **Shows its reasoning** — every flag comes with *why*, so it earns trust
  instead of being a black box.

## Under the hood (the technical lens)

- **Claude API** for classification and summarization, using **structured
  outputs** so every result is reliable, typed JSON — not free text to parse.
- **Prompt caching** on the static instructions to keep repeated calls fast and
  cheap; a **fast, low-cost model** chosen deliberately because classification
  is a high-volume, well-scoped task.
- **Graceful rule-based fallback** so the app is fully functional with no API
  key — anyone can evaluate it instantly.
- **Production-minded guardrails** for a public demo: server-side-only secrets,
  a hard shared spend cap, and result caching so nothing is ever re-charged.
- **Evaluated, not asserted** — the synthetic dataset carries hidden
  ground-truth labels the model never sees, so accuracy is a measured number.

## 30-second evaluation guide

1. **Overview** — projects ranked worst-first; open a red one to see *why* the
   AI flagged each issue.
2. **Project view** — each raw update shown next to the AI's read of it, plus a
   trend line and a status digest.
3. **How it works** — the workflow and the AI's measured accuracy vs. the hidden
   ground-truth labels.

---

## Dataset note

Synthetic, illustrative mock data hand-generated for this demo, themed around
Careem-style lines of business (Careem Pay, Rides, Careem Food, Quik, platform,
compliance). **Not** real Careem data and not affiliated with, endorsed by, or
sourced from Careem. No confidential information is included.

## Screenshots
_Paste 2–3 here: the Overview, an expanded project, and the Project view's
raw-update-vs-AI-read cards._
