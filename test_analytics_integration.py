"""Quick test of analytics integration"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from decision import build_recommendations, parse_customer_query

# Test signals (fake Scout output)
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
        "signal_type": "web",
        "product_name": "Pack system",
        "price": "250",
        "rank": "1",
        "url": "https://example.com/signal1",
        "notes": "Growing Reddit discussion",
        "artifact_type": "csv",
        "artifact_uri": "out/signals.csv",
        "created_by_tool": "scout",
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
        "signal_type": "social",
        "product_name": "Backpack",
        "price": "280",
        "rank": "2",
        "url": "https://example.com/signal2",
        "notes": "Trending in outdoor communities",
        "artifact_type": "csv",
        "artifact_uri": "out/signals.csv",
        "created_by_tool": "scout",
    },
]

# Test profile (default)
test_profile = {
    "company_name": "Test Swiss Retailer",
    "active_markets": ["CH", "DE"],
    "positioning": "mid-range",
    "target_price_band": "mid (100-300)",
    "customer_segments": ["hikers", "backpackers"],
    "current_assortment_gaps": "ultralight systems, sustainable materials",
    "strategic_expansion_focus": "ultralight backpacking",
}

# Test request
request = parse_customer_query("Test company needs ultralight packs", "CH")

# Run recommendation building
print("=" * 60)
print("Testing Analytics Integration")
print("=" * 60)

result = build_recommendations(test_signals, test_profile, request)

print("\n✅ Build completed successfully!")
print(f"\nRecommendations generated: {len(result['recommendations'])}")

for rec in result["recommendations"]:
    print(f"\n📊 Opportunity: {rec['opportunity']}")
    print(f"   Base score: ~{rec['scores']['final_score']}")
    print(f"   Analytics adjustment: {rec.get('analytics_adjustment', {})}")
    print(f"   Trend: {rec['analytics']['trend']}")
    print(f"   Saturation: {rec['analytics']['saturation']}")
    print(f"   Diversity: {rec['analytics']['diversity']:.2f}")
    print(f"   Action: {rec['recommended_action']}")

print("\n" + "=" * 60)
print("✅ TEST PASSED")
print("=" * 60)
