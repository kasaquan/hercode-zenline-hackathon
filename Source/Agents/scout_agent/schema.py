"""Contract-exact row schemas + CSV writers.

Column order and names match docs/data-contract.md and examples/signals.csv
verbatim, so the jury can inspect and rerun our output.
"""
from __future__ import annotations

import csv
import datetime as _dt
from dataclasses import dataclass, field, asdict
from typing import List, Optional

TODAY = _dt.date.today().isoformat()

# Exact column orders from docs/data-contract.md
SIGNAL_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "signal_score",
    "confidence", "notes", "observed_at", "artifact_type", "artifact_uri",
    "created_by_tool",
]

RECOMMENDATION_COLUMNS = [
    "rank", "opportunity", "first_observed_market", "evidence_summary",
    "evidence_urls", "transferability", "coverage_status",
    "recommended_action", "confidence", "risks",
]


@dataclass
class SignalRow:
    source: str
    market: str
    keyword: str
    signal_name: str
    signal_type: str            # search | social | web | marketplace | competitor | api | manual
    url: str
    signal_score: float         # 0.0–1.0, scale defined in SUBMISSION.md
    confidence: str             # high | medium | low
    created_by_tool: str
    product_name: str = ""
    brand: str = ""
    price: str = ""
    rank: str = ""
    notes: str = ""
    observed_at: str = TODAY
    artifact_type: str = "csv"
    artifact_uri: str = "out/signals.csv"


@dataclass
class RecommendationRow:
    rank: int
    opportunity: str
    first_observed_market: str
    evidence_summary: str
    evidence_urls: List[str]            # joined with " | " on write
    transferability: str                # global -> Switzerland/DACH reasoning
    coverage_status: str                # covered | partially_covered | absent | unknown | not_relevant
    recommended_action: str             # stock | test | monitor (+ rationale)
    confidence: str                     # high | medium | low
    risks: str


def _write(path: str, columns: List[str], rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def write_signals(rows: List[SignalRow], path: str = "out/signals.csv") -> None:
    _write(path, SIGNAL_COLUMNS, [asdict(r) for r in rows])


def write_recommendations(rows: List[RecommendationRow], path: str = "out/recommendations.csv") -> None:
    out = []
    for r in rows:
        d = asdict(r)
        d["evidence_urls"] = " | ".join(r.evidence_urls)
        out.append(d)
    _write(path, RECOMMENDATION_COLUMNS, out)
