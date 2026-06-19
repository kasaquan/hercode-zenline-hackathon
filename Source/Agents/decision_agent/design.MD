# Decision Agent (Agent 2 — Buyer Orchestrator)

The customer-facing decision layer. Parses a retailer request, dispatches seed keywords to Agent 1 and
company context to Agent 3, then combines both outputs into ranked assortment recommendations in the
**Zenline Recommendation Row** contract (`docs/data-contract.md`). Deterministic scoring — no live
browsing — so results are reproducible and auditable.

> **One-line summary**
> Agent 1 finds signals. Agent 3 explains the company. Agent 2 decides what the company should do.

---

## Role in the pipeline

```
Customer query
  └─▶ Agent 2: parse_customer_query
        ├─▶ Agent 1 (Scout)        ─┐  parallel fan-out
        └─▶ Agent 3 (Profiler)     ─┘  (independent, both API-bound)
              ↓ join (the "wait")
        Agent 2: build_recommendations
              ↓
        out/recommendations.csv   ← Zenline contract (jury-facing)
        out/recommendations.json  ← richer scoring + debug output
```

Scout and Profiler don't depend on each other, so `pipeline.py` runs them concurrently
on two threads and joins before scoring. The file artifacts (`signals.csv`,
`company_profile.json`) are still written for the dashboard/jury, but Decision receives
Scout/Profiler output **in-memory** so it never re-parses its own inputs. Orchestration is
deterministic (a fixed fan-out → join → score), not an agent deciding when to call whom.

**Key scoring distinction**

| Score | Owner | Range | Meaning |
|---|---|---|---|
| `signal_score` | Agent 1 | 0.0–1.0 | Signal-level emerging strength |
| `final_score` | Agent 2 | 0–100 | Opportunity-level business decision score |

Agent 2 uses `signal_score` as a component of `trend_momentum` only — it is **not** the final ranking.

---

## Layout

```
decision_agent/
├── pipeline.py     # orchestrator: parse → fan-out Scout+Profiler (parallel) → join → score
├── decision.py     # scoring core: grouping, 8-dimension scoring, action logic, CSV/JSON writers
├── __main__.py     # `python -m Source.Agents.decision_agent` → runs the orchestrator
├── design.MD       # this file
└── design.txt      # original build notes (implementation spec)
```

Reuses the shared contract from `../scout_agent/schema.py` (`RecommendationRow`,
`write_recommendations`) rather than redefining it.

---

## Inputs

### Input 1 — Agent 1 output (`out/signals.csv`)

Fields consumed from the `SignalRow` contract:

| Field | Used for |
|---|---|
| `signal_score` | `trend_momentum` sub-score |
| `signal_type` | Cross-source validation diversity |
| `market` | Swiss/DACH transferability |
| `source` | Source diversity count |
| `url` | `evidence_urls` in output |
| `confidence` | Evidence strength weighting |
| `signal_name`, `keyword`, `product_name`, `brand`, `notes` | Opportunity grouping & text matching |

### Input 2 — Agent 3 output (`out/company_profile.json`)

Key fields consumed:

```jsonc
{
  "company_name": "string",
  "active_markets": ["CH", "AT", "DE"],
  "positioning": "budget | mid-range | premium | niche",
  "target_price_band": "economy (<100) | mid (100-300) | premium (300+) | mixed",
  "customer_segments": ["ultralight hikers", "climbers", ...],
  "current_product_categories": ["shells", "packs", "boots"],
  "current_assortment_gaps": "string",
  "target_gross_margin": "low (15-25%) | medium (25-40%) | high (40%+)",
  "innovation_appetite": "low | medium | high",
  "supply_chain_constraints": "string",
  "strategic_expansion_focus": "string",
  "strategic_assortment_gaps": "string",
  "confidence_by_field": { "field_name": "high | medium | low" }
}
```

If `out/company_profile.json` is absent, a default mid-range Swiss/DACH outdoor retailer profile is used.

---

## Scoring model

Each signal group is scored across eight dimensions that combine into `final_score` (0–100):

| Dimension | Weight | Source |
|---|---|---|
| Evidence strength | 18% | Signal scores, URL coverage, confidence |
| Cross-source validation | 12% | Diversity of signal types, markets, sources |
| Trend momentum | 12% | Agent 1 `signal_score` (avg + max) |
| Swiss/DACH transferability | 16% | Market proximity, outdoor use-case fit, sustainability relevance |
| Commercial potential | 10% | Competitor/marketplace signals, price data, brand mentions |
| Current assortment gap fit | 10% | Keyword overlap with `current_assortment_gaps` |
| Strategic gap fit | 12% | Keyword overlap with `strategic_expansion_focus` / `strategic_assortment_gaps` |
| Company profile fit | 10% | Positioning, price band, customer segments, innovation appetite, margin |

### Recommended action decision tree

```
evidence_strength < 45  OR  cross_source < 35  →  Monitor
company_profile_fit < 45                         →  Monitor
strategic_fit ≥ 75  AND  final ≥ 65             →  Test / Contact supplier
sustainability / PFAS signals  AND  final ≥ 82  →  Launch
final ≥ 84  AND  evidence ≥ 75  AND  transfer ≥ 75  AND  company_fit ≥ 70  →  Launch
final ≥ 68                                       →  Test
final ≥ 55                                       →  Monitor
otherwise                                        →  Ignore
```

Valid actions: `Launch`, `Test`, `Buy`, `Contact supplier/brand`, `Monitor`, `Reposition existing assortment`, `Ignore`

---

## Outputs

### Output 1 — `out/recommendations.csv` (Zenline contract)

| Field | Description |
|---|---|
| `rank` | Final ranking by `final_score` |
| `opportunity` | Canonical opportunity name |
| `first_observed_market` | Market with highest signal score |
| `evidence_summary` | Human-readable signal summary |
| `evidence_urls` | Up to 8 source URLs |
| `transferability` | Swiss/DACH transferability text + score |
| `coverage_status` | `absent` / `covered` / `partially_covered` / `unknown` |
| `recommended_action` | Action + next step text |
| `confidence` | `high` / `medium-high` / `medium` / `medium-low` / `low` |
| `risks` | Business risks + missing evidence list |

### Output 2 — `out/recommendations.json` (richer debug/dashboard)

Extends each row with:

```jsonc
{
  "scores": { "evidence_strength": 78.2, "final_score": 71.4, ... },
  "opportunity_type": ["product_type", "material", "feature"],
  "signal_markets": ["CH", "DACH"],
  "missing_evidence": ["Local competitor or search evidence"],
  "next_step": "Run a small test capsule...",
  "company_alignment_summary": "Current gap fit: ... Strategic fit: ...",
  "profile_fields_used": ["positioning", "target_price_band", ...],
  "source_count": 3,
  "signal_count": 7,
  "deduplication_note": "Grouped 7 signal row(s) under canonical opportunity: ..."
}
```

Also includes `methodology_note`, `known_limitations`, and `input_summary` at the top level.

---

## Run

From the **repo root** (all outputs land in `<repo>/out/`). Requires `ANTHROPIC_API_KEY`
in `.env` for the live Scout/Profiler calls.

### Orchestrated run (recommended) — one command, parallel Scout + Profiler

```bash
python -m Source.Agents.decision_agent \
  --query "Decathlon CH is looking for decision support on winter jackets" \
  --market DACH \
  --company https://www.decathlon.ch \
  --notes "Premium positioning, 12 CH stores, high innovation appetite"
# → out/signals.csv, out/company_profile.json,
#   out/recommendations.csv, out/recommendations.json
```

| Flag | Default | Description |
|---|---|---|
| `--query` | *required* | Customer query string |
| `--market` | `DACH` | Target market lens |
| `--company` | `""` | Company website URL for Agent 3 |
| `--pdf` | `None` | Path to a strategy-PDF text file for Agent 3 |
| `--notes` | `None` | Freeform company notes for Agent 3 |
| `--max-steps` | `16` | Scout agent step budget |

### Standalone scoring — re-score existing artifacts (no Scout/Profiler rerun)

Useful for tuning the scoring without paying for live sourcing:

```bash
python -m Source.Agents.decision_agent.decision \
  --query "Decathlon CH is looking for decision support on winter jackets" \
  --market DACH \
  --signals out/signals.csv \
  --profile out/company_profile.json
```

| Flag | Default | Description |
|---|---|---|
| `--query` | `""` | Customer query string |
| `--market` | `DACH` | Target market lens |
| `--signals` | `out/signals.csv` | Agent 1 output path |
| `--profile` | `out/company_profile.json` | Agent 3 output path |
| `--out-csv` | `out/recommendations.csv` | Zenline CSV output |
| `--out-json` | `out/recommendations.json` | Rich JSON output |
| `--init-only` | `false` | Only write the request file, skip scoring |

---

## Orchestration (`pipeline.py`)

`run_pipeline()` is the single in-process entry point the dashboard can also import:

```python
from Source.Agents.decision_agent.pipeline import run_pipeline

result = run_pipeline(
    query="Decathlon CH is looking for decision support on winter jackets",
    market="DACH",
    company_link="https://www.decathlon.ch",
    user_notes="Premium positioning, 12 CH stores",
)  # -> rich recommendations dict (same shape as out/recommendations.json)
```

Flow:

1. `parse_customer_query()` → derives `product_focus` + Agent 1 seed keywords.
2. `ThreadPoolExecutor(max_workers=2)` submits `scout.run()` and `extract_company_profile()`
   concurrently — the fan-out.
3. `.result()` on both futures is the join (the "wait" — Decision can't score until both land).
4. `build_recommendations()` scores in-memory; outputs are written for the dashboard/jury.

Grouping note: each signal is classified by its **own** content. The customer's
`product_focus` steers Scout's seeds upstream — it is deliberately *not* mixed into
Decision's grouping, otherwise the query keyword would relabel every unrelated signal.

---

## Optional LLM refinement

`prompts/agent2_refinement_prompt.txt` is an optional post-processing step where a Claude model
polishes recommendation wording after the deterministic scoring pass. Rules:

- No browsing, no invented URLs, no invented evidence
- Preserves all `evidence_urls` from the deterministic pass
- Returns valid JSON only
- Conservative: weak or single-source signals stay `Monitor` or `Test`

---

## Known limitations

- Coverage status is inferred without full internal assortment data unless Agent 3 provides detailed categories/gaps.
- Commercial potential is estimated from public signals, not retailer sales or margin data.
- Opportunity grouping is deterministic keyword-matching; embeddings would improve recall.
- All recommendations are decision-support output and must be reviewed by a human buyer before acting.
