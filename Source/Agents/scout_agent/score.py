"""Emerging-score math + optional clustering.

signal_score scale (documented in SUBMISSION.md):
    0.0 - 1.0, where
        velocity     = normalized growth of search / listing / community volume
        engagement   = log-scaled social interaction volume
        event_lift   = >1.0 when a related global event boosts the category, else 1.0
    emerging_score = clamp01( velocity * log1p(engagement) / NORM * event_lift )

Kept deliberately simple — the intelligence is in *how the Scout weighs signals*
(visible in its reasoning trace), not in formula complexity.
"""
from __future__ import annotations

import math
from typing import List, Dict

# Divisor that maps the raw product into roughly [0, 1] for typical inputs.
_NORM = 6.0


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def emerging_score(velocity: float, engagement: float, event_lift: float = 1.0) -> Dict:
    """velocity in [0,1], engagement is a raw count, event_lift >= 1.0."""
    raw = velocity * math.log1p(max(0.0, engagement)) / _NORM * max(1.0, event_lift)
    score = clamp01(raw)
    return {
        "emerging_score": round(score, 3),
        "breakdown": {
            "velocity": round(velocity, 3),
            "engagement": engagement,
            "event_lift": round(event_lift, 3),
        },
    }


def cluster_labels(texts: List[str], n_clusters: int = 5) -> List[int]:
    """Group free-text signal labels into emerging subcategories.

    Uses sentence-transformers + KMeans when available; otherwise falls back to
    a deterministic token-overlap bucketing so the scaffold always runs.
    """
    if not texts:
        return []
    try:  # upgrade path — install the optional deps in requirements.txt
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import KMeans

        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(texts)
        k = min(n_clusters, len(texts))
        return list(KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(emb))
    except Exception:
        return _fallback_cluster(texts, n_clusters)


def _fallback_cluster(texts: List[str], n_clusters: int) -> List[int]:
    """Greedy token-overlap clustering. No external deps."""
    seeds: List[set] = []
    labels: List[int] = []
    for t in texts:
        tokens = set(t.lower().split())
        best, best_overlap = -1, 0.0
        for i, s in enumerate(seeds):
            overlap = len(tokens & s) / max(1, len(tokens | s))
            if overlap > best_overlap:
                best, best_overlap = i, overlap
        if best_overlap >= 0.3 and best >= 0:
            labels.append(best)
        elif len(seeds) < n_clusters:
            seeds.append(tokens)
            labels.append(len(seeds) - 1)
        else:
            labels.append(best if best >= 0 else 0)
    return labels
