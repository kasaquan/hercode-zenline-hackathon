# Zenline Outdoor Retail Recommender

> A three-agent decision system that turns noisy market signals into one clear answer:
> **what should this retailer test, buy, launch, or monitor next?**

![Outdoor opportunity radar](assets/alpine-opportunity-hero.png)

Retail buying teams are flooded with weak signals — search spikes, niche communities, new
materials, marketplace bestsellers, competitor drops. The hard part isn't finding more data; it's
turning it into a defensible decision. Zenline does that with three cooperating Claude agents and a
deterministic scoring core, then explains every recommendation with real evidence and an auditable
score.

Built for the [HerCode × Zenline hackathon](docs/challenge.md) (Swiss / DACH outdoor retail), but
**generic-first by design** — point it at any category or market by changing inputs, not code.

---

## How it works

```
Customer query (chat or CLI)
        │
        ▼
  Agent 2 — Decision (orchestrator)
        │  parses request → generic seed keywords
        ├──────────────► Agent 1 — Scout        ┐  run in parallel
        │                 web_search · Trends ·  │
        │                 Reddit · GDELT         │
        │                 → signals.csv          │
        └──────────────► Agent 3 — Profiler     ┘
                          website · PDF · notes
                          → company_profile.json
        │  join
        ▼
  group → score (8 dimensions, dynamic weights) → analytics multiplier → rank
        │
        ▼
  recommendations.csv  +  recommendations.json  →  Streamlit app
```

| Agent | Role | What it produces |
| --- | --- | --- |
| **Agent 1 — Scout** | Agentic sourcing loop (`claude-opus-4-8`). Gathers real, cited evidence from `web_search`, Google Trends, Reddit, and GDELT. | `out/signals.csv` — Signal Rows, each backed by a real URL and tagged with the market it appears in |
| **Agent 3 — Profiler** | Reads the company website + strategy PDF + notes; infers strategic assortment gaps. | `out/company_profile.json` |
| **Agent 2 — Decision** | Parses the request, fans out to Scout + Profiler **in parallel**, groups signals into opportunities, and scores each on 8 buyer dimensions with **dynamic, auditable weights** plus a statistical analytics layer. | `out/recommendations.csv` (Zenline contract) + `out/recommendations.json` |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY (never commit it)

python Source/main.py           # launches the chat app at http://localhost:8501
```

Prefer the command line? Run the full pipeline headless:

```bash
python -m Source.Agents.decision_agent.pipeline \
  --query "Decathlon CH is looking for decision support on winter jackets" \
  --market DACH --company https://www.decathlon.ch --notes "Premium, 12 CH stores"
```

Each agent also runs standalone — see [`SUBMISSION.md`](SUBMISSION.md#how-to-run).

## What makes it more than a research report

- **Evidence-first.** Every recommendation traces back to real source URLs; the agent never invents
  citations. Intermediate findings are logged as Signal Rows with their own provenance.
- **Auditable scoring.** `final_score` (0–100) is a weighted blend of eight dimensions. The weights
  are **dynamic** — they shift with query intent, the company profile, and evidence quality — and
  every adjustment is recorded in `weights_used` / `weight_adjustment_reasons`.
- **Statistical rigor.** A deterministic analytics layer (clustering, trend velocity, market
  saturation, anomaly detection, geographic concentration, source quality, diversity) applies a
  transparent multiplier on top of the base score.
- **Transferability is explicit.** Swiss/DACH fit is a scored dimension, not an afterthought —
  flagged as inferred when local evidence is missing.
- **Reusable.** Swap the product focus, market, or community sources and the same flow works for a
  different vertical. Outdoor-specific rules exist only as optional normalization.

## Repository layout

```
Source/
  main.py                       # entry point — launches the Streamlit app
  App/customer_chat.py          # conversational intake + results (Profile · Signals · Recommendations)
  Agents/
    scout_agent/                # Agent 1 — sourcing loop, tools, scoring, schema
    agent_3.py                  # Agent 3 — company profile extractor
    decision_agent/
      decision.py               # Agent 2 — grouping + 8-dimension dynamic scoring
      analytics.py              # statistical signal analysis layer
      pipeline.py               # parallel orchestrator (Scout + Profiler → Decision)
docs/                           # challenge brief, data contract, evaluation rubric
examples/                       # sample signals.csv + company_profile.json
out/                            # generated artifacts (recommendations, signals, traces)
SUBMISSION.md                   # full hackathon writeup, run modes, ranked results
```

## Outputs

Running the pipeline writes everything to `out/`:

- **`recommendations.csv`** — the deliverable, in the [Zenline Recommendation Row](docs/data-contract.md#recommendation-row) contract
- **`recommendations.json`** — full scoring detail: per-dimension scores, dynamic weights, analytics adjustments, risks, next steps
- **`signals.csv`** / `signals_raw.csv` — sourced [Signal Rows](docs/data-contract.md#signal-row) + raw provenance log
- **`company_profile.json`** — extracted company profile
- **`trace.json`** — Scout's live reasoning trace

## Documentation

- [`SUBMISSION.md`](SUBMISSION.md) — full writeup: approach, run modes, ranked opportunities, evidence trail
- [`docs/data-contract.md`](docs/data-contract.md) — Signal Row & Recommendation Row schemas
- [`docs/evaluation.md`](docs/evaluation.md) — judging rubric
- [`Source/Agents/decision_agent/design.txt`](Source/Agents/decision_agent/design.txt) — Agent 2 design notes

## Tech

Python · [Anthropic Claude](https://www.anthropic.com) (`claude-opus-4-8`) with `web_search` ·
Streamlit · pandas · pytrends. Source APIs (Google Trends, Reddit, GDELT) are free and
no-auth; only the Anthropic API needs a key.

---

<sub>Team **HappyCats** — Cheng, Sara, Quan · HerCode × Zenline Hackathon, June 2026.
Decision-support output; review by a human buyer before acting.</sub>
