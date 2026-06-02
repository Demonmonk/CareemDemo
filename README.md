# 📡 Risk Radar

**An AI workflow that monitors project updates to flag risks, dependencies and
blockers early — and rolls them into a clear status digest (health · risks ·
next steps).**

Built as a take-home AI challenge. It tackles two of the three prompts at once:

- **Risk Radar** — the core monitoring workflow.
- **Status Summarizer** — falls out of it as the per-project status digest.

> Live demo runs **with no API key** thanks to a built-in rule-based engine. Add
> an Anthropic key and it flips to real LLM reasoning with `claude-opus-4-8`.

---

## What it does

```
Raw updates  →  AI classifier  →  Signal store  →  Health rollup  →  Status digest
 (messy text)   risk/blocker/      structured       🔴🟠🟢 per       executive
                dependency/        signals          project          summary
                on-track + sev
```

1. **Ingest** a stream of free-text updates — standups, status emails, ticket
   comments. The kind of noise where *"backend slipped again, still waiting on
   the payments team, might miss the launch"* hides a risk, a dependency **and**
   a blocker in one sentence.
2. **Classify** each update into one structured signal: `blocker` / `risk` /
   `dependency` / `on_track`, plus severity, affected milestone, what it depends
   on, a rationale, and a recommended action.
3. **Roll up** recent signals into a 🔴 / 🟠 / 🟢 health per project.
4. **Summarize** any project into a director-ready status digest.

## Two engines, one interface

| Engine | When | How |
|---|---|---|
| **Claude** (`claude-opus-4-8`) | An `ANTHROPIC_API_KEY` is present | Structured outputs (`messages.parse`) + prompt caching on the static instructions. Reads for *intent*. |
| **Rule-based** | No key | Transparent keyword/heuristic classifier. Always available, zero cost — so graders can run it instantly. |

The app picks the engine automatically and shows which one is live.

## Run it locally

```bash
pip install -r requirements.txt
python generate_dataset.py        # writes data/project_updates.csv (already committed)
streamlit run app.py
```

Optional — enable Claude:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

…or paste the key into the sidebar. You can also drop it in
`.streamlit/secrets.toml` (git-ignored).

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), point a new app at
   `app.py`.
3. (Optional) Add `ANTHROPIC_API_KEY` under **App → Settings → Secrets**.

Runs out of the box without the key.

## The dataset

`data/project_updates.csv` — **218 self-generated, synthetic updates** across 12
projects and 6 programs at a fictional generic enterprise ("Helios Group"),
spanning 10 weeks. No real or confidential data.

It's deliberately messy and seeded with risks, blockers and cross-team
dependencies so the radar can be seen catching them. Each row also carries a
**hidden ground-truth label** (`signal_truth`, `severity_truth`) that the radar
never sees — used only on the *How it works* tab to report classification
accuracy (the rule engine alone recovers the planted signal ~93% of the time).

Regenerate it any time with `python generate_dataset.py` (deterministic, seeded).

### Bring your own data
Upload any CSV with at least `project` and `update_text` columns. `date`,
`program`, `milestone`, `author`, etc. are used if present.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI (radar, flagged signals, status digest, accuracy) |
| `radar.py` | Core workflow — both engines, health rollup, digests |
| `prompts.py` | The prompts (the "Status Summarizer" prompt engineering) |
| `generate_dataset.py` | Reproducible synthetic dataset generator |
| `data/project_updates.csv` | The public demo dataset |

## Design notes

- **Claude usage** follows current best practice: `claude-opus-4-8`, structured
  outputs via `messages.parse`, and `cache_control` on the static system prompt
  so the instruction prefix is prompt-cached across batched calls.
- **Graceful degradation** is a feature, not a hack — the rule engine keeps the
  demo honest and runnable, and the side-by-side accuracy view makes the value
  of the LLM explicit.
- **Synthetic-with-ground-truth** is the rigorous choice for an evaluation: you
  can show *input → correctly flagged signal*, not just vibes.
