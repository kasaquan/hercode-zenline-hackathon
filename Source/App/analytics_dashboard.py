"""
Analytics Results Dashboard
Beautiful visualization of Agent 2 scoring, analytics insights, and recommendations
"""

import streamlit as st
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="Zenline Analytics Results",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# STYLING
# ============================================================================

st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.9;
        margin-top: 5px;
    }
    .score-high {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .score-medium {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    .score-low {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
    }
    .insight-box {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 10px 0;
    }
    .insight-title {
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# LOAD DATA
# ============================================================================

@st.cache_data
def load_recommendations():
    """Load recommendations from JSON file"""
    rec_path = Path("out/recommendations.json")
    if not rec_path.exists():
        return None
    
    with open(rec_path) as f:
        return json.load(f)

data = load_recommendations()

if not data:
    st.error("❌ No recommendations found. Run the analysis first!")
    st.info("📍 Run: `python -m Agents.decision_agent --query '...'`")
    st.stop()

# ============================================================================
# HEADER
# ============================================================================

col1, col2 = st.columns([1, 4])

with col1:
    st.markdown("📊")

with col2:
    st.title("Zenline Analytics Results")
    st.caption(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

st.divider()

# ============================================================================
# SUMMARY STATS
# ============================================================================

st.subheader("📈 Summary")

col1, col2, col3, col4 = st.columns(4)

recommendations = data.get("recommendations", [])
input_summary = data.get("input_summary", {})

with col1:
    st.metric(
        "Total Signals Analyzed",
        input_summary.get("number_of_input_signals", 0)
    )

with col2:
    st.metric(
        "Opportunities Identified",
        input_summary.get("number_of_recommendations", 0)
    )

with col3:
    top_score = max([r["scores"]["final_score"] for r in recommendations], default=0)
    st.metric(
        "Highest Score",
        f"{top_score:.1f}/100"
    )

with col4:
    avg_score = sum([r["scores"]["final_score"] for r in recommendations]) / max(1, len(recommendations))
    st.metric(
        "Average Score",
        f"{avg_score:.1f}/100"
    )

st.divider()

# ============================================================================
# TABS: ANALYTICS INSIGHTS
# ============================================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Recommendations Overview",
    "📊 Scoring Breakdown",
    "🔬 Analytics Deep Dive",
    "💡 Insights & Explanations"
])

# ============================================================================
# TAB 1: RECOMMENDATIONS OVERVIEW
# ============================================================================

with tab1:
    st.subheader("Top Opportunities Ranked by Score")
    
    # Create ranking table
    ranking_data = []
    for rec in recommendations:
        ranking_data.append({
            "Rank": rec["rank"],
            "Opportunity": rec["opportunity"][:60],
            "Score": f"{rec['scores']['final_score']:.1f}",
            "Action": rec["recommended_action"].split(":")[0],
            "Confidence": rec["confidence"],
            "Signals": rec["signal_count"],
        })
    
    df_ranking = pd.DataFrame(ranking_data)
    
    # Color code by score
    def highlight_score(val):
        try:
            score = float(val)
            if score >= 75:
                return "background-color: #c6efce; color: #006100"
            elif score >= 60:
                return "background-color: #ffeb9c; color: #9c6500"
            else:
                return "background-color: #fccccb; color: #9c0000"
        except:
            return ""
    
    st.dataframe(
        df_ranking.style.applymap(highlight_score, subset=["Score"]),
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()
    
    # Score distribution chart
    scores = [r["scores"]["final_score"] for r in recommendations]
    
    fig = px.histogram(
        x=scores,
        nbins=10,
        labels={"x": "Final Score", "y": "Count"},
        title="Distribution of Recommendation Scores"
    )
    fig.update_traces(marker_color="#667eea")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 2: SCORING BREAKDOWN
# ============================================================================

with tab2:
    st.subheader("Detailed Scoring Analysis")
    
    # Select opportunity to analyze
    opportunity_names = [r["opportunity"] for r in recommendations]
    selected_idx = st.selectbox(
        "Select an opportunity to analyze:",
        range(len(opportunity_names)),
        format_func=lambda i: f"#{recommendations[i]['rank']} - {recommendations[i]['opportunity'][:60]}"
    )
    
    rec = recommendations[selected_idx]
    scores = rec["scores"]
    
    st.subheader(f"🎯 {rec['opportunity']}")
    
    # Main score highlight
    col1, col2, col3 = st.columns(3)
    
    with col1:
        final_score = scores["final_score"]
        score_class = "score-high" if final_score >= 75 else "score-medium" if final_score >= 60 else "score-low"
        st.markdown(f"""
        <div class="metric-card {score_class}">
            <div class="metric-value">{final_score:.1f}</div>
            <div class="metric-label">Final Score (0-100)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        confidence_colors = {
            "high": "🟢",
            "medium-high": "🟡",
            "medium": "🟡",
            "medium-low": "🟠",
            "low": "🔴"
        }
        conf = rec["confidence"]
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{confidence_colors.get(conf, '❓')} {conf.upper()}</div>
            <div class="metric-label">Confidence Level</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        action = rec["recommended_action"].split(":")[0]
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{action}</div>
            <div class="metric-label">Recommended Action</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Scoring dimensions breakdown
    st.subheader("📊 Scoring Dimensions (8 Factors)")
    
    dimensions = [
        ("Evidence Strength", scores["evidence_strength"], "Quality of sources and confidence"),
        ("Cross-Source Validation", scores["cross_source_validation"], "Diversity of signal types and markets"),
        ("Trend Momentum", scores["trend_momentum"], "Signal-level trend strength"),
        ("Swiss/DACH Transferability", scores["swiss_dach_transferability"], "Regional relevance and fit"),
        ("Commercial Potential", scores["commercial_potential"], "Market viability and margin potential"),
        ("Current Gap Fit", scores["current_assortment_gap_fit"], "Matches current assortment gaps"),
        ("Strategic Gap Fit", scores["strategic_gap_fit"], "Aligns with strategic expansion"),
        ("Company Profile Fit", scores["company_profile_fit"], "Fits company positioning and constraints"),
    ]
    
    weights = [0.18, 0.12, 0.12, 0.16, 0.10, 0.10, 0.12, 0.10]
    
    # Create radar chart
    fig = go.Figure()
    
    dimension_names = [d[0] for d in dimensions]
    dimension_scores = [d[1] for d in dimensions]
    
    fig.add_trace(go.Scatterpolar(
        r=dimension_scores,
        theta=dimension_names,
        fill='toself',
        name='Score',
        line_color='#667eea',
        fillcolor='rgba(102, 126, 234, 0.3)'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10)
            )
        ),
        title="Scoring Dimensions Breakdown",
        showlegend=False,
        height=500
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Detailed dimension scores
    st.markdown("#### Individual Dimension Scores")
    
    for i, (name, score, description) in enumerate(dimensions):
        weight = weights[i]
        contribution = score * weight / 100
        
        col1, col2, col3 = st.columns([2, 1, 2])
        
        with col1:
            st.write(f"**{name}**")
            st.caption(description)
        
        with col2:
            st.metric("Score", f"{score:.1f}")
        
        with col3:
            st.metric("Weight", f"{weight:.0%}")
            st.caption(f"Contributes: {contribution:.1f} pts")

# ============================================================================
# TAB 3: ANALYTICS DEEP DIVE
# ============================================================================

with tab3:
    st.subheader("🔬 Analytics Insights (Clustering, Trends, Saturation)")
    
    # Select opportunity
    opportunity_names = [r["opportunity"] for r in recommendations]
    selected_idx = st.selectbox(
        "Select opportunity for analytics:",
        range(len(opportunity_names)),
        format_func=lambda i: f"#{recommendations[i]['rank']} - {recommendations[i]['opportunity'][:60]}",
        key="analytics_select"
    )
    
    rec = recommendations[selected_idx]
    analytics = rec.get("analytics", {})
    
    if not analytics:
        st.warning("No analytics data available for this opportunity.")
        st.stop()
    
    st.subheader(f"Analytics: {rec['opportunity']}")
    
    # Analytics metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        trend = analytics.get("trend", "unknown")
        trend_emoji = "📈" if trend == "accelerating" else "📉" if trend == "decelerating" else "➡️"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{trend_emoji}</div>
            <div class="metric-label">Trend: {trend.upper()}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        saturation = analytics.get("saturation", "unknown")
        sat_emoji = "🌱" if saturation == "low" else "🌳" if saturation == "medium" else "🌲"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{sat_emoji}</div>
            <div class="metric-label">Saturation: {saturation.upper()}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        diversity = analytics.get("diversity", 0.5)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{diversity:.2f}</div>
            <div class="metric-label">Diversity Score (0-1)</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        quality = analytics.get("source_quality", 0.5)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{quality:.2f}</div>
            <div class="metric-label">Source Quality (0-1)</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # Analytics breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Signal Clustering")
        clustering = analytics.get("clustering", {})
        clusters = clustering.get("clusters", 0)
        signal_count = rec.get("signal_count", 1)
        
        st.metric("Signal Groups", clusters)
        st.metric("Total Signals", signal_count)
        st.caption(f"Deduplication: {clusters} unique cluster(s) from {signal_count} signal(s)")
        
        if clusters > 0 and signal_count > clusters:
            dedup_ratio = (signal_count - clusters) / signal_count * 100
            st.success(f"✅ Removed {dedup_ratio:.0f}% duplicate signals")
    
    with col2:
        st.subheader("🌍 Geographic Analysis")
        geography = analytics.get("geography", "unknown")
        
        st.metric("Geographic Focus", geography.upper())
        
        if geography == "ch_focused":
            st.success("✅ Strong CH signal concentration")
        elif geography == "dach_focused":
            st.info("ℹ️ DACH-wide signal coverage")
        else:
            st.warning("⚠️ Global signals - CH relevance uncertain")
    
    st.divider()
    
    # Analytics adjustment explanation
    adjustment = rec.get("analytics_adjustment", {})
    
    if adjustment:
        st.subheader("🎯 Score Adjustments Applied")
        
        for factor, change in adjustment.items():
            if change:
                st.markdown(f"""
                <div class="insight-box">
                    <div class="insight-title">{factor}</div>
                    {change}
                </div>
                """, unsafe_allow_html=True)
    
    # Anomalies
    anomaly_list = analytics.get("anomaly_list", [])
    
    if anomaly_list:
        st.subheader("⚠️ Detected Anomalies")
        for anomaly in anomaly_list:
            st.warning(f"**{anomaly.get('anomaly_type')}**: {anomaly.get('reason')}")
    else:
        st.success("✅ No anomalies detected - consistent signal patterns")

# ============================================================================
# TAB 4: INSIGHTS & EXPLANATIONS
# ============================================================================

with tab4:
    st.subheader("💡 Understanding Your Results")
    
    # Methodology explanation
    st.markdown("### How Scoring Works")
    
    st.markdown("""
    Your scores are calculated using **8 dimensions** weighted by business importance:
    
    1. **Evidence Strength (18%)** - Quality and credibility of sources
       - High = multiple credible sources with high confidence
       - Low = single weak source with low confidence
    
    2. **Cross-Source Validation (12%)** - Diversity of evidence
       - High = signals from web, social, marketplace, competitors
       - Low = all signals from one type (e.g., only Reddit)
    
    3. **Trend Momentum (12%)** - Signal-level trend strength
       - High = signals have high emerging scores (0.8+)
       - Low = signals are weak indicators (0.4-)
    
    4. **Swiss/DACH Transferability (16%)** - Regional fit
       - High = signals from CH/DACH with outdoor/outdoor use-case relevance
       - Low = global signals with unclear CH applicability
    
    5. **Commercial Potential (10%)** - Market viability
       - High = competitor activity, pricing data, brand mentions
       - Low = soft signals with no commercial validation
    
    6. **Current Gap Fit (10%)** - Matches existing gaps
       - High = overlaps with stated assortment gaps
       - Low = doesn't align with current strategy
    
    7. **Strategic Gap Fit (12%)** - Aligns with future plans
       - High = matches expansion focus and timeline
       - Low = doesn't support strategic direction
    
    8. **Company Profile Fit (10%)** - Overall alignment
       - High = matches positioning, segments, margins, innovation appetite
       - Low = conflicts with company constraints
    """)
    
    st.divider()
    
    # Analytics explanations
    st.markdown("### Analytics Layer Adjustments")
    
    st.markdown("""
    After deterministic scoring, we apply **real data science analysis** to refine scores:
    
    **Signal Clustering** 🎯
    - Groups similar signals to avoid double-counting
    - Example: "ultralight packs" + "lightweight modular packs" = same cluster
    - Score impact: Prevents inflated scores from duplicates
    
    **Trend Velocity** 📈
    - Measures if a trend is accelerating or decelerating
    - Accelerating (+15%) = growing momentum
    - Decelerating (-15%) = fading interest
    - Unknown (0%) = insufficient timestamp data
    
    **Market Saturation** 🌳
    - Counts unique brands and calculates market concentration
    - Low saturation (+10%) = greenfield opportunity, few competitors
    - High saturation (-10%) = crowded market, harder to differentiate
    
    **Source Quality** ⭐
    - Weights by credibility: Web (0.9) > Marketplace (0.8) > Reddit (0.6) > Manual (0.4)
    - High quality (+5%) = trustworthy evidence
    - Low quality (-15%) = unverified claims
    
    **Signal Diversity** 🌈
    - Measures variety of keywords, brands, sources
    - High diversity (+5%) = robust, multi-faceted trend
    - Low diversity (-10%) = single-source hype
    
    **Geographic Concentration** 🗺️
    - Is trend CH-focused, DACH-wide, or global?
    - CH/DACH focus (+8%) = directly applicable
    - Global signals = harder to validate locally
    
    **Anomaly Detection** 🚨
    - Flags unusual signals (high engagement, outlier prices, market spikes)
    - Helps identify genuine breakthroughs vs. noise
    """)
    
    st.divider()
    
    # Action guidance
    st.markdown("### Recommended Actions")
    
    st.markdown("""
    Based on your scores, we suggest:
    
    | Score | Confidence | Action | Rationale |
    |-------|-----------|--------|-----------|
    | 84+ | High | **Launch** | Strong evidence, good fit, clear strategic alignment |
    | 68-84 | Medium-High | **Test** | Run small pilot, validate demand before scaling |
    | 55-68 | Medium | **Monitor** | Collect more evidence, reassess quarterly |
    | <55 | Low | **Ignore** | Evidence or fit too weak for action now |
    
    **Other Actions:**
    - **Contact Supplier/Brand** - When emerging brand/supplier warrants outreach
    - **Reposition Assortment** - Shift existing SKUs toward opportunity
    """)
    
    st.divider()
    
    # Known limitations
    st.markdown("### Known Limitations")
    
    st.info("""
    ✓ **What we do well:**
    - Detect emerging trends from public signals
    - Identify strategic gaps vs. current assortment
    - Assess Swiss/DACH transferability
    - Provide reproducible, auditable scoring
    
    ⚠️ **What we can't do:**
    - Access internal sales/margin data
    - Guarantee supplier availability or terms
    - Predict customer demand with certainty
    - Account for exclusive partnerships
    """)
    
    st.markdown("""
    **Always** review recommendations with your buying team before acting.
    These are decision-support tools, not final recommendations.
    """)

# ============================================================================
# FOOTER
# ============================================================================

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📥 Export Results as JSON"):
        st.download_button(
            label="Download recommendations.json",
            data=json.dumps(data, indent=2),
            file_name="recommendations.json",
            mime="application/json"
        )

with col2:
    if st.button("🔄 Run New Analysis"):
        st.info("Go to the main chat interface to run a new analysis.")

with col3:
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

st.markdown("""
<div style='text-align: center; color: #888; font-size: 11px; margin-top: 20px;'>
    <strong>Zenline Analytics Dashboard</strong> • Powered by Claude AI<br>
    Evidence-based decision support for outdoor retail
</div>
""", unsafe_allow_html=True)
