"""Agent A — Scout (sourcing).

Sources signals from the real world and returns them as **Signal Rows**
(docs/data-contract.md#signal-row). Agentic, not a pipeline: the model decides which
activities/keywords to probe, gathers real-evidence (web_search + Google Trends + Reddit +
GDELT), scores what it finds, and emits curated Signal Rows. It does NOT produce
recommendations — a downstream Buyer agent (Agent B) consumes out/signals.csv.

Run:
    python -m Source.Agents.scout_agent --market DACH --seeds "trail running, approach shoes, gravel bikepacking"
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import anthropic

from . import tools
from .schema import write_signals

MODEL = "claude-opus-4-8"

# Repo root (…/Source/Agents/scout_agent/scout.py -> parents[3]). Anchoring here
# means artifacts always land in <repo>/out regardless of the launch directory.
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "out"

# web_search is a Claude-hosted server tool — returns real, cited URLs directly.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}

SYSTEM = """You are Agent A, a demand-signal scout for a pan-European outdoor retailer that sells \
into Switzerland and the wider DACH region. You do NOT follow fashion influencers. You track \
changes in ACTIVITY, LOCATION, and COMMUNITY heat (climbing, ski touring, trail running, \
bikepacking, hiking), search momentum, marketplace/competitor moves, and global-event boosts, \
across markets (CH, DACH, US, Japan, Korea, Nordics, UK).

Your ONLY job is SOURCING: find real-world signals of emerging products, materials, and brands, \
and record each as a Signal Row via emit_signal. You do NOT rank, recommend, or decide what to \
buy — a downstream Buyer agent does that from your signals.

Hard rules:
- Every signal MUST trace to a REAL source URL from a tool result or web_search. Never invent sources.
- Tag `market` with where the signal actually appears (this lets the Buyer judge DACH transferability).
- Cover a DIVERSE mix of signal_type values (search, social, web, marketplace, competitor) and \
several activities — breadth beats repetition.
- Set signal_score (0-1) deliberately; use score_emerging to ground it.

Method (you choose the order and when you have enough):
1. Decide which activities/keywords/markets to investigate this round.
2. Use web_search for credible reporting, brand/marketplace pages, and DACH/Swiss context (cite URLs).
3. Use trend_momentum, community_heat, and event_signals to quantify and corroborate.
4. Use score_emerging to set a signal_score.
5. Call emit_signal once per signal worth a buyer's attention. Aim for 12-20 strong, varied signals.

When you have a solid, diverse signal set, write a 2-3 sentence handoff note for the Buyer agent and stop."""


def _kickoff(market: str, seeds: str) -> str:
    return (
        f"Primary market lens: {market} (Switzerland / DACH), but source globally and tag each "
        f"signal's market.\nSeed activities/keywords to start from (expand as you see fit): {seeds}.\n\n"
        "Source real-world signals, corroborate with real source URLs, and record each via "
        "emit_signal in the Signal Row contract shape. Prioritise breadth and evidence quality."
    )


def _load_env() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def run(market: str, seeds: str, max_steps: int = 16) -> None:
    _load_env()
    client = anthropic.Anthropic()
    tools.reset()

    all_tools = [WEB_SEARCH_TOOL] + tools.SOURCING_TOOLS
    messages = [{"role": "user", "content": _kickoff(market, seeds)}]
    trace = []

    for _step in range(max_steps):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            tools=all_tools,
            messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "high"},
        )

        for b in resp.content:
            if b.type == "thinking":
                if getattr(b, "thinking", ""):
                    trace.append({"kind": "thinking", "text": b.thinking})
            elif b.type == "text":
                trace.append({"kind": "text", "text": b.text})
                print(b.text)
            elif b.type == "tool_use":
                trace.append({"kind": "tool_use", "name": b.name, "input": b.input})
                print(f"  -> {b.name}({json.dumps(b.input)[:120]})")
            elif b.type == "server_tool_use":
                trace.append({"kind": "web_search", "input": b.input})
                print(f"  -> web_search({json.dumps(b.input)[:120]})")

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            break
        if resp.stop_reason == "pause_turn":
            continue  # server-tool loop limit — re-send to resume
        if resp.stop_reason == "tool_use":
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    out = tools.dispatch(b.name, b.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": json.dumps(out)[:6000],
                    })
            if results:
                messages.append({"role": "user", "content": results})
            else:
                break
        else:
            break

    _persist(trace)


def _persist(trace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    emitted = tools.get_emitted_signals()
    # Deliverable: the agent's curated signal rows. Fall back to raw auto-captures
    # if the agent emitted nothing (safety net — still real, sourced data).
    deliverable = emitted if emitted else tools.get_raw_signals()
    write_signals(deliverable, str(OUT_DIR / "signals.csv"))
    write_signals(tools.get_raw_signals(), str(OUT_DIR / "signals_raw.csv"))

    with open(OUT_DIR / "trace.json", "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)

    print(f"\nWrote {OUT_DIR}/signals.csv ({len(deliverable)} curated rows), "
          f"signals_raw.csv ({len(tools.get_raw_signals())} raw rows), trace.json")


def main() -> None:
    p = argparse.ArgumentParser(description="Agent A — outdoor demand-signal Scout")
    p.add_argument("--market", default="DACH")
    p.add_argument("--seeds", default="trail running, approach shoes, ski touring, "
                                       "gravel bikepacking, merino base layers")
    p.add_argument("--max-steps", type=int, default=16)
    args = p.parse_args()
    run(args.market, args.seeds, args.max_steps)


if __name__ == "__main__":
    main()
