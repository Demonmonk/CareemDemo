# 📡 Risk Radar — AI early-warning for project delivery

> Take-home submission for the AI challenge. It tackles **Challenge 1 — Risk
> Radar**, and folds in **Challenge 3 — Status Summarizer** as one of its outputs.

**The idea in one line:** teams write messy status updates faster than anyone can
read them. Risk Radar reads every update with AI, flags **risks, blockers and
dependencies early**, and turns the noise into a clear, per-project status — in
plain English, with the reasoning shown.

| | |
|---|---|
| 🔗 **Live demo** | _add your Streamlit URL here_ |
| 📊 **Dataset** | [`data/project_updates.csv`](data/project_updates.csv) |
| 📝 **100-word summary** | [`SUMMARY.md`](SUMMARY.md) |

---

## What it does

```
Raw updates  →  AI reads each one  →  Structured signal  →  Health rollup  →  Status digest
 (messy text)   risk / blocker /      + severity +          🔴🟠🟢 per        plain-English
                dependency / ok       why + next action     project          brief
```

1. **Ingest** a stream of free-text updates — standups, status emails, ticket
   comments. The kind of noise where *"the price-cap rules depend on the ETA
   service from Maps, which has slipped, might miss Eid readiness"* hides a
   risk **and** a dependency in one sentence.
2. **Classify** each update into one structured signal — `blocker` / `risk` /
   `dependency` / `on-track` — with a **severity**, the **reason it was
   flagged**, and a **recommended next step**.
3. **Roll up** recent signals into a 🔴 / 🟠 / 🟢 health for every project.
4. **Summarize** any project into a director-ready status digest.

## Why it's more than a prompt

- It's a **monitoring workflow**, not a one-off prompt — ingest → classify →
  roll up → summarize.
- Every signal is **auditable**: the radar shows *why* it flagged each update
  (it quotes the trigger), which is the whole point of an early-warning system.
- The **status digest** (health · risks · next steps) falls out for free —
  that's Challenge 3 covered by the same pipeline.

## Try it in 30 seconds

1. Open the live demo (link above) — it runs immediately, no login.
2. **Overview** tab → projects sorted worst-first. **Click a red one** to drill
   in and see *why* the AI flagged what it did.
3. **Project view** → see the **raw update next to the AI's read of it**, plus a
   problems-over-time trend and a status digest.
4. **The data** tab → search and browse the full dataset.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app runs out of the box on a free, built-in engine — **no API key needed**.
To enable AI analysis, provide an Anthropic key via the environment or
`.streamlit/secrets.toml`:

```toml
# .streamlit/secrets.toml   (git-ignored)
ANTHROPIC_API_KEY = "sk-ant-..."
```

The key is read only from the server side — it is **never entered or shown in
the UI**.

## How the AI works

- Built on **Claude** via the Anthropic API, using **structured outputs**
  (`messages.parse`) so every classification comes back as reliable, typed JSON,
  and **prompt caching** on the static instructions to keep repeated calls cheap.
- **Cost-aware:** classification is a simple task, so it runs on a fast,
  low-cost model by default — the right-sized tool for the job.
- **Graceful fallback:** a transparent, rule-based engine means the app is fully
  functional with **no key**, so it can be evaluated instantly. Turn on AI
  analysis for sharper, intent-aware reading (it can tell a casual "blocked on
  lunch" from a halted production rollout).
- **Guardrails for a public demo:** a hard, shared spend cap stops abuse, and
  results are cached so nothing is ever re-charged.

## The dataset

[`data/project_updates.csv`](data/project_updates.csv) — **synthetic project
updates** across **12 projects** spanning Careem-style lines of business
(Careem Pay, Rides, Careem Food, Quik, platform and compliance), over ~10 weeks.
It's deliberately messy and seeded with risks, blockers and cross-team
dependencies so the radar can be seen catching them.

> **Disclaimer:** This is **illustrative mock data**, hand-generated for this
> demo. It is **not** real Careem data and is **not** affiliated with, endorsed
> by, or sourced from Careem — the company and product names are used only to
> make the example domain-relevant. No real or confidential data is included.

Each row also carries a **hidden ground-truth label** (`signal_truth`) that the
radar never sees — used only to measure accuracy. The rule-based engine alone
recovers the planted signal **~94%** of the time; with AI analysis on, the
reasoning is sharper still. Regenerate the data any time with
`python generate_dataset.py` (deterministic, seeded).

## Repo layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit app — Overview, Project view, Data, How-it-works |
| `radar.py` | The workflow — both engines, health rollup, status digest |
| `prompts.py` | The prompts (the Status-Summarizer prompt engineering) |
| `generate_dataset.py` | Reproducible synthetic-dataset generator |
| `data/project_updates.csv` | The public dataset |
| `SUMMARY.md` | The 100-word summary |

## Design decisions worth noting

- **Framed as a workflow**, not a chatbot — the value is the pipeline and the
  rollup, not a single clever prompt.
- **Structured outputs + a rule-based fallback** make it reliable *and* always
  runnable.
- **Synthetic data with planted ground truth** is the rigorous choice for an
  evaluation — you can show *input → correctly-flagged signal*, with a measured
  accuracy number rather than vibes.
- **Production-minded touches** — server-side-only secrets, a hard spend cap,
  and result caching — because a public demo has to be safe and cheap to run.
