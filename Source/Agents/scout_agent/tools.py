"""Real, citeable evidence tools for the Scout (Agent A — sourcing).

Agent A's job: source signals from the real world and return them as **Signal Rows**
(docs/data-contract.md#signal-row). Every signal traces to a real source URL — the rubric
rewards evidence quality and penalizes speculation. Recommendations are NOT Agent A's job;
a downstream Buyer agent (Agent B) consumes these signal rows.

The fetch tools each return REAL data and auto-log a raw Signal Row for provenance. The agent
then curates the signals worth a buyer's attention with `emit_signal` — those curated rows are
Agent A's deliverable (out/signals.csv).

First good responses are cached under data/cache/ (real fetched data, not synthetic) so a live
API hiccup on stage can't sink the demo.

Tools exposed to Agent A (SOURCING_TOOLS):
    trend_momentum   - Google Trends rising interest (pytrends)   -> search signals
    community_heat   - Reddit outdoor communities (public JSON)   -> social signals
    event_signals    - GDELT global news/events (free API)        -> web/news signals
    score_emerging   - emerging-score helper (pure function)
    emit_signal      - record ONE curated Signal Row (the deliverable)

The Claude-hosted `web_search` server tool is added in scout.py as the primary general-evidence
engine (returns cited URLs directly). `emit_recommendation` is defined here for Agent B but is
NOT part of Agent A's toolset.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List

import requests

from .schema import SignalRow
from .score import emerging_score

# Anchor the cache to the repo root so it's shared/stable regardless of CWD.
CACHE_DIR = str(Path(__file__).resolve().parents[3] / "data" / "cache")
_HEADERS = {"User-Agent": "hercode-zenline-scout/0.1 (hackathon research)"}

# Raw signals auto-captured by the fetch tools (provenance backup).
_RAW_SIGNALS: List[SignalRow] = []
# Signals the agent curates via emit_signal — Agent A's deliverable.
_EMITTED_SIGNALS: List[SignalRow] = []
# Recommendations (Agent B only).
_RECS: List[Dict] = []


def reset() -> None:
    _RAW_SIGNALS.clear()
    _EMITTED_SIGNALS.clear()
    _RECS.clear()


def get_raw_signals() -> List[SignalRow]:
    return list(_RAW_SIGNALS)


def get_emitted_signals() -> List[SignalRow]:
    return list(_EMITTED_SIGNALS)


def get_recommendations() -> List[Dict]:
    return list(_RECS)


# --------------------------------------------------------------------------- #
# caching helpers
# --------------------------------------------------------------------------- #
def _cache_path(tool: str, key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{tool}_{h}.json")


def _cached(tool: str, key: str, fetch):
    """Return live data and cache it; fall back to cache on any failure.

    Never fabricates data — on total failure returns an explicit error payload
    so the agent (and the jury) can see the source was unavailable.
    """
    path = _cache_path(tool, key)
    try:
        data = fetch()
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.strftime("%Y-%m-%d %H:%M"), "data": data}, f)
        return data
    except Exception as e:  # noqa: BLE001 - demo robustness
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)["data"]
        return {"error": str(e), "results": []}


# --------------------------------------------------------------------------- #
# 1. Google Trends — search momentum
# --------------------------------------------------------------------------- #
def trend_momentum(keyword: str, market: str = "DACH", window: str = "today 3-m") -> Dict:
    geo = {"DACH": "DE", "CH": "CH", "US": "US", "UK": "GB"}.get(market.upper(), "")

    def fetch():
        from pytrends.request import TrendReq
        py = TrendReq(hl="en-US", tz=60)
        py.build_payload([keyword], timeframe=window, geo=geo)
        df = py.interest_over_time()
        if df.empty:
            raise RuntimeError("no trends data")
        series = df[keyword].tolist()
        third = max(1, len(series) // 3)
        first = sum(series[:third]) / third
        last = sum(series[-third:]) / third
        growth = (last - first) / max(1.0, first)
        rising = []
        try:
            rq = py.related_queries().get(keyword, {}).get("rising")
            if rq is not None:
                rising = rq.head(5)["query"].tolist()
        except Exception:
            pass
        return {
            "keyword": keyword, "geo": geo or "worldwide",
            "growth_ratio": round(growth, 3), "current_interest": series[-1],
            "rising_queries": rising,
            "url": f"https://trends.google.com/trends/explore?q={keyword.replace(' ', '%20')}&geo={geo}",
        }

    res = _cached("trend_momentum", f"{keyword}|{geo}|{window}", fetch)
    if "error" not in res:
        velocity = max(0.0, min(1.0, 0.5 + res["growth_ratio"]))
        _RAW_SIGNALS.append(SignalRow(
            source="Google Trends", market=market, keyword=keyword,
            signal_name=f"Search momentum: {keyword}", signal_type="search",
            url=res["url"], signal_score=round(velocity, 3),
            confidence="medium" if abs(res["growth_ratio"]) > 0.15 else "low",
            notes=f"growth_ratio={res['growth_ratio']}; rising={res.get('rising_queries')}",
            created_by_tool="trend_momentum",
        ))
    return res


# --------------------------------------------------------------------------- #
# 2. Reddit — activity / community heat
# --------------------------------------------------------------------------- #
def community_heat(topic: str, subreddits: List[str] = None) -> Dict:
    subs = subreddits or ["Ultralight", "CampingGear", "alpinism", "trailrunning", "Switzerland"]

    def fetch():
        posts = []
        for sub in subs:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/search.json",
                params={"q": topic, "restrict_sr": 1, "sort": "top", "t": "month", "limit": 5},
                headers=_HEADERS, timeout=15,
            )
            r.raise_for_status()
            for c in r.json().get("data", {}).get("children", []):
                d = c["data"]
                posts.append({
                    "subreddit": sub, "title": d.get("title", ""),
                    "score": d.get("score", 0), "comments": d.get("num_comments", 0),
                    "url": "https://www.reddit.com" + d.get("permalink", ""),
                })
            time.sleep(0.5)
        posts.sort(key=lambda p: p["score"], reverse=True)
        return {"topic": topic, "results": posts[:10]}

    res = _cached("community_heat", topic + "|" + ",".join(subs), fetch)
    for p in res.get("results", [])[:5]:
        engagement = p["score"] + p["comments"]
        _RAW_SIGNALS.append(SignalRow(
            source=f"Reddit r/{p['subreddit']}", market="global", keyword=topic,
            signal_name=p["title"][:80], signal_type="social", url=p["url"],
            signal_score=round(min(1.0, engagement / 3000.0), 3),
            confidence="medium",
            notes=f"score={p['score']} comments={p['comments']}",
            created_by_tool="community_heat",
        ))
    return res


# --------------------------------------------------------------------------- #
# 3. GDELT — global events / news
# --------------------------------------------------------------------------- #
def event_signals(query: str) -> Dict:
    def fetch():
        r = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "ArtList", "format": "json",
                    "maxrecords": 10, "timespan": "3months", "sort": "hybridrel"},
            headers=_HEADERS, timeout=20,
        )
        r.raise_for_status()
        arts = r.json().get("articles", [])
        return {"query": query, "results": [
            {"title": a.get("title", ""), "url": a.get("url", ""),
             "domain": a.get("domain", ""), "date": a.get("seendate", "")}
            for a in arts
        ]}

    res = _cached("event_signals", query, fetch)
    n = len(res.get("results", []))
    for a in res.get("results", [])[:4]:
        _RAW_SIGNALS.append(SignalRow(
            source=f"GDELT/{a['domain']}", market="global", keyword=query,
            signal_name=a["title"][:80] or query, signal_type="web", url=a["url"],
            signal_score=round(min(1.0, n / 10.0), 3), confidence="low",
            notes="event/news coverage via GDELT", brand=a["domain"],
            created_by_tool="event_signals",
        ))
    res["demand_lift"] = round(1.0 + min(0.5, n / 20.0), 3)
    return res


# --------------------------------------------------------------------------- #
# 4. score_emerging — pure function tool
# --------------------------------------------------------------------------- #
def score_emerging(velocity: float, engagement: float, event_lift: float = 1.0) -> Dict:
    return emerging_score(velocity, engagement, event_lift)


# --------------------------------------------------------------------------- #
# 5. emit_signal — record ONE curated Signal Row (Agent A's deliverable)
# --------------------------------------------------------------------------- #
def emit_signal(**kwargs) -> Dict:
    row = SignalRow(
        source=kwargs.get("source", ""),
        market=kwargs.get("market", ""),
        keyword=kwargs.get("keyword", ""),
        signal_name=kwargs.get("signal_name", ""),
        signal_type=kwargs.get("signal_type", "web"),
        url=kwargs.get("url", ""),
        signal_score=float(kwargs.get("signal_score", 0.0)),
        confidence=kwargs.get("confidence", "low"),
        created_by_tool=kwargs.get("created_by_tool", "scout/emit_signal"),
        product_name=kwargs.get("product_name", ""),
        brand=kwargs.get("brand", ""),
        price=str(kwargs.get("price", "")),
        rank=str(kwargs.get("rank", "")),
        notes=kwargs.get("notes", ""),
    )
    _EMITTED_SIGNALS.append(row)
    return {"ok": True, "emitted_count": len(_EMITTED_SIGNALS)}


# --------------------------------------------------------------------------- #
# emit_recommendation — Agent B only (defined here, NOT in Agent A's toolset)
# --------------------------------------------------------------------------- #
def emit_recommendation(**kwargs) -> Dict:
    _RECS.append(kwargs)
    return {"ok": True, "recorded_rank": kwargs.get("rank")}


# --------------------------------------------------------------------------- #
# Tool schemas + dispatch
# --------------------------------------------------------------------------- #
_TREND = {
    "name": "trend_momentum",
    "description": "Google Trends search momentum for a keyword in a market. Returns growth ratio, "
                   "current interest, rising related queries, and a trends.google.com evidence URL. "
                   "Use to quantify how fast demand is accelerating, and in which market.",
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search phrase, e.g. 'approach shoes'"},
            "market": {"type": "string", "enum": ["DACH", "CH", "US", "UK"],
                       "description": "Market geo. Use CH/DACH to check where a signal lands locally."},
        },
        "required": ["keyword"],
    },
}
_COMMUNITY = {
    "name": "community_heat",
    "description": "Activity/community signal: searches outdoor subreddits (Ultralight, CampingGear, "
                   "alpinism, trailrunning, Switzerland) for a topic and returns top posts with "
                   "engagement counts and real reddit.com URLs. Use for activity/location/community heat, "
                   "NOT influencer outfits.",
    "input_schema": {
        "type": "object",
        "properties": {"topic": {"type": "string", "description": "Activity/product topic"}},
        "required": ["topic"],
    },
}
_EVENT = {
    "name": "event_signals",
    "description": "GDELT global news/events for a query (last 3 months). Returns articles with real URLs. "
                   "Use to detect short-term demand boosters (events, viral moments) AND red flags "
                   "(brand/supplier scandals, material regulatory risk).",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Event/brand/material query"}},
        "required": ["query"],
    },
}
_SCORE = {
    "name": "score_emerging",
    "description": "Compute an emerging_score (0-1) from velocity (0-1), engagement (raw count), and "
                   "event_lift (>=1.0). Use to set a signal_score before emitting a signal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "velocity": {"type": "number"},
            "engagement": {"type": "number"},
            "event_lift": {"type": "number"},
        },
        "required": ["velocity", "engagement"],
    },
}
_EMIT_SIGNAL = {
    "name": "emit_signal",
    "description": "Record ONE curated Signal Row in the jury's contract shape "
                   "(docs/data-contract.md#signal-row). Call once per real-world signal worth a buyer's "
                   "attention. `url` MUST be a real source URL from a tool result or web_search. "
                   "Tag `market` with where the signal actually appears (CH, DACH, US, Japan, Korea, "
                   "Nordics, UK, global). This is your deliverable — emit 10-20 diverse signals.",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "e.g. Google Trends, Reddit r/alpinism, GDELT/domain, retailer site"},
            "market": {"type": "string", "description": "CH, DACH, US, Japan, Korea, Nordics, UK, global"},
            "keyword": {"type": "string"},
            "signal_name": {"type": "string", "description": "Human-readable name of the trend/opportunity"},
            "signal_type": {"type": "string",
                            "enum": ["search", "social", "web", "marketplace", "competitor", "api", "manual"]},
            "url": {"type": "string", "description": "Real evidence URL"},
            "signal_score": {"type": "number", "description": "0.0-1.0 signal strength (define via score_emerging)"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "product_name": {"type": "string"},
            "brand": {"type": "string"},
            "price": {"type": "string"},
            "rank": {"type": "string", "description": "bestseller/listing/popularity rank if relevant"},
            "notes": {"type": "string", "description": "Short evidence notes and limitations"},
        },
        "required": ["source", "market", "keyword", "signal_name", "signal_type", "url",
                     "signal_score", "confidence"],
    },
}

# Agent A (sourcing) toolset.
SOURCING_TOOLS = [_TREND, _COMMUNITY, _EVENT, _SCORE, _EMIT_SIGNAL]

# Back-compat alias.
TOOL_SCHEMAS = SOURCING_TOOLS

_DISPATCH = {
    "trend_momentum": trend_momentum,
    "community_heat": community_heat,
    "event_signals": event_signals,
    "score_emerging": score_emerging,
    "emit_signal": emit_signal,
    "emit_recommendation": emit_recommendation,
}


def dispatch(name: str, tool_input: Dict) -> Dict:
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**tool_input)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{name} failed: {e}"}
