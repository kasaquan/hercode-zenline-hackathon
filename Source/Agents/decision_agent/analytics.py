"""
Agent 2 Analytics: Statistical Analysis of Scout Signals

Adds data science rigor to recommendations:
- Signal clustering (deduplication)
- Trend velocity (acceleration/deceleration)
- Market saturation (brand diversity, crowding)
- Anomaly detection (unusual signals)
- Geographic concentration (CH vs DACH)
- Source diversity (Reddit vs web vs marketplace)
- Confidence weighting (high-confidence signals > low-confidence)

All analysis is deterministic and reproducible.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional, Tuple
import json
from datetime import datetime

import numpy as np
from pathlib import Path


# ============================================================================
# 1. SIGNAL CLUSTERING (Deduplication)
# ============================================================================

def cluster_signals_simple(signals: List[Dict]) -> Dict[int, List[Dict]]:
    """
    Group similar signals by keyword overlap (no external deps).
    
    Returns: {cluster_id: [signals in cluster]}
    
    Example: "ultralight packs" + "lightweight modular packs" → same cluster
    """
    
    def keyword_similarity(s1: str, s2: str, threshold: float = 0.4) -> float:
        """Jaccard similarity between keyword sets"""
        tokens1 = set(s1.lower().split())
        tokens2 = set(s2.lower().split())
        
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return intersection / union if union > 0 else 0.0
    
    clusters = {}
    cluster_id = 0
    
    for signal in signals:
        signal_text = signal.get("signal_name", "")
        
        # Try to match with existing clusters
        best_cluster = None
        best_score = 0.0
        
        for cid, cluster_signals in clusters.items():
            for cs in cluster_signals:
                score = keyword_similarity(signal_text, cs.get("signal_name", ""))
                if score > best_score:
                    best_score = score
                    best_cluster = cid
        
        # If match found (>40% overlap), add to cluster; else create new
        if best_cluster is not None and best_score >= 0.4:
            clusters[best_cluster].append(signal)
        else:
            clusters[cluster_id] = [signal]
            cluster_id += 1
    
    return clusters


def cluster_signals_embedding(signals: List[Dict]) -> Dict[int, List[Dict]]:
    """
    Group similar signals using sentence embeddings + KMeans.
    
    Requires: pip install sentence-transformers scikit-learn
    
    Returns: {cluster_id: [signals in cluster]}
    """
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import KMeans
    except ImportError:
        print("[analytics] sentence-transformers/sklearn not available; falling back to keyword clustering")
        return cluster_signals_simple(signals)
    
    if not signals:
        return {}
    
    texts = [s.get("signal_name", "") for s in signals]
    
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(texts)
    
    n_clusters = min(max(2, len(signals) // 3), 15)
    kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = kmeans.fit_predict(embeddings)
    
    clusters = defaultdict(list)
    for sig, label in zip(signals, labels):
        clusters[int(label)].append(sig)
    
    return dict(clusters)


# ============================================================================
# 2. TREND VELOCITY (Acceleration Analysis)
# ============================================================================

def extract_date_from_signal(signal: Dict) -> Optional[datetime]:
    """Try to parse observed_at timestamp from signal"""
    observed = signal.get("observed_at")
    if not observed:
        return None
    
    try:
        return datetime.fromisoformat(observed)
    except (ValueError, TypeError):
        return None


def calculate_trend_velocity(signals: List[Dict]) -> Dict[str, Any]:
    """
    Measure trend acceleration/deceleration.
    
    If signals have timestamps, fit linear regression to mention volume over time.
    
    Returns:
        {
            "has_timestamps": bool,
            "velocity": float,  # mentions/day (or None if no timestamps)
            "trend": "accelerating" | "stable" | "decelerating",
            "days_observed": int,
            "mentions_per_day": float,
        }
    """
    
    # Try to extract dates
    signals_with_dates = []
    for sig in signals:
        date = extract_date_from_signal(sig)
        if date:
            signals_with_dates.append((date, sig))
    
    if len(signals_with_dates) < 2:
        return {
            "has_timestamps": False,
            "velocity": None,
            "trend": "unknown",
            "days_observed": len(signals_with_dates),
            "mentions_per_day": 0.0,
        }
    
    # Group by date
    dates_sorted = sorted(signals_with_dates, key=lambda x: x[0])
    date_range = dates_sorted[-1][0] - dates_sorted[0][0]
    days = max(1, date_range.days)
    
    # Count mentions per day
    mentions_by_date = defaultdict(int)
    for date, sig in signals_with_dates:
        mentions_by_date[date.date()] += 1
    
    sorted_dates = sorted(mentions_by_date.keys())
    mention_counts = [mentions_by_date[d] for d in sorted_dates]
    
    # Fit linear regression: count ~ day_number
    try:
        x = np.array(range(len(mention_counts))).reshape(-1, 1).astype(float)
        y = np.array(mention_counts).astype(float)
        
        # Simple linear fit (avoid sklearn if possible)
        from sklearn.linear_model import LinearRegression
        lr = LinearRegression().fit(x, y)
        slope = float(lr.coef_[0])
    except ImportError:
        # Fallback: simple slope calculation
        if len(mention_counts) >= 2:
            slope = (mention_counts[-1] - mention_counts[0]) / max(1, len(mention_counts) - 1)
        else:
            slope = 0.0
    
    # Interpret trend
    if slope > 0.1:
        trend = "accelerating"
    elif slope < -0.1:
        trend = "decelerating"
    else:
        trend = "stable"
    
    avg_mentions_per_day = len(signals_with_dates) / max(1, days)
    
    return {
        "has_timestamps": True,
        "velocity": round(slope, 3),
        "trend": trend,
        "days_observed": days,
        "mentions_per_day": round(avg_mentions_per_day, 2),
    }


# ============================================================================
# 3. MARKET SATURATION (Brand Diversity)
# ============================================================================

def calculate_market_saturation(signals: List[Dict]) -> Dict[str, Any]:
    """
    Estimate market crowding based on unique brands and source diversity.
    
    Returns:
        {
            "unique_brands": int,
            "brand_concentration": float,  # Herfindahl index (0-1)
            "saturation_level": "low" | "medium" | "high",
            "top_brands": [("brand", count)],
            "source_diversity": float,  # 0-1, how many different source types
            "competitor_count": int,
        }
    """
    
    # Count brands
    brands = Counter()
    sources = Counter()
    
    for sig in signals:
        brand = sig.get("brand", "unknown")
        if brand:
            brands[brand] += 1
        
        source = sig.get("source", "unknown")
        if source:
            sources[source] += 1
    
    # Herfindahl index: sum of squared market shares (0 = diverse, 1 = monopoly)
    total = len(signals)
    hhi = sum((count / total) ** 2 for count in brands.values()) if total > 0 else 0.0
    
    # Source diversity: Shannon entropy
    source_entropy = 0.0
    if total > 0:
        for count in sources.values():
            p = count / total
            if p > 0:
                source_entropy -= p * math.log(p)
    max_entropy = math.log(len(sources)) if len(sources) > 1 else 1.0
    source_diversity = source_entropy / max_entropy if max_entropy > 0 else 0.0
    
    # Saturation level
    if hhi > 0.5 or len(brands) < 3:
        saturation = "low"  # Few players, greenfield
    elif hhi > 0.25:
        saturation = "medium"
    else:
        saturation = "high"  # Many competitors, crowded
    
    return {
        "unique_brands": len(brands),
        "brand_concentration": round(hhi, 3),
        "saturation_level": saturation,
        "top_brands": brands.most_common(5),
        "source_diversity": round(source_diversity, 3),
        "competitor_count": len(brands),
    }


# ============================================================================
# 4. ANOMALY DETECTION (Statistical Outliers)
# ============================================================================

def detect_anomalies(signals: List[Dict]) -> Dict[str, Any]:
    """
    Identify unusual signals (high engagement, unusual price, outlier markets).
    
    Uses statistical methods (IQR for scores, simple z-score for others).
    
    Returns:
        {
            "anomalies": [
                {
                    "signal_name": str,
                    "anomaly_type": "high_engagement" | "unusual_price" | "outlier_market",
                    "reason": str,
                    "severity": "low" | "medium" | "high",
                }
            ],
            "anomaly_count": int,
        }
    """
    
    anomalies = []
    
    if not signals:
        return {"anomalies": [], "anomaly_count": 0}
    
    # 1. Outlier signal scores (IQR method)
    scores = [float(s.get("signal_score", 0.5)) for s in signals]
    if scores:
        scores_arr = np.array(scores)
        q1 = np.percentile(scores_arr, 25)
        q3 = np.percentile(scores_arr, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        for sig in signals:
            score = float(sig.get("signal_score", 0.5))
            if score > upper_bound:
                anomalies.append({
                    "signal_name": sig.get("signal_name", "Unknown"),
                    "anomaly_type": "high_engagement",
                    "reason": f"Signal score {score:.2f} is unusually high (>Q3+1.5*IQR)",
                    "severity": "medium",
                })
    
    # 2. Unusual price points
    prices = [float(p) for s in signals if (p := s.get("price")) and isinstance(p, (int, float))]
    if prices:
        prices_arr = np.array(prices)
        mean_price = np.mean(prices_arr)
        std_price = np.std(prices_arr)
        
        for sig in signals:
            try:
                price = float(sig.get("price", mean_price))
                z_score = abs((price - mean_price) / (std_price + 1e-6))
                if z_score > 2.5:
                    anomalies.append({
                        "signal_name": sig.get("signal_name", "Unknown"),
                        "anomaly_type": "unusual_price",
                        "reason": f"Price {price:.0f} CHF is unusual (z-score {z_score:.1f})",
                        "severity": "low",
                    })
            except (ValueError, TypeError):
                pass
    
    # 3. Outlier markets (signals from unexpected regions)
    market_counts = Counter(s.get("market", "unknown") for s in signals)
    total = len(signals)
    expected_freq = 1 / max(1, len(market_counts))
    
    for market, count in market_counts.items():
        freq = count / total
        if freq > expected_freq * 2:  # 2x more than expected
            anomalies.append({
                "signal_name": f"Market concentration: {market}",
                "anomaly_type": "outlier_market",
                "reason": f"{market} accounts for {freq:.0%} of signals (unusual concentration)",
                "severity": "low",
            })
    
    return {
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
    }


# ============================================================================
# 5. ADDITIONAL INSIGHTS
# ============================================================================

def calculate_geographic_concentration(signals: List[Dict]) -> Dict[str, Any]:
    """
    Measure if trend is CH-specific or DACH-wide or global.
    
    Returns:
        {
            "ch_ratio": float,  # % of signals from CH
            "dach_ratio": float,
            "global_ratio": float,
            "concentration": "ch_focused" | "dach_focused" | "global",
        }
    """
    
    markets = Counter(s.get("market", "other") for s in signals)
    total = len(signals)
    
    ch_ratio = (markets.get("CH", 0) + markets.get("ch", 0)) / max(1, total)
    dach_ratio = sum(markets.get(m, 0) for m in ["AT", "DE", "at", "de"]) / max(1, total)
    global_ratio = 1 - ch_ratio - dach_ratio
    
    if ch_ratio > 0.5:
        concentration = "ch_focused"
    elif ch_ratio + dach_ratio > 0.7:
        concentration = "dach_focused"
    else:
        concentration = "global"
    
    return {
        "ch_ratio": round(ch_ratio, 2),
        "dach_ratio": round(dach_ratio, 2),
        "global_ratio": round(global_ratio, 2),
        "concentration": concentration,
    }


def calculate_source_quality(signals: List[Dict]) -> Dict[str, Any]:
    """
    Assess source credibility (web > marketplace > social > manual).
    
    Returns:
        {
            "avg_confidence": float,  # Average stated confidence
            "source_types": {type: count},
            "quality_score": float,  # 0-1, weighted by confidence
        }
    """
    
    sources = Counter(s.get("source", "unknown") for s in signals)
    
    confidence_map = {"high": 1.0, "medium": 0.7, "low": 0.4}
    confidences = [
        confidence_map.get(s.get("confidence", "medium"), 0.7) for s in signals
    ]
    avg_confidence = np.mean(confidences) if confidences else 0.5
    
    # Weight by source type credibility
    source_credibility = {
        "web": 0.9,
        "competitor": 0.85,
        "marketplace": 0.8,
        "search": 0.75,
        "social": 0.6,
        "reddit": 0.6,
        "manual": 0.4,
        "unknown": 0.5,
    }
    
    quality_scores = []
    for sig in signals:
        source = sig.get("source", "unknown").lower()
        cred = source_credibility.get(source, 0.5)
        conf = confidence_map.get(sig.get("confidence", "medium"), 0.7)
        quality_scores.append(cred * conf)
    
    avg_quality = np.mean(quality_scores) if quality_scores else 0.5
    
    return {
        "avg_confidence": round(avg_confidence, 2),
        "source_types": dict(sources),
        "quality_score": round(avg_quality, 2),
    }


def calculate_signal_diversity(signals: List[Dict]) -> Dict[str, Any]:
    """
    Measure how diverse the signals are (product types, keywords, etc).
    
    High diversity = robust trend. Low diversity = single mention repeated.
    
    Returns:
        {
            "unique_keywords": int,
            "unique_signal_names": int,
            "unique_brands": int,
            "diversity_score": float,  # 0-1
        }
    """
    
    keywords = set()
    for sig in signals:
        kw = sig.get("keyword", "")
        keywords.update(kw.lower().split(","))
    
    signal_names = set(s.get("signal_name", "") for s in signals)
    brands = set(s.get("brand", "") for s in signals)
    
    # Diversity = unique_items / total_items (more unique = more diverse)
    total = len(signals)
    diversity = (
        0.3 * (len(keywords) / max(1, total)) +
        0.4 * (len(signal_names) / max(1, total)) +
        0.3 * (len(brands) / max(1, total))
    )
    
    return {
        "unique_keywords": len(keywords),
        "unique_signal_names": len(signal_names),
        "unique_brands": len(brands),
        "diversity_score": round(min(1.0, diversity), 2),
    }


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def analyze_signals(
    signals: List[Dict],
    use_embeddings: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Run all analytics on a signal set.
    
    Args:
        signals: List of Scout signal dicts
        use_embeddings: Use sentence-transformers for clustering (slower, better)
        verbose: Print progress
    
    Returns:
        {
            "clustering": {...},
            "trend": {...},
            "saturation": {...},
            "anomalies": {...},
            "geography": {...},
            "source_quality": {...},
            "diversity": {...},
        }
    """
    
    if not signals:
        return {
            "clustering": {},
            "trend": {"has_timestamps": False},
            "saturation": {"unique_brands": 0},
            "anomalies": {"anomaly_count": 0},
            "geography": {},
            "source_quality": {},
            "diversity": {},
        }
    
    results = {}
    
    if verbose:
        print(f"[analytics] Analyzing {len(signals)} signals...")
    
    # Clustering
    if verbose:
        print("[analytics] Clustering...")
    clusters = (
        cluster_signals_embedding(signals)
        if use_embeddings
        else cluster_signals_simple(signals)
    )
    results["clustering"] = {
        "cluster_count": len(clusters),
        "clusters": {
            cid: {
                "signal_count": len(sigs),
                "canonical_name": sigs[0].get("signal_name", "Unknown"),
                "top_score": max((s.get("signal_score", 0) for s in sigs), default=0),
            }
            for cid, sigs in clusters.items()
        }
    }
    
    # Trend velocity
    if verbose:
        print("[analytics] Trend velocity...")
    results["trend"] = calculate_trend_velocity(signals)
    
    # Market saturation
    if verbose:
        print("[analytics] Market saturation...")
    results["saturation"] = calculate_market_saturation(signals)
    
    # Anomalies
    if verbose:
        print("[analytics] Anomaly detection...")
    results["anomalies"] = detect_anomalies(signals)
    
    # Geography
    if verbose:
        print("[analytics] Geographic concentration...")
    results["geography"] = calculate_geographic_concentration(signals)
    
    # Source quality
    if verbose:
        print("[analytics] Source quality...")
    results["source_quality"] = calculate_source_quality(signals)
    
    # Diversity
    if verbose:
        print("[analytics] Diversity...")
    results["diversity"] = calculate_signal_diversity(signals)
    
    if verbose:
        print("[analytics] ✓ Complete")
    
    return results


# ============================================================================
# INTEGRATION WITH AGENT 2 SCORING
# ============================================================================

def adjust_final_score(
    base_score: float,
    analytics: Dict[str, Any],
    opportunity_name: str,
) -> Tuple[float, Dict[str, str]]:
    """
    Adjust final_score based on analytics insights.
    
    Args:
        base_score: Initial score from deterministic Agent 2
        analytics: Output from analyze_signals()
        opportunity_name: Name of the opportunity (for matching to clusters)
    
    Returns:
        (adjusted_score, adjustment_notes)
    """
    
    adjustments = {}
    multiplier = 1.0
    
    # Trend boost/penalty
    trend = analytics.get("trend", {})
    if trend.get("trend") == "accelerating":
        multiplier *= 1.15
        adjustments["trend"] = "+15% (trend accelerating)"
    elif trend.get("trend") == "decelerating":
        multiplier *= 0.85
        adjustments["trend"] = "-15% (trend decelerating)"
    
    # Saturation penalty
    saturation = analytics.get("saturation", {})
    sat_level = saturation.get("saturation_level", "medium")
    if sat_level == "high":
        multiplier *= 0.9
        adjustments["saturation"] = "-10% (crowded market)"
    elif sat_level == "low":
        multiplier *= 1.1
        adjustments["saturation"] = "+10% (greenfield opportunity)"
    
    # Diversity boost
    diversity = analytics.get("diversity", {})
    div_score = diversity.get("diversity_score", 0.5)
    if div_score > 0.7:
        multiplier *= 1.05
        adjustments["diversity"] = "+5% (high signal diversity)"
    elif div_score < 0.3:
        multiplier *= 0.9
        adjustments["diversity"] = "-10% (low diversity, single source)"
    
    # Source quality
    src_quality = analytics.get("source_quality", {})
    quality = src_quality.get("quality_score", 0.5)
    if quality > 0.8:
        multiplier *= 1.05
        adjustments["quality"] = "+5% (high source credibility)"
    elif quality < 0.5:
        multiplier *= 0.85
        adjustments["quality"] = "-15% (low source credibility)"
    
    # Geographic fit (bonus for CH/DACH focus)
    geo = analytics.get("geography", {})
    if geo.get("concentration") in ["ch_focused", "dach_focused"]:
        multiplier *= 1.08
        adjustments["geography"] = "+8% (strong regional signal)"
    
    adjusted_score = base_score * multiplier
    
    return adjusted_score, adjustments


if __name__ == "__main__":
    # Test example
    test_signals = [
        {
            "signal_name": "Ultralight modular packs",
            "signal_score": 0.82,
            "source": "web",
            "market": "CH",
            "brand": "Deuter",
            "confidence": "high",
            "observed_at": "2026-06-15",
            "keyword": "ultralight, packs",
        },
        {
            "signal_name": "Lightweight modular backpacks",
            "signal_score": 0.79,
            "source": "reddit",
            "market": "CH",
            "brand": "ArcTeryx",
            "confidence": "medium",
            "observed_at": "2026-06-18",
            "keyword": "ultralight, backpacks",
        },
    ]
    
    result = analyze_signals(test_signals, verbose=True)
    print("\n=== ANALYTICS RESULTS ===")
    print(json.dumps(result, indent=2, default=str))