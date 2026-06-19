# Submission

## Team

- Team name: HappyCats
- Team members: Cheng, Sara, Quan
- GitHub fork URL: https://github.com/kasaquan/hercode-zenline-hackathon
- Demo URL, if any: _local Streamlit app (see How To Run)_
- Video walkthrough URL, if any: _TODO_

## Summary

**Zenline Outdoor Retail Recommender — a three-agent decision system that turns the noisy real
world into one clear answer: what should this retailer test, buy, launch, or monitor next?**

A customer describes their company in a short chat. Behind it, three agents run:

1. **Agent 1 — Scout (sourcing).** An agentic Claude (`claude-opus-4-8`) tool-calling loop that
   gathers **real, citeable evidence** from four live sources (Claude `web_search`, Google Trends,
   Reddit, GDELT), scores each finding, and records it as a **Signal Row** in the jury's contract
   shape (`docs/data-contract.md#signal-row`) — every row backed by a real URL and tagged with the
   market it appears in.
2. **Agent 3 — Company Profiler.** A Claude extractor that reads the company website + optional
   strategy PDF + freeform notes and returns a structured profile, *inferring strategic assortment
   gaps* (what's missing to execute the stated strategy).
3. **Agent 2 — Decision Agent (orchestrator).** Parses the customer request, fans out to Scout and
   Profiler **in parallel**, then groups signals into canonical opportunities and scores each on
   **eight buyer dimensions with dynamic weights** that adapt to the query, the company profile,
   and the evidence quality. A deterministic **analytics layer** (clustering, trend velocity,
   market saturation, anomalies, geography, source quality, diversity) then applies a transparent
   multiplier. The output is a ranked, evidence-backed recommendation set in the Zenline contract.

The whole flow is **generic-first**: seed expansion and opportunity grouping are driven by the
customer's product focus and each signal's own content, so the same system retargets to any
category or market by changing inputs — not code.

## How To Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your ANTHROPIC_API_KEY (never commit it)

# Main demo — conversational app: intake → Scout + Profiler (parallel) → Decision → ranked results
python Source/main.py           # opens http://localhost:8501 (Streamlit)
```

Headless / CLI (same orchestrator the app calls):

```bash
# Full pipeline: parse query → Scout + Profiler in parallel → Decision → out/recommendations.*
python -m Source.Agents.decision_agent.pipeline \
  --query "Decathlon CH is looking for decision support on winter jackets" \
  --market DACH --company https://www.decathlon.ch --notes "Premium, 12 CH stores"
```

Run any agent on its own:

```bash
# Agent 1 — Scout only (writes out/signals.csv, signals_raw.csv, trace.json)
python -m Source.Agents.scout_agent --market DACH --seeds "trail running, ski touring, merino base layers"

# Agent 2 — Decision only, re-scoring existing artifacts (no live browsing)
python -m Source.Agents.decision_agent.decision \
  --query "Decathlon CH is looking for decision support on winter jackets" \
  --market DACH --signals out/signals.csv --profile out/company_profile.json

# Agent 3 — Company Profiler self-test
python -m Source.Agents.agent_3
```

## Inputs

- **Market:** CH / AT / DE / DACH (configurable; chosen in chat or via `--market`)
- **Product focus:** free text — *any* category ("winter jackets", "ultralight hiking",
  "sustainable gear", …). Drives Scout seed keywords and Decision weighting.
- **Company context (Agent 3):** website URL, optional strategy PDF text, freeform notes
- **Sources (Agent 1):** **Claude `web_search`** (cited URLs) · **Google Trends** (pytrends) ·
  **Reddit** outdoor communities (public JSON) · **GDELT** global news/events
- **External APIs:** Anthropic API (`ANTHROPIC_API_KEY`); all source APIs are free / no-auth

## Outputs

- **App / UI:** `Source/App/customer_chat.py` (launched by `Source/main.py`) — conversational
  intake plus three result tabs: **Company Profile**, **Emerging Signals**, **Recommendations**
  (with per-opportunity score breakdowns and a `recommendations.csv` download).
- **Structured deliverables in `out/`:**
  - `recommendations.csv` — **the jury-facing deliverable**, in the Zenline Recommendation Row
    contract (`docs/data-contract.md#recommendation-row`)
  - `recommendations.json` — richer scoring/debug view (per-dimension scores, dynamic
    `weights_used`, `weight_adjustment_reasons`, analytics adjustments, risks, next steps)
  - `signals.csv` — Agent 1 curated Signal Rows (`signals_raw.csv` = raw provenance log)
  - `company_profile.json` — Agent 3 structured profile
  - `agent2_request.json` — parsed customer request + seed keywords
  - `trace.json` — Scout's live reasoning trace
- **Report:** this `SUBMISSION.md`
- **Screenshots:** _add a dashboard screenshot before submitting_

## Ranked Opportunities

> Produced by **Agent 2** and written to `out/recommendations.csv` / `recommendations.json`.
> Run the pipeline, then paste the top rows here. Each carries an action, confidence, evidence,
> and risks.

| Rank | Opportunity | Recommended action | Final score | Confidence | Key evidence |
| --- | --- | --- | --- | --- | --- |
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |

## Evidence Trail

Every recommendation aggregates real `evidence_urls` from the underlying signals; every
intermediate observation is a row in `out/signals.csv` with its own `url` and `created_by_tool`.
Evidence comes from `web_search` (cited reporting / brand / marketplace pages),
`trends.google.com`, `reddit.com`, and GDELT article URLs. Recommendations never add sources that
aren't present in the sourced signals.

## Transferability (Swiss / DACH)

`swiss_dach_transferability` is an explicit scored dimension: signals are tagged with the market
they appear in, and Decision boosts opportunities seen in CH/DACH, with secondary credit for
EU/Nordics/UK proximity and outdoor/sustainability relevance. When no local evidence exists, the
weighting **raises** the transferability dimension and flags it as inferred rather than observed.

## Reusability

Three things retarget the system, none of which require code changes:

1. **Product focus / seeds** — `expand_seed_keywords()` is generic-first: it builds seeds from the
   customer's focus ("emerging X", "X new materials", "X rising brands", "X marketplace
   bestsellers", …) so any category works out of the box.
2. **Market geo** — `--market` (mapped to a Google Trends region).
3. **Community sources** — the subreddit / source list in `Source/Agents/scout_agent/tools.py`.

Grouping (`canonical_opportunity`), scoring dimensions, and dynamic weights are all category-
agnostic; outdoor-specific rules survive only as optional normalization on top. The same
architecture works for beauty, home, or any other vertical by repointing inputs.

## Known Limitations

- Live APIs can rate-limit on stage; the first good response from each Scout tool is cached under
  `data/cache/` (real fetched data, not synthetic) so demos replay deterministically.
- `signal_score` (Scout) and `final_score` (Decision) are transparent heuristics, not calibrated
  models. They are auditable — `recommendations.json` records the exact weights and adjustments.
- Coverage vs. Swiss retailers is reasoned from public info, not scraped from retailer catalogs;
  flagged `unknown` / inferred when unverifiable.
- Signal clustering uses a keyword-overlap fallback unless `sentence-transformers` + `scikit-learn`
  are installed (optional in `requirements.txt`).
- Recommendations are decision-support outputs and should be reviewed by a human buyer before acting.

## Architecture Notes

```
Customer query (chat or --query)
   └─▶ Agent 2 — Decision (orchestrator)  Source/Agents/decision_agent/
         parse_customer_query → generic seed keywords
              ├─▶ Agent 1 — Scout  ─────────┐  parallel fan-out (ThreadPoolExecutor)
              │     claude-opus-4-8 loop:    │  Source/Agents/scout_agent/
              │       web_search (cited URLs)│
              │       Google Trends / Reddit / GDELT
              │       score_emerging → emit_signal ─▶ out/signals.csv  (Signal Row contract)
              └─▶ Agent 3 — Profiler ───────┘  Source/Agents/agent_3.py
                    Claude → company_profile.json (infers strategic assortment gaps)
                          ↓ join ("the wait")
         build_recommendations:
           group_signals → canonical opportunities (generic-first)
           score_group → 8 buyer dimensions
           get_dynamic_weights(profile, request, rows) → normalized weights
           analytics.analyze_signals + adjust_final_score → transparent multiplier
                          ↓
         out/recommendations.csv  (Zenline contract — THE deliverable)
         out/recommendations.json (scores, weights_used, analytics, risks, next steps)
                          ↓
         Streamlit app  Source/App/customer_chat.py  (Profile · Signals · Recommendations)
```

**Eight scored dimensions** (each 0–100): `evidence_strength`, `cross_source_validation`,
`trend_momentum`, `swiss_dach_transferability`, `commercial_potential`,
`current_assortment_gap_fit`, `strategic_gap_fit`, `company_profile_fit`.

**Dynamic weighting** (`get_dynamic_weights`): starts from `BASE_WEIGHTS`, then nudges and
re-normalizes (sum = 1.0) based on — high/low innovation appetite, target gross margin, presence of
strategic focus/gaps, single-source evidence, missing CH/DACH evidence, missing URLs, and query
intent. Every adjustment is logged in `weight_adjustment_reasons`.

**Analytics layer** (`Source/Agents/decision_agent/analytics.py`, deterministic): signal
clustering/dedup, trend velocity (accelerating/decelerating), market saturation, anomaly detection,
geographic concentration, source quality, and diversity — applied as a final transparent multiplier
on `final_score`.

**`signal_score` scale:** `0.0–1.0`,
`emerging_score = clamp01( velocity × log1p(engagement) / 6 × event_lift )`
(see `Source/Agents/scout_agent/score.py`). Scout's `signal_score` feeds Decision mainly as
`trend_momentum`, **not** as the final ranking.
**`final_score`:** `0–100` business decision score. **`confidence`:** `high | medium | low`.
**Recommended actions:** Launch · Test · Buy · Contact supplier/brand · Reposition existing
assortment · Monitor · Ignore.
