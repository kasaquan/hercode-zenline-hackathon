"""Agent 2 — Main Decision Agent / Buyer Orchestrator (scoring core).

Consumes Agent 1 Signal Rows (out/signals.csv) and the Agent 3 company profile
(out/company_profile.json), groups related signals into canonical opportunities,
scores each on eight buyer-level dimensions, and emits Zenline Recommendation Rows.

Deterministic by design — no live browsing — so results are reproducible and auditable.
Agent 1 `signal_score` (0.0-1.0, signal-level strength) feeds `trend_momentum` only;
it is NOT the final ranking. Agent 2 `final_score` (0-100) is the business decision score.

CLI (re-score existing artifacts):
    python -m Source.Agents.decision_agent.decision \
      --query "Decathlon CH needs decision support on winter jackets" \
      --signals out/signals.csv --profile out/company_profile.json

For the full Scout + Profiler + Decision run, see pipeline.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Tuple

from ..scout_agent.schema import RecommendationRow, write_recommendations
from . import analytics


DEFAULT_PROFILE = {
    "company_name": "Default Swiss/DACH Outdoor Retailer",
    "website": "",
    "active_markets": ["CH", "DE", "AT"],
    "primary_cantons": [],
    "positioning": "mid-range",
    "target_price_band": "mid (100-300)",
    "customer_segments": ["hikers", "trail runners", "ski tourers", "urban outdoor commuters"],
    "current_product_categories": [],
    "current_assortment_gaps": "",
    "store_count": "unknown",
    "distribution_model": "hybrid",
    "target_gross_margin": "medium (25-40%)",
    "innovation_appetite": "medium",
    "strategic_expansion_focus": "",
    "strategic_timeline": "",
    "strategic_rationale": "",
    "strategic_assortment_gaps": "",
    "data_sources": [],
    "confidence_by_field": {},
    "extra": "",
}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9+\-]+", _norm(s)))


def keyword_overlap_score(a: str, b: str) -> float:
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = len(a_tokens & b_tokens)
    denom = max(1, min(len(a_tokens), len(b_tokens)))
    return min(100.0, 100.0 * overlap / denom)


# Agent 3 fills unknown fields with filler prose ("Not available - no strategy PDF
# provided", "Cannot infer ...") rather than leaving them blank. Treat that filler as
# absent so a profile that honestly says "I don't know" scores neutral, not worse than
# one that says nothing — and so the noise never pollutes keyword-overlap matching.
_PLACEHOLDER_MARKERS = (
    "not available",
    "cannot infer",
    "not provided",
    "no strategy",
    "no executive strategy",
    "no strategy document",
    "no data",
    "unknown",
    "n/a",
)


def _is_placeholder(value: Any) -> bool:
    v = _norm(value)
    if not v or v in {"none", "nan", "na"}:
        return True
    return any(marker in v for marker in _PLACEHOLDER_MARKERS)


def _profile_text(profile: Dict[str, Any], *fields: str) -> str:
    parts = []
    for field in fields:
        value = profile.get(field)
        if isinstance(value, list):
            parts.extend(str(x) for x in value if not _is_placeholder(x))
        elif isinstance(value, dict):
            parts.extend(str(k) + " " + str(v) for k, v in value.items())
        elif value and not _is_placeholder(value):
            parts.append(str(value))
    return _norm(" ".join(parts))


def _opportunity_text(opportunity: str, rows: List[Dict[str, Any]]) -> str:
    return _norm(
        " ".join(
            [
                opportunity,
                " ".join(r.get("signal_name", "") for r in rows),
                " ".join(r.get("keyword", "") for r in rows),
                " ".join(r.get("product_name", "") for r in rows),
                " ".join(r.get("brand", "") for r in rows),
                " ".join(r.get("notes", "") for r in rows),
            ]
        )
    )


def _clean_signal_dicts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop empty rows and coerce signal_score to float. Shared by file + in-memory paths."""
    cleaned = []
    for r in rows:
        if not r.get("signal_name") and not r.get("keyword"):
            continue
        r = dict(r)
        r["signal_score"] = _safe_float(r.get("signal_score"), 0.0)
        cleaned.append(r)
    return cleaned


def read_signals(path: str) -> List[Dict[str, Any]]:
    """Load Agent 1 Signal Rows from a CSV file (CLI path)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing Agent 1 signal file: {path}")

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    return _clean_signal_dicts(rows)


def signals_from_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    """Normalize in-memory Agent 1 output (SignalRow dataclasses or dicts) for scoring."""
    dicts = [asdict(r) if is_dataclass(r) else dict(r) for r in rows]
    return _clean_signal_dicts(dicts)


def merge_profile(data: Dict[str, Any] | None) -> Dict[str, Any]:
    """Merge an Agent 3 profile dict over the defaults, ignoring error payloads."""
    profile = DEFAULT_PROFILE.copy()
    if data and "error" not in data:
        profile.update(data)
    return profile


def load_profile(path: str | None) -> Dict[str, Any]:
    """Load the Agent 3 company profile from JSON, falling back to defaults (CLI path)."""
    if not path or not os.path.exists(path):
        return DEFAULT_PROFILE.copy()

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return merge_profile(data)


def expand_seed_keywords(product_focus: str) -> List[str]:
    # Generic-first: the seed set is driven by the customer's product_focus itself,
    # so the agent works for ANY category (winter jackets, cookware, e-bikes, …),
    # not just the hard-coded outdoor verticals. Category-specific seeds below are
    # optional enrichment layered on top of these generic, always-present seeds.
    focus = (product_focus or "").strip() or "outdoor products"
    t = _norm(focus)

    seeds = [
        focus,
        f"emerging {focus}",
        f"{focus} trends",
        f"{focus} new materials",
        f"{focus} rising brands",
        f"{focus} competitor assortment",
        f"{focus} marketplace bestsellers",
        f"{focus} Switzerland DACH",
        f"sustainable {focus}",
        f"premium {focus}",
        f"lightweight {focus}",
        f"repairable {focus}",
    ]

    # Optional category-specific additions (only when the focus clearly matches a
    # known outdoor vertical). These supplement — they never replace — the generic
    # seeds above.
    if any(k in t for k in ["winter jacket", "winter jackets", "insulated jacket", "ski jacket"]):
        seeds += [
            "winter jackets",
            "insulated jackets",
            "synthetic insulation",
            "down alternative jacket",
            "waterproof winter shell",
            "ski touring jacket",
            "breathable winter jacket",
            "PFAS-free winter shell",
        ]
    elif any(k in t for k in ["rain", "shell", "waterproof"]):
        seeds += [
            "PFAS-free rain shell",
            "PFC-free waterproof jacket",
            "lightweight rain jacket",
            "waterproof breathable shell",
            "trail-to-city rain shell",
        ]
    elif any(k in t for k in ["ultralight", "backpacking"]):
        seeds += [
            "ultralight backpacking",
            "ultralight packs under 500g",
            "modular backpacking kit",
            "lightweight tents",
            "sustainable ultralight gear",
        ]
    elif any(k in t for k in ["trail running", "trail"]):
        seeds += [
            "trail running vest",
            "hydration vest",
            "ultralight running pack",
            "technical trail apparel",
        ]
    elif any(k in t for k in ["climbing", "bouldering"]):
        seeds += [
            "bouldering accessories",
            "climbing chalk bag",
            "approach shoes",
            "climbing gym apparel",
        ]

    seen = set()
    out = []
    for s in seeds:
        sn = _norm(s)
        if sn not in seen:
            seen.add(sn)
            out.append(s)
    return out


def parse_customer_query(query: str, market: str = "DACH") -> Dict[str, Any]:
    q = query or ""
    product_focus = ""
    company_name = ""

    patterns = [
        r"(.+?) is looking for decision support on (.+)",
        r"(.+?) wants decision support on (.+)",
        r"(.+?) needs decision support on (.+)",
        r"(.+?) needs help with (.+)",
        r"decision support on (.+)",
        r"support on (.+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, q, flags=re.IGNORECASE)
        if m:
            if len(m.groups()) == 2:
                company_name = m.group(1).strip()
                product_focus = m.group(2).strip()
            else:
                product_focus = m.group(1).strip()
            break

    if not product_focus:
        product_focus = q.strip() or "outdoor products"

    return {
        "market": market,
        "category": "outdoor retail",
        "company_name": company_name or "unknown company",
        "product_focus": product_focus,
        "agent1_seed_keywords": expand_seed_keywords(product_focus),
        "agent1_expected_output": "out/signals.csv",
        "agent3_expected_output": "out/company_profile.json",
        "original_query": query,
    }


def write_request_file(request: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(request, f, indent=2, ensure_ascii=False)


_GENERIC_BRAND_NAMES = {"", "global", "none", "nan", "unknown", "n/a", "various"}


def infer_opportunity_types(row: Dict[str, Any]) -> List[str]:
    """Infer the buyer-relevant facets a signal touches, from the row's OWN content.

    Generic across categories — returns any of: product_type, material, feature,
    brand, supplier, price_band_gap, usage_occasion, merchandising_idea,
    service_model. Always returns at least ["product_type"].
    """
    text = _norm(
        " ".join(
            [
                row.get("signal_name", ""),
                row.get("keyword", ""),
                row.get("product_name", ""),
                row.get("brand", ""),
                row.get("signal_type", ""),
                row.get("notes", ""),
            ]
        )
    )

    types: List[str] = []

    def add(t: str) -> None:
        if t not in types:
            types.append(t)

    if (row.get("product_name") or "").strip() or any(
        k in text for k in ["jacket", "shoe", "boot", "pack", "vest", "tent", "shirt", "apparel", "gear", "product", "kit", "bag"]
    ):
        add("product_type")
    if any(k in text for k in ["material", "fabric", "insulation", "down", "merino", "recycled", "pfas", "pfc", "fluorocarbon", "membrane", "gore", "nylon", "polyester"]):
        add("material")
    if any(k in text for k in ["waterproof", "breathable", "lightweight", "ultralight", "uv", "upf", "durable", "repairable", "insulated", "windproof", "feature"]):
        add("feature")

    brand = _norm(row.get("brand"))
    if brand and brand not in _GENERIC_BRAND_NAMES:
        add("brand")
    if any(k in text for k in ["supplier", "manufacturer", "oem", "wholesale", "distributor", "vendor"]):
        add("supplier")
    if any(k in text for k in ["price", "margin", "premium", "budget", "entry-level", "mid-range", "price band", "price-band", "under ", "gap"]):
        add("price_band_gap")
    if any(k in text for k in ["commuter", "trail-to-city", "urban", "occasion", "gym", "touring", "hiking", "running", "season", "winter", "summer", "everyday"]):
        add("usage_occasion")
    if any(k in text for k in ["bestseller", "assortment", "merchandis", "bundle", "display", "collection", "capsule", "trend", "rank"]):
        add("merchandising_idea")
    if any(k in text for k in ["repair", "rental", "resale", "warranty", "subscription", "service", "take-back", "secondhand", "circular"]):
        add("service_model")

    signal_type = _norm(row.get("signal_type"))
    if "competitor" in signal_type or "marketplace" in signal_type:
        add("merchandising_idea")
    if "brand" in signal_type:
        add("brand")

    if not types:
        types = ["product_type"]
    return types


def _normalize_outdoor_label(text: str) -> Tuple[str, List[str]] | None:
    """Optional normalization: collapse near-duplicate labels into a shared
    canonical outdoor bucket. Returns None when no known pattern matches, so it
    only ever *refines* the generic grouping below — it is not the main logic."""
    t = _norm(text)

    if any(k in t for k in ["winter jacket", "insulated", "down alternative", "ski jacket", "winter shell"]):
        return "Winter jacket and insulation opportunity", ["product_type", "material", "feature"]
    if any(k in t for k in ["pfas", "pfc", "fluorocarbon"]) and any(k in t for k in ["rain", "shell", "waterproof", "jacket"]):
        return "PFAS-free lightweight rain shells", ["material", "feature", "product_type"]
    if any(k in t for k in ["uv", "upf", "sun hoodie", "sun shirt", "sun-protective", "sun protective"]):
        return "UV-protective hiking shirts and sun hoodies", ["product_type", "feature", "usage_occasion"]
    if any(k in t for k in ["ultralight", "backpacking", "lightweight tent", "modular kit"]):
        return "Ultralight backpacking and modular kit systems", ["product_type", "feature", "usage_occasion"]
    if any(k in t for k in ["commuter", "trail-to-city", "city", "urban outdoor", "gorpcore"]):
        return "Trail-to-city commuter shell", ["usage_occasion", "product_type", "merchandising_idea"]
    if any(k in t for k in ["climbing", "bouldering", "chalk", "climbing gym"]):
        return "Climbing gym-driven bouldering accessories", ["usage_occasion", "product_type"]
    if any(k in t for k in ["hydration vest", "running vest", "trail vest"]):
        return "Ultralight hydration and trail running vests", ["product_type", "feature"]
    if any(k in t for k in ["repair", "repairable", "durability", "durable"]):
        return "Repairable durable outdoor gear", ["feature", "service_model", "merchandising_idea"]
    if any(k in t for k in ["merino", "base layer", "baselayer"]):
        return "Merino and technical base layers", ["material", "product_type"]
    return None


def canonical_opportunity(row: Dict[str, Any], request: Dict[str, Any]) -> Tuple[str, List[str]]:
    # Generic-first grouping. The canonical key is taken from the signal's OWN
    # content in priority order — Agent 1 signal_name, then product_name, then a
    # brand/supplier label when the signal is brand-led, then keyword — so the
    # agent groups ANY category, not just hard-coded outdoor verticals. The
    # customer's product_focus is deliberately NOT mixed in here (that would make
    # the query keyword dominate and relabel unrelated signals); it steers Scout's
    # seeds upstream instead.
    types = infer_opportunity_types(row)

    signal_name = (row.get("signal_name") or "").strip()
    product_name = (row.get("product_name") or "").strip()
    brand = (row.get("brand") or "").strip()
    keyword = (row.get("keyword") or "").strip()
    brand_led = bool(brand) and _norm(brand) not in _GENERIC_BRAND_NAMES and not signal_name and not product_name

    if signal_name:
        label = signal_name
    elif product_name:
        label = product_name
    elif brand_led:
        label = f"Watch or contact emerging brand/supplier: {brand}"
        for t in ("brand", "supplier"):
            if t not in types:
                types.append(t)
    elif keyword:
        label = keyword
    else:
        label = "Unspecified opportunity"

    # Optional outdoor normalization, applied over the row's own text. When a known
    # vertical matches, collapse to its canonical bucket and merge in its facets;
    # otherwise keep the generic label above.
    row_text = " ".join([signal_name, keyword, product_name, brand, row.get("notes", "")])
    normalized = _normalize_outdoor_label(row_text)
    if normalized:
        label, extra_types = normalized
        for t in extra_types:
            if t not in types:
                types.append(t)

    return label.strip()[:120], types


def group_signals(signals: List[Dict[str, Any]], request: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}

    for row in signals:
        opportunity, types = canonical_opportunity(row, request)
        if opportunity not in groups:
            groups[opportunity] = {
                "opportunity": opportunity,
                "opportunity_type": set(types),
                "signals": [],
            }
        groups[opportunity]["signals"].append(row)
        groups[opportunity]["opportunity_type"].update(types)

    return groups


def confidence_to_num(confidence: str) -> float:
    c = _norm(confidence)
    if c == "high":
        return 1.0
    if c == "medium":
        return 0.65
    if c == "low":
        return 0.35
    return 0.5


def unique_nonempty(rows: List[Dict[str, Any]], field: str) -> List[str]:
    seen = []
    for r in rows:
        value = (r.get(field) or "").strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def evidence_urls(rows: List[Dict[str, Any]]) -> List[str]:
    return unique_nonempty(rows, "url")[:8]


def infer_first_observed_market(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "unknown"
    best = max(rows, key=lambda r: _safe_float(r.get("signal_score"), 0.0))
    return best.get("market") or "unknown"


def current_assortment_gap_fit(opportunity: str, rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> Tuple[float, str]:
    opp_text = _opportunity_text(opportunity, rows)
    current_categories = _profile_text(profile, "current_product_categories")
    current_gaps = _profile_text(profile, "current_assortment_gaps")

    gap_overlap = keyword_overlap_score(opp_text, current_gaps)
    category_overlap = keyword_overlap_score(opp_text, current_categories)

    if gap_overlap >= 25:
        return min(100.0, 70 + gap_overlap * 0.3), "Matches current_assortment_gaps from Agent 3."
    if category_overlap >= 25:
        return 50.0, "Overlaps with current_product_categories; may need repositioning or SKU-level gap check."
    return 60.0, "Not clearly covered by current_product_categories; possible assortment gap."


def strategic_gap_fit(opportunity: str, rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> Tuple[float, str]:
    opp_text = _opportunity_text(opportunity, rows)
    strategic_text = _profile_text(
        profile,
        "strategic_expansion_focus",
        "strategic_assortment_gaps",
        "strategic_rationale",
    )

    if not strategic_text:
        return 50.0, "No strategic expansion information provided."

    overlap = keyword_overlap_score(opp_text, strategic_text)

    if overlap >= 35:
        return min(100.0, 75 + overlap * 0.25), "Strong match with strategic_expansion_focus or strategic_assortment_gaps."
    if overlap >= 15:
        return min(85.0, 60 + overlap * 0.3), "Partial alignment with strategic direction."
    return 40.0, "No clear match with stated strategic expansion focus."


def company_profile_fit_score(opportunity: str, rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> Tuple[float, str]:
    opp_text = _opportunity_text(opportunity, rows)

    positioning = _norm(profile.get("positioning", ""))
    price_band = _norm(profile.get("target_price_band", ""))
    customer_segments = _profile_text(profile, "customer_segments")
    innovation = _norm(profile.get("innovation_appetite", "medium"))
    margin = _norm(profile.get("target_gross_margin", "medium"))

    score = 55.0
    reasons = []

    if keyword_overlap_score(opp_text, customer_segments) >= 20:
        score += 12
        reasons.append("matches target customer segments")

    if positioning in ["premium", "niche"]:
        if any(k in opp_text for k in ["technical", "ultralight", "pfas", "repair", "durable", "modular", "winter", "shell"]):
            score += 10
            reasons.append("fits premium/niche technical positioning")
    elif positioning in ["budget", "mid-range"]:
        if any(k in opp_text for k in ["accessory", "shirt", "base layer", "mid", "entry"]):
            score += 6
            reasons.append("fits budget/mid-range accessible assortment")

    if price_band:
        if "premium" in price_band and any(k in opp_text for k in ["premium", "technical", "shell", "winter", "ultralight"]):
            score += 8
            reasons.append("plausible premium price-band fit")
        elif "mid" in price_band and any(k in opp_text for k in ["shirt", "jacket", "pack", "shell", "base layer"]):
            score += 8
            reasons.append("plausible mid price-band fit")
        elif "mixed" in price_band:
            score += 5
            reasons.append("mixed price band allows flexibility")

    if innovation == "high":
        score += 8
        reasons.append("high innovation appetite supports testing emerging opportunities")
    elif innovation == "low":
        score -= 8
        reasons.append("low innovation appetite suggests conservative action")

    if "high" in margin:
        if any(k in opp_text for k in ["premium", "technical", "supplier", "brand", "modular", "ultralight", "pfas", "repair"]):
            score += 8
            reasons.append("could support high-margin differentiation")
        else:
            score -= 4
            reasons.append("margin differentiation is not obvious")

    score = max(0.0, min(100.0, score))
    if not reasons:
        reasons.append("generic fit based on available company profile")

    return score, "; ".join(reasons)


# Baseline contribution of each buyer dimension to final_score. These are the
# original fixed coefficients; get_dynamic_weights() nudges them per request and
# re-normalizes, so the score adapts to query intent, the Agent 3 profile, and the
# quality of the Agent 1 evidence instead of being one-size-fits-all.
BASE_WEIGHTS: Dict[str, float] = {
    "evidence_strength": 0.18,
    "cross_source_validation": 0.12,
    "trend_momentum": 0.12,
    "swiss_dach_transferability": 0.16,
    "commercial_potential": 0.10,
    "current_assortment_gap_fit": 0.10,
    "strategic_gap_fit": 0.12,
    "company_profile_fit": 0.10,
}

WEIGHT_BUMP = 0.04


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Clamp negatives and rescale so the weights sum to 1.0."""
    clamped = {k: max(0.0, v) for k, v in weights.items()}
    total = sum(clamped.values())
    if total <= 0:
        n = len(clamped) or 1
        return {k: 1.0 / n for k in clamped}
    return {k: v / total for k, v in clamped.items()}


def get_dynamic_weights(
    profile: Dict[str, Any],
    request: Dict[str, Any],
    rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, float], List[str]]:
    """Adapt BASE_WEIGHTS to the customer query intent, the Agent 3 profile, and the
    Agent 1 evidence quality. Returns (normalized_weights, adjustment_reasons)."""
    profile = profile or {}
    request = request or {}
    weights = dict(BASE_WEIGHTS)
    reasons: List[str] = []

    def bump(key: str, amount: float, reason: str) -> None:
        weights[key] = weights.get(key, 0.0) + amount
        reasons.append(reason)

    # --- Agent 3 profile intent ---
    innovation = _norm(profile.get("innovation_appetite", "medium"))
    if "high" in innovation:
        bump("trend_momentum", WEIGHT_BUMP, "High innovation appetite: weighting trend_momentum up.")
        bump("strategic_gap_fit", WEIGHT_BUMP, "High innovation appetite: weighting strategic_gap_fit up.")
    elif "low" in innovation:
        bump("evidence_strength", WEIGHT_BUMP, "Low innovation appetite: weighting evidence_strength up.")
        bump("cross_source_validation", WEIGHT_BUMP, "Low innovation appetite: weighting cross_source_validation up.")

    margin = _norm(profile.get("target_gross_margin", ""))
    if "high" in margin:
        bump("commercial_potential", WEIGHT_BUMP, "High target gross margin: weighting commercial_potential up.")

    strategic_focus = profile.get("strategic_expansion_focus")
    strategic_gaps = profile.get("strategic_assortment_gaps")
    if (strategic_focus and not _is_placeholder(strategic_focus)) or (
        strategic_gaps and not _is_placeholder(strategic_gaps)
    ):
        bump("strategic_gap_fit", WEIGHT_BUMP, "Strategic expansion focus / assortment gaps present: weighting strategic_gap_fit up.")

    # --- Agent 1 evidence quality ---
    sources = set((r.get("source") or "").strip().lower() for r in rows if r.get("source"))
    signal_types = set((r.get("signal_type") or "").strip().lower() for r in rows if r.get("signal_type"))
    if len(sources) <= 1 or len(signal_types) <= 1:
        bump("evidence_strength", WEIGHT_BUMP, "Single-source evidence: weighting evidence_strength up.")
        bump("cross_source_validation", WEIGHT_BUMP, "Single-source evidence: weighting cross_source_validation up.")
        bump("trend_momentum", -WEIGHT_BUMP, "Single-source evidence: discounting trend_momentum.")

    markets = set((r.get("market") or "").strip().upper() for r in rows if r.get("market"))
    if not any(m in {"CH", "DACH", "DE", "AT", "SWITZERLAND", "GERMANY", "AUSTRIA"} for m in markets):
        bump("swiss_dach_transferability", WEIGHT_BUMP, "No CH/DACH evidence: weighting swiss_dach_transferability up.")

    if not any((r.get("url") or "").strip() for r in rows):
        bump("evidence_strength", WEIGHT_BUMP, "No evidence URLs: weighting evidence_strength up.")
        bump("trend_momentum", -WEIGHT_BUMP, "No evidence URLs: discounting trend_momentum.")

    # --- Customer query intent ---
    intent_text = _norm(str(request.get("product_focus", "")) + " " + str(request.get("original_query", "")))
    if any(k in intent_text for k in ["trend", "emerging", "rising", "innovative", "new"]):
        bump("trend_momentum", WEIGHT_BUMP, "Query signals trend/innovation intent: weighting trend_momentum up.")
    if any(k in intent_text for k in ["premium", "margin", "profit", "high-margin"]):
        bump("commercial_potential", WEIGHT_BUMP, "Query signals commercial/margin intent: weighting commercial_potential up.")

    return normalize_weights(weights), reasons


def compute_final_score(scores: Dict[str, float], weights: Dict[str, float]) -> float:
    """Weighted sum of the buyer dimensions named in weights."""
    return sum(weights.get(k, 0.0) * scores.get(k, 0.0) for k in weights)


def score_group(group: Dict[str, Any], profile: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    rows = group["signals"]

    signal_scores = [max(0.0, min(1.0, _safe_float(r.get("signal_score"), 0.0))) for r in rows]
    avg_signal = sum(signal_scores) / max(1, len(signal_scores))
    max_signal = max(signal_scores) if signal_scores else 0.0

    urls = evidence_urls(rows)
    url_coverage = len(urls) / max(1, len(rows))
    conf_avg = sum(confidence_to_num(r.get("confidence", "")) for r in rows) / max(1, len(rows))

    signal_types = set((r.get("signal_type") or "").strip().lower() for r in rows if r.get("signal_type"))
    markets = set((r.get("market") or "").strip().upper() for r in rows if r.get("market"))
    sources = set((r.get("source") or "").strip().lower() for r in rows if r.get("source"))

    all_text = _opportunity_text(group["opportunity"], rows)

    evidence_strength = 50 * avg_signal + 25 * min(1.0, url_coverage) + 25 * conf_avg
    cross_source_validation = min(100, 25 * len(signal_types) + 10 * len(markets) + 5 * min(len(sources), 4))
    trend_momentum = (0.7 * avg_signal + 0.3 * max_signal) * 100

    local_markets = {"CH", "DACH", "DE", "SWITZERLAND", "GERMANY", "AUSTRIA"}
    has_local = any(m in local_markets for m in markets)
    has_eu = any(m in {"EU", "EUROPE", "NORDICS", "UK"} for m in markets)

    swiss_dach_transferability = 50
    if has_local:
        swiss_dach_transferability += 30
    elif has_eu:
        swiss_dach_transferability += 18
    else:
        swiss_dach_transferability += 8

    if any(k in all_text for k in ["hiking", "rain", "shell", "waterproof", "trail", "ski", "climbing", "winter", "outdoor"]):
        swiss_dach_transferability += 10
    if any(k in all_text for k in ["pfas", "pfc", "sustainability", "repair", "recycled", "durable"]):
        swiss_dach_transferability += 8

    swiss_dach_transferability = min(100, swiss_dach_transferability)

    commercial_potential = 55
    if any(t in signal_types for t in ["competitor", "marketplace"]):
        commercial_potential += 15
    if any(r.get("price") for r in rows):
        commercial_potential += 8
    if any(r.get("brand") for r in rows):
        commercial_potential += 6
    if any(k in all_text for k in ["margin", "premium", "supplier", "bestseller", "rank"]):
        commercial_potential += 6
    commercial_potential = min(100, commercial_potential)

    sustainability_risk_relevance = 45
    if any(k in all_text for k in ["pfas", "pfc", "fluorocarbon"]):
        sustainability_risk_relevance += 35
    if any(k in all_text for k in ["repair", "durable", "recycled", "sustainability", "merino", "down alternative"]):
        sustainability_risk_relevance += 20
    sustainability_risk_relevance = min(100, sustainability_risk_relevance)

    current_gap_score, current_gap_reason = current_assortment_gap_fit(group["opportunity"], rows, profile)
    strategic_score, strategic_reason = strategic_gap_fit(group["opportunity"], rows, profile)
    company_score, company_reason = company_profile_fit_score(group["opportunity"], rows, profile)

    dimension_scores = {
        "evidence_strength": evidence_strength,
        "cross_source_validation": cross_source_validation,
        "trend_momentum": trend_momentum,
        "swiss_dach_transferability": swiss_dach_transferability,
        "commercial_potential": commercial_potential,
        "current_assortment_gap_fit": current_gap_score,
        "strategic_gap_fit": strategic_score,
        "company_profile_fit": company_score,
    }
    weights, weight_reasons = get_dynamic_weights(profile, request, rows)
    final_score = compute_final_score(dimension_scores, weights)

    return {
        "evidence_strength": round(evidence_strength, 1),
        "cross_source_validation": round(cross_source_validation, 1),
        "trend_momentum": round(trend_momentum, 1),
        "swiss_dach_transferability": round(swiss_dach_transferability, 1),
        "commercial_potential": round(commercial_potential, 1),
        "sustainability_risk_relevance": round(sustainability_risk_relevance, 1),
        "current_assortment_gap_fit": round(current_gap_score, 1),
        "strategic_gap_fit": round(strategic_score, 1),
        "company_profile_fit": round(company_score, 1),
        "final_score": round(final_score, 1),
        "current_gap_reason": current_gap_reason,
        "strategic_fit_reason": strategic_reason,
        "company_fit_reason": company_reason,
        "weights_used": {k: round(v, 4) for k, v in weights.items()},
        "weight_adjustment_reasons": weight_reasons,
    }


def infer_coverage_status(opportunity: str, rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> str:
    opp_text = _opportunity_text(opportunity, rows)

    current_categories = _profile_text(profile, "current_product_categories")
    current_gaps = _profile_text(profile, "current_assortment_gaps")
    strategic_gaps = _profile_text(profile, "strategic_assortment_gaps")

    category_overlap = keyword_overlap_score(opp_text, current_categories)
    current_gap_overlap = keyword_overlap_score(opp_text, current_gaps)
    strategic_gap_overlap = keyword_overlap_score(opp_text, strategic_gaps)

    if current_gap_overlap >= 25 or strategic_gap_overlap >= 25:
        return "absent"
    if category_overlap >= 35:
        return "covered"
    if category_overlap >= 15:
        return "partially_covered"

    markets = set((r.get("market") or "").strip().upper() for r in rows if r.get("market"))
    if any(m in {"CH", "DACH", "DE", "SWITZERLAND"} for m in markets):
        return "partially_covered"

    return "unknown"


def choose_action(opportunity: str, scores: Dict[str, Any], rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> str:
    text = _opportunity_text(opportunity, rows)

    final = scores["final_score"]
    evidence = scores["evidence_strength"]
    transfer = scores["swiss_dach_transferability"]
    cross = scores["cross_source_validation"]
    company_fit = scores["company_profile_fit"]
    strategic_fit = scores["strategic_gap_fit"]

    innovation = _norm(profile.get("innovation_appetite", "medium"))

    if evidence < 45 or cross < 35:
        return "Monitor"

    if company_fit < 45:
        return "Monitor"

    if strategic_fit >= 75 and final >= 65:
        if innovation == "high":
            return "Test"
        return "Monitor"

    if "Watch or contact emerging brand/supplier" in opportunity:
        if final >= 60:
            return "Contact supplier/brand"
        return "Monitor"

    if any(k in text for k in ["commuter", "trail-to-city", "urban outdoor", "gorpcore"]):
        if transfer >= 65 and final >= 60:
            return "Reposition existing assortment"
        return "Monitor"

    if any(k in text for k in ["pfas", "pfc", "fluorocarbon", "repair", "recycled", "down alternative", "synthetic insulation"]):
        if final >= 82 and evidence >= 75 and transfer >= 75 and company_fit >= 70:
            return "Launch"
        if final >= 62:
            return "Test"
        return "Monitor"

    if final >= 84 and evidence >= 75 and transfer >= 75 and company_fit >= 70:
        return "Launch"

    if final >= 68:
        return "Test"

    if final >= 55:
        return "Monitor"

    return "Ignore"


def confidence_label(scores: Dict[str, Any]) -> str:
    final = scores["final_score"]
    evidence = scores["evidence_strength"]
    cross = scores["cross_source_validation"]
    transfer = scores["swiss_dach_transferability"]
    fit = scores["company_profile_fit"]

    if final >= 82 and evidence >= 75 and cross >= 65 and transfer >= 75 and fit >= 70:
        return "high"
    if final >= 72 and evidence >= 65 and transfer >= 65 and fit >= 60:
        return "medium-high"
    if final >= 58:
        return "medium"
    if final >= 45:
        return "medium-low"
    return "low"


def transferability_text(scores: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    markets = unique_nonempty(rows, "market")
    market_text = ", ".join(markets) if markets else "unknown"
    rating = "high" if scores["swiss_dach_transferability"] >= 75 else "medium" if scores["swiss_dach_transferability"] >= 55 else "low"

    return (
        f"{rating.capitalize()}. Signals appear in {market_text}. "
        f"Swiss/DACH fit is {scores['swiss_dach_transferability']}/100 based on market proximity, "
        f"outdoor use-case relevance, climate/activity fit, and sustainability or regulatory relevance."
    )


def risks_and_missing(opportunity: str, scores: Dict[str, Any], rows: List[Dict[str, Any]], profile: Dict[str, Any], action: str) -> Tuple[List[str], List[str]]:
    risks = []
    missing = []

    signal_types = set((r.get("signal_type") or "").strip().lower() for r in rows if r.get("signal_type"))
    markets = set((r.get("market") or "").strip().upper() for r in rows if r.get("market"))
    urls = evidence_urls(rows)
    text = _opportunity_text(opportunity, rows)

    if len(signal_types) < 2:
        risks.append("Evidence is concentrated in one source type.")
        missing.append("Additional validation from competitor, marketplace, search, community, or publication sources.")

    if not any(m in {"CH", "DACH", "DE", "SWITZERLAND"} for m in markets):
        risks.append("Swiss/DACH transferability is inferred rather than directly observed.")
        missing.append("Local Swiss/DACH competitor or search evidence.")

    if len(urls) == 0:
        risks.append("No evidence URLs are attached to this opportunity.")
        missing.append("Source URLs for auditability.")

    if any(k in text for k in ["pfas", "pfc", "eco", "sustainability", "recycled", "down alternative"]):
        risks.append("Sustainability or material claims require verification before buying or marketing.")
        missing.append("Supplier-level material certification or claim substantiation.")

    if any(k in text for k in ["jacket", "shell", "commuter", "trail-to-city", "winter"]):
        risks.append("Potential cannibalization with existing jacket or shell assortment.")
        missing.append("Internal assortment snapshot and SKU overlap check.")

    confidence_map = profile.get("confidence_by_field", {}) or {}
    if confidence_map.get("strategic_expansion_focus") == "low":
        risks.append("Strategic expansion focus is low-confidence in Agent 3 profile; confirm with company.")
    if confidence_map.get("current_assortment_gaps") == "low":
        risks.append("Current assortment gaps are low-confidence; internal assortment validation is needed.")

    if action == "Launch":
        risks.append("Launch recommendation depends on margin, supplier availability, and inventory assumptions not yet validated.")
        missing.append("Supplier terms, margin estimates, and initial buy-depth assumptions.")

    if not risks:
        risks.append("Commercial potential is plausible but still directional; internal sales and margin data are unavailable.")

    return risks, missing


def summarize_evidence(opportunity: str, rows: List[Dict[str, Any]], scores: Dict[str, Any]) -> str:
    signal_types = sorted(set((r.get("signal_type") or "").strip() for r in rows if r.get("signal_type")))
    markets = unique_nonempty(rows, "market")
    sources = unique_nonempty(rows, "source")
    top_notes = [r.get("notes", "") for r in rows if r.get("notes")][:2]

    parts = [
        f"{len(rows)} signal row(s) grouped into this opportunity",
        f"source types: {', '.join(signal_types) if signal_types else 'unknown'}",
        f"markets: {', '.join(markets) if markets else 'unknown'}",
        f"final score: {scores['final_score']}/100",
    ]

    if sources:
        parts.append(f"key sources include {', '.join(sources[:3])}")
    if top_notes:
        parts.append("notes: " + " / ".join(top_notes))

    return ". ".join(parts) + "."


def next_step_text(action: str, opportunity: str) -> str:
    if action == "Launch":
        return f"Prepare a launch brief for {opportunity}, including supplier shortlist, price band, initial buy depth, and margin guardrails."
    if action == "Test":
        return f"Run a small test capsule for {opportunity}; validate local demand, sell-through, price band, and supplier margin before scaling."
    if action == "Buy":
        return f"Shortlist stockable products or brands for {opportunity} and compare price, availability, margin, and local competitor coverage."
    if action == "Contact supplier/brand":
        return f"Contact relevant brands or suppliers linked to {opportunity} and assess exclusivity, margin, availability, and Swiss/DACH fit."
    if action == "Reposition existing assortment":
        return f"Review existing SKUs that could be repositioned toward {opportunity} before buying additional overlapping products."
    if action == "Ignore":
        return f"Do not act on {opportunity} for now; evidence or transferability is too weak."
    return f"Monitor {opportunity} and collect additional Swiss/DACH evidence before buying or launching."


def build_recommendations(signals: List[Dict[str, Any]], profile: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    groups = group_signals(signals, request)
    rich_recs = []
    analytics_results = analytics.analyze_signals(signals, use_embeddings=False, verbose=False)

    for opportunity, group in groups.items():
        rows = group["signals"]
        scores = score_group(group, profile, request)
        base_score = scores["final_score"]

        adjusted_score, adjustment_notes = analytics.adjust_final_score(
            base_score,
            analytics_results,
            opportunity
        )

        scores["final_score"] = adjusted_score  # ← overwrites with adjusted score
        scores["analytics_adjustment"] = adjustment_notes

        action = choose_action(opportunity, scores, rows, profile)
        confidence = confidence_label(scores)
        risks, missing = risks_and_missing(opportunity, scores, rows, profile, action)

        rich_recs.append(
            {
                "rank": 0,
                "opportunity": opportunity,
                "first_observed_market": infer_first_observed_market(rows),
                "evidence_summary": summarize_evidence(opportunity, rows, scores),
                "evidence_urls": evidence_urls(rows),
                "transferability": transferability_text(scores, rows),
                "coverage_status": infer_coverage_status(opportunity, rows, profile),
                "recommended_action": action,
                "confidence": confidence,
                "risks": risks + [f"Missing evidence: {m}" for m in missing],
                "opportunity_type": sorted(group["opportunity_type"]),
                "signal_markets": unique_nonempty(rows, "market"),
                "scores": scores,
                "missing_evidence": missing,
                "next_step": next_step_text(action, opportunity),
                "company_alignment_summary": (
                    f"Current gap fit: {scores['current_gap_reason']} "
                    f"Strategic fit: {scores['strategic_fit_reason']} "
                    f"Company fit: {scores['company_fit_reason']}"
                ),
                "profile_fields_used": [
                    "positioning",
                    "target_price_band",
                    "customer_segments",
                    "current_product_categories",
                    "current_assortment_gaps",
                    "target_gross_margin",
                    "innovation_appetite",
                    "strategic_expansion_focus",
                    "strategic_assortment_gaps",
                    "confidence_by_field",
                ],
                "source_count": len(set(r.get("source", "") for r in rows if r.get("source"))),
                "signal_count": len(rows),
                "deduplication_note": f"Grouped {len(rows)} signal row(s) under canonical opportunity: {opportunity}",
                 "analytics_adjustment": scores.get("analytics_adjustment", {}),
                "analytics": {
                    "trend": analytics_results["trend"].get("trend"),
                    "trend_velocity": analytics_results["trend"].get("velocity"),  # ← NEW: rate of change
                    "saturation": analytics_results["saturation"].get("saturation_level"),
                    "saturation_score": analytics_results["saturation"].get("brand_concentration"),  # ← NEW: 0-1 score
                    "competitor_count": analytics_results["saturation"].get("competitor_count"),  # ← NEW: how many brands
                    "diversity": analytics_results["diversity"].get("diversity_score"),
                    "diversity_detail": {  # ← NEW: breakdown
                        "unique_keywords": analytics_results["diversity"].get("unique_keywords"),
                        "unique_brands": analytics_results["diversity"].get("unique_brands"),
                    },
                    "source_quality": analytics_results["source_quality"].get("quality_score"),
                    "anomalies": analytics_results["anomalies"].get("anomaly_count"),
                    "anomaly_list": analytics_results["anomalies"].get("anomalies", []),  # ← NEW: what's unusual
                    "geography": analytics_results["geography"].get("concentration"),  # ← NEW: CH-focused vs global
                    "clustering": {  # ← NEW: deduplication stats
                        "clusters": analytics_results["clustering"].get("cluster_count"),
                    },
                }
            
            }
        )

    rich_recs.sort(key=lambda r: r["scores"]["final_score"], reverse=True)

    for i, rec in enumerate(rich_recs, start=1):
        rec["rank"] = i

    return {
        "recommendations": rich_recs,
        "methodology_note": (
            "Agent 2 is the customer-facing decision agent. It parses the customer request, waits for Agent 1 signal rows "
            "and Agent 3 company profile, groups related signals into opportunities, uses Agent 1 signal_score mainly as "
            "trend_momentum, adds buyer-level scoring factors, adjusts by company profile and strategic gaps, and outputs "
            "Zenline-compatible recommendation rows."
        ),
        "known_limitations": [
            "Coverage status is inferred without full internal retailer assortment data unless Agent 3 provides detailed categories/gaps.",
            "Commercial potential is estimated from public signals, not retailer sales or margin data.",
            "Deterministic grouping is transparent but should be improved with embeddings if time allows.",
            "Recommendations are decision-support outputs and should be reviewed by a human buyer before acting.",
        ],
        "input_summary": {
            "customer_query": request.get("original_query", ""),
            "market": request.get("market", "DACH"),
            "category": request.get("category", "outdoor retail"),
            "product_focus": request.get("product_focus", ""),
            "number_of_input_signals": len(signals),
            "number_of_recommendations": len(rich_recs),
            "company_profile_used": bool(profile),
            "company_name": profile.get("company_name", "unknown"),
        },
    }


def write_json(data: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def to_recommendation_rows(data: Dict[str, Any]) -> List[RecommendationRow]:
    rows = []
    for rec in data["recommendations"]:
        rows.append(
            RecommendationRow(
                rank=rec["rank"],
                opportunity=rec["opportunity"],
                first_observed_market=rec["first_observed_market"],
                evidence_summary=rec["evidence_summary"],
                evidence_urls=rec["evidence_urls"],
                transferability=rec["transferability"],
                coverage_status=rec["coverage_status"],
                recommended_action=f"{rec['recommended_action']}: {rec['next_step']}",
                confidence=rec["confidence"],
                risks="; ".join(rec["risks"]),
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 2 — Main Decision Agent / Buyer Orchestrator (scoring core)")
    parser.add_argument("--query", default="", help="Customer query, e.g. 'Decathlon CH needs decision support on winter jackets'")
    parser.add_argument("--market", default="DACH", help="Target market lens, e.g. DACH or CH")
    parser.add_argument("--signals", default="out/signals.csv", help="Agent 1 output CSV")
    parser.add_argument("--profile", default="out/company_profile.json", help="Agent 3 output JSON")
    parser.add_argument("--request-json", default="out/agent2_request.json", help="Parsed request JSON for Agent 1 and Agent 3")
    parser.add_argument("--out-csv", default="out/recommendations.csv", help="Zenline-compatible recommendations CSV")
    parser.add_argument("--out-json", default="out/recommendations.json", help="Richer recommendations JSON")
    parser.add_argument("--init-only", action="store_true", help="Only parse customer request and write out/agent2_request.json")
    args = parser.parse_args()

    request = parse_customer_query(args.query, args.market)
    write_request_file(request, args.request_json)

    if args.init_only:
        print(f"Wrote request file: {args.request_json}")
        print("Next: run Agent 1 using agent1_seed_keywords and run Agent 3 to create out/company_profile.json.")
        print("Suggested Agent 1 seeds:")
        print(", ".join(request["agent1_seed_keywords"]))
        return

    if not os.path.exists(args.signals):
        print(f"Missing {args.signals}. Wrote {args.request_json}.")
        print("Run Agent 1 first using these seed keywords:")
        print(", ".join(request["agent1_seed_keywords"]))
        return

    signals = read_signals(args.signals)
    profile = load_profile(args.profile)

    result = build_recommendations(signals, profile, request)
    write_json(result, args.out_json)
    write_recommendations(to_recommendation_rows(result), args.out_csv)

    print(f"Wrote {args.out_csv}")
    print(f"Wrote {args.out_json}")
    print(f"Input signals: {len(signals)}")
    print(f"Recommendations: {len(result['recommendations'])}")


if __name__ == "__main__":
    main()
