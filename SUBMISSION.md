# Submission

## Team

- Team name: _TODO_
- Team members: Analyst · Neuro-Datascientist · Software Engineer
- GitHub fork URL: _TODO_
- Demo URL, if any: _local Streamlit dashboard (see How To Run)_
- Video walkthrough URL, if any: _TODO_

## Summary

**Outdoor Retail Radar — Agent A (Scout): a sourcing agent that turns the noisy real world into
clean, evidence-backed Signal Rows for a Swiss / DACH outdoor retailer.**

It is *agentic, not a pipeline*: a Claude (`claude-opus-4-8`) tool-calling loop decides which
activities/keywords/markets to investigate, gathers **real, citeable evidence** from four live
sources, scores what it finds, and records each finding as a **Signal Row** in the jury's contract
shape (`docs/data-contract.md#signal-row`) — every row backed by a real source URL and tagged with
the market it appears in. Recommendations are out of scope here: a downstream **Buyer agent
(Agent B)** consumes `out/signals.csv`. The agent's reasoning trace is shown live on the dashboard.

We improve the **signal-detection → evidence** front of the pipeline, with evidence quality and
multi-market coverage (for downstream DACH transferability) as first-class outputs.

## How To Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your ANTHROPIC_API_KEY (never commit it)

# 1. Run Agent A (Scout) — sources signals, writes out/signals.csv (+ signals_raw.csv, trace.json)
python -m Source.Agents.scout_agent --market DACH --seeds "trail running, approach shoes, ski touring, gravel bikepacking, merino base layers"

# 2. Open the dashboard (separate terminal)
streamlit run Source/Agents/scout_agent/dashboard.py
```

## Inputs

- Market: Switzerland / DACH (configurable via `--market`)
- Category: outdoor (footwear, apparel, equipment) — taxonomy is swappable
- Seed keywords: passed via `--seeds`; the agent expands them autonomously
- Sources: **Claude `web_search`** (cited URLs) · **Google Trends** (pytrends) · **Reddit** outdoor
  communities (public JSON) · **GDELT** global news/events
- Languages: English queries (DACH context surfaced via web_search)
- External APIs: Anthropic API (`ANTHROPIC_API_KEY`); all others are free/no-auth

## Outputs

- Dashboard or UI: `app.py` (Streamlit) — sourced signals (filter by type/market) + reasoning trace
- Report: this `SUBMISSION.md`
- Structured data: **`out/signals.csv`** — the deliverable, in the Signal Row contract shape
  (`out/signals_raw.csv` is the raw auto-captured provenance log)
- Reasoning trace: `out/trace.json`
- Screenshots or visuals: _add a dashboard screenshot before submitting_

## Ranked Opportunities

> Agent A produces **Signal Rows** (`out/signals.csv`), not rankings. Ranked opportunities are
> produced by the downstream **Buyer agent (Agent B)** from these signals. Paste B's top 5 here
> once it runs; until then, the strongest sourced signals (highest `signal_score`) stand in.

| Rank | Opportunity | Evidence | Confidence |
| --- | --- | --- | --- |
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |

## Evidence Trail

Every recommendation row carries 2–4 real `evidence_urls`; every intermediate observation is logged
as a row in `out/signals.csv` with its own `url` and `created_by_tool`. Evidence comes from
`web_search` (cited reporting/brand pages), `trends.google.com`, `reddit.com`, and GDELT article URLs.

## Reusability

Swap three things to retarget the system: the **seed keywords** (`--seeds`), the **market geo**
(`--market`, mapped to a Google Trends region), and the **community sources** (subreddit list in
`Source/Agents/scout_agent/tools.py`). The contract-shaped output and the Scout loop are domain-agnostic — the same
architecture works for beauty, home, or any other vertical by repointing the sources.

## Known Limitations

- Live APIs can rate-limit on stage; the first good response from each tool is cached under
  `data/cache/` (real fetched data, not synthetic) so the demo replays deterministically.
- `signal_score` is a transparent heuristic (see below), not a calibrated model.
- Coverage vs. Swiss retailers is reasoned by the agent from public info, not scraped from
  retailer catalogs — flagged as `unknown` when unverifiable.
- Clustering uses a token-overlap fallback unless `sentence-transformers` is installed.

## Architecture Notes

```
seed keywords ─▶ Agent A — Scout (claude-opus-4-8, tool-calling loop)
                   ├─ web_search        (Claude server tool — cited URLs)
                   ├─ trend_momentum    (Google Trends / pytrends)
                   ├─ community_heat    (Reddit public JSON)
                   ├─ event_signals     (GDELT news/events + red flags)
                   ├─ score_emerging    (emerging_score formula)
                   └─ emit_signal ─▶ out/signals.csv  (THE deliverable — Signal Row contract)
                          │                 │
                          │                 └─▶ Agent B (Buyer, downstream) ─▶ recommendations
                          └─ reasoning trace ─▶ trace.json ─▶ Streamlit dashboard (app.py)
```

**`signal_score` scale:** `0.0–1.0`, where
`emerging_score = clamp01( velocity × log1p(engagement) / 6 × event_lift )` —
`velocity` = normalized search/community growth, `engagement` = social interaction volume,
`event_lift` ≥ 1.0 when a related global event boosts the category (see `Source/Agents/scout_agent/score.py`).
**`confidence`:** `high | medium | low`.
