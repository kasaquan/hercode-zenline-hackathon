"""Deterministic orchestrator for the three-agent pipeline.

Agent 2 (Decision) parses the customer request, then fans out to Agent 1 (Scout) and
Agent 3 (Profiler) **in parallel** — they are independent and both API-bound — joins
their results, and scores them into ranked recommendations.

    Customer query
      └─▶ parse_customer_query                     (Agent 2)
            ├─▶ scout.run(seeds)        ─┐ parallel  (Agent 1)
            └─▶ extract_company_profile ─┘ fan-out   (Agent 3)
                  ↓ join (the "wait")
            build_recommendations                   (Agent 2)
                  ↓
            out/recommendations.csv + out/recommendations.json

The file artifacts (signals.csv, company_profile.json, recommendations.*) are still
written for the dashboard and jury, but Decision receives Scout/Profiler output
in-memory so it never has to re-parse its own inputs.

Run:
    python -m Source.Agents.decision_agent.pipeline \
      --query "Decathlon CH is looking for decision support on winter jackets" \
      --market DACH --company https://www.decathlon.ch --notes "Premium, 12 CH stores"
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

from .. import agent_3
from ..scout_agent import scout
from ..scout_agent.schema import write_recommendations
from . import decision

# …/Source/Agents/decision_agent/pipeline.py -> parents[3] == repo root.
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "out"


def run_pipeline(
    query: str,
    market: str = "DACH",
    company_link: str = "",
    pdf_content: Optional[str] = None,
    user_notes: Optional[str] = None,
    max_steps: int = 16,
    write: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run Scout + Profiler concurrently, then score with Decision.

    Returns the rich recommendations dict (same shape as out/recommendations.json).
    """
    request = decision.parse_customer_query(query, market)
    seeds = ", ".join(request["agent1_seed_keywords"])

    if verbose:
        print(f"[pipeline] product focus: {request['product_focus']}")
        print(f"[pipeline] dispatching Scout + Profiler in parallel…")

    # Fan-out: Scout and Profiler don't depend on each other and are both API-bound,
    # so run them on two threads and join before Decision scores.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_signals = pool.submit(scout.run, market, seeds, max_steps)
        f_profile = pool.submit(
            agent_3.extract_company_profile, company_link, pdf_content, user_notes, verbose
        )
        signal_rows = f_signals.result()   # join — the "wait" the design called for
        profile_raw = f_profile.result()

    signals = decision.signals_from_rows(signal_rows)
    profile = decision.merge_profile(profile_raw)

    if verbose:
        print(f"[pipeline] Scout returned {len(signals)} signal row(s); "
              f"profiling company: {profile.get('company_name', 'unknown')}")

    result = decision.build_recommendations(signals, profile, request)

    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        decision.write_request_file(request, str(OUT_DIR / "agent2_request.json"))
        with open(OUT_DIR / "company_profile.json", "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        decision.write_json(result, str(OUT_DIR / "recommendations.json"))
        write_recommendations(
            decision.to_recommendation_rows(result), str(OUT_DIR / "recommendations.csv")
        )
        if verbose:
            print(f"[pipeline] wrote {OUT_DIR}/recommendations.csv + recommendations.json")

    return result


def main() -> None:
    p = argparse.ArgumentParser(
        description="Agent 2 pipeline orchestrator — Scout + Profiler (parallel) → Decision"
    )
    p.add_argument("--query", required=True,
                   help="Customer query, e.g. 'Decathlon CH needs decision support on winter jackets'")
    p.add_argument("--market", default="DACH", help="Target market lens, e.g. DACH or CH")
    p.add_argument("--company", default="", help="Company website URL for Agent 3")
    p.add_argument("--pdf", default=None, help="Path to a strategy PDF text file for Agent 3")
    p.add_argument("--notes", default=None, help="Freeform company notes for Agent 3")
    p.add_argument("--max-steps", type=int, default=16, help="Scout agent step budget")
    args = p.parse_args()

    pdf_content = None
    if args.pdf and os.path.exists(args.pdf):
        pdf_content = Path(args.pdf).read_text(encoding="utf-8")

    result = run_pipeline(
        query=args.query,
        market=args.market,
        company_link=args.company,
        pdf_content=pdf_content,
        user_notes=args.notes,
        max_steps=args.max_steps,
        verbose=True,
    )

    recs = result["recommendations"]
    print(f"\nTop recommendations ({len(recs)} total):")
    for rec in recs[:5]:
        print(f"  #{rec['rank']:>2}  [{rec['scores']['final_score']:>5}/100] "
              f"{rec['recommended_action']:<28} {rec['opportunity']}")


if __name__ == "__main__":
    main()
