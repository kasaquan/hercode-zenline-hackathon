# Scout Agent (sourcing)

Sources real-world demand signals for a Swiss / DACH outdoor retailer and records each as a
**Signal Row** (`docs/data-contract.md#signal-row`). Agentic, not a pipeline: a `claude-opus-4-8`
tool-calling loop decides which activities/keywords/markets to probe, gathers real evidence
(web_search + Google Trends + Reddit + GDELT), scores it, and emits curated Signal Rows. It does
**not** rank or recommend — the downstream Buyer/Profiler agents consume `out/signals.csv`.

## Layout

```
scout_agent/
├── scout.py       # the agent loop (run / run_iter / CLI)
├── tools.py       # evidence tools: trend_momentum, community_heat, event_signals, score_emerging, emit_signal
├── schema.py      # Signal/Recommendation contract rows + CSV writers
├── score.py       # signal_score math (emerging_score)
└── dashboard.py   # Streamlit view of sourced signals + reasoning trace
```

## Run

From the **repo root** (paths are anchored to the repo root, so artifacts always land in `<repo>/out`):

```bash
# 1. one-time setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (gitignored — never commit)

# 2. run the agent
python -m Source.Agents.scout_agent --market DACH --seeds "trail running, ski touring, merino base layers"

# 3. view the result (separate terminal; leave it running)
streamlit run Source/Agents/scout_agent/dashboard.py
```

Outputs (at `<repo>/out`): `signals.csv` (deliverable), `signals_raw.csv` (raw provenance),
`trace.json` (reasoning trace). First good API responses are cached under `<repo>/data/cache/`.

Flags: `--market` (DACH|CH|US|UK), `--seeds` (comma-separated), `--max-steps` (default 16).
