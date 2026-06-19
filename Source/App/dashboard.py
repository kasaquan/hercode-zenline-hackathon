"""
Streamlit Dashboard: Outdoor Retail Recommender System
Flow: Company Profile Extraction (Agent 3) → Signal Analysis (Agent 2)
"""

# Load environment variables from .env FIRST
from dotenv import load_dotenv
import os
load_dotenv()

import streamlit as st
import json
import sys
from pathlib import Path

# Add parent directory (Source root) to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from Agents.agent_3 import extract_company_profile, format_profile_for_display

st.set_page_config(
    page_title="Outdoor Retail Recommender",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏔️ Outdoor Retail Recommender System")
st.markdown("Extract company profile → Analyze emerging signals → Personalize recommendations")

# Sidebar for navigation
st.sidebar.header("Navigation")
page = st.sidebar.radio("Select module:", ["Company Profiler (Agent 3)", "Signal Analyzer (Agent 2)", "Dashboard"])

# ============================================================================
# PAGE 1: Company Profiler (Agent 3)
# ============================================================================

if page == "Company Profiler (Agent 3)":
    st.header("1️⃣ Extract Company Profile")
    st.markdown("""
    Provide company information (website + optional strategy document) to extract a structured profile.
    Agent 3 will infer strategic gaps if a strategy document is provided.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Company Information")
        company_link = st.text_input(
            "Company Website URL",
            value="https://www.decathlon.ch",
            placeholder="https://www.example-outdoor.ch"
        )
        
        company_notes = st.text_area(
            "Additional Context (optional)",
            placeholder="E.g., 'Premium positioning, 12 stores, high innovation appetite'",
            height=100
        )
    
    with col2:
        st.subheader("Strategy Document (optional)")
        uploaded_pdf = st.file_uploader(
            "Upload strategy PDF or text",
            type=["pdf", "txt"],
            help="Executive vision, roadmap, expansion plans"
        )
        
        # If no file, offer manual input
        if not uploaded_pdf:
            st.info("Or paste strategy text directly:")
            pdf_content = st.text_area(
                "Strategy text",
                placeholder="E.g., 'Strategic expansion: Ultralight systems by Q3 2026...'",
                height=150,
                key="strategy_text"
            )
        else:
            # Simple text extraction (not full PDF parsing)
            if uploaded_pdf.type == "text/plain":
                pdf_content = uploaded_pdf.read().decode("utf-8")
            else:
                pdf_content = f"[PDF uploaded: {uploaded_pdf.name}]"
            st.success(f"✓ Loaded: {uploaded_pdf.name}")
    
    # Extract button
    if st.button("🔍 Extract Company Profile", type="primary", use_container_width=True):
        if not company_link:
            st.error("Please enter a company website URL")
        else:
            with st.spinner("Agent 3 is extracting profile..."):
                try:
                    profile = extract_company_profile(
                        company_link=company_link,
                        pdf_content=pdf_content if pdf_content else None,
                        user_notes=company_notes if company_notes else None,
                        verbose=True
                    )
                    
                    # Store in session state for Agent 2
                    st.session_state.company_profile = profile
                    st.session_state.company_link = company_link
                    
                    # Check for errors
                    if "error" in profile:
                        st.error(f"Extraction failed: {profile.get('error')}")
                    else:
                        st.success("✓ Profile extracted successfully!")
                        
                        # Display profile in tabs
                        tab1, tab2, tab3 = st.tabs(["Overview", "Raw JSON", "Strategic Analysis"])
                        
                        with tab1:
                            col_a, col_b = st.columns(2)
                            
                            with col_a:
                                st.metric("Company", profile.get("company_name", "N/A"))
                                st.metric("Positioning", profile.get("positioning", "N/A"))
                                st.metric("Markets", ", ".join(profile.get("active_markets", [])))
                                st.metric("Innovation Appetite", profile.get("innovation_appetite", "N/A"))
                            
                            with col_b:
                                st.metric("Stores", profile.get("store_count", "N/A"))
                                st.metric("Price Band", profile.get("target_price_band", "N/A"))
                                st.metric("Margin Target", profile.get("target_gross_margin", "N/A"))
                                st.metric("Distribution", profile.get("distribution_model", "N/A"))
                            
                            st.subheader("Customer Segments")
                            segments = profile.get("customer_segments", [])
                            st.write(", ".join(segments) if segments else "Not specified")
                            
                            st.subheader("Current Assortment")
                            categories = profile.get("current_product_categories", [])
                            st.write(", ".join(categories) if categories else "Not specified")
                            
                            st.subheader("Current Gaps")
                            st.write(profile.get("current_assortment_gaps", "None identified"))
                        
                        with tab2:
                            st.code(format_profile_for_display(profile), language="json")
                        
                        with tab3:
                            if profile.get("strategic_expansion_focus"):
                                st.info("📊 Strategic Direction Detected")
                                st.write(f"**Focus:** {profile.get('strategic_expansion_focus')}")
                                st.write(f"**Timeline:** {profile.get('strategic_timeline', 'Not specified')}")
                                st.write(f"**Rationale:** {profile.get('strategic_rationale', 'Not specified')}")
                                
                                st.subheader("Strategic Gaps (Inferred)")
                                st.write(profile.get("strategic_assortment_gaps", "None identified"))
                                st.markdown("""
                                **Interpretation for Agent 2:** These gaps represent opportunities aligned with 
                                the company's strategic direction. Signals matching these gaps should score higher.
                                """)
                            else:
                                st.info("No strategic expansion data provided. Focus on current gaps.")
                        
                        # Show confidence
                        if "confidence_by_field" in profile:
                            with st.expander("Field Confidence Levels"):
                                st.json(profile["confidence_by_field"])
                
                except Exception as e:
                    st.error(f"Error: {str(e)}")


# ============================================================================
# PAGE 2: Signal Analyzer (Agent 2 Skeleton)
# ============================================================================

elif page == "Signal Analyzer (Agent 2)":
    st.header("2️⃣ Analyze Emerging Signals")
    st.markdown("Signals are potential opportunities sourced by Agent 1. Analyze & personalize using company profile.")
    
    # Check if profile exists
    if "company_profile" not in st.session_state:
        st.warning("⚠️ Please extract a company profile first (Agent 3 tab)")
        st.info("Agent 2 will use the company profile to contextualize signals.")
    else:
        profile = st.session_state.company_profile
        st.success(f"✓ Profile loaded: {profile.get('company_name', 'Unknown')}")
        
        # Sample signals (Agent 1 output)
        sample_signals = [
            {
                "signal_name": "Ultralight day-hike kits",
                "signal_type": "web",
                "market": "CH/DE",
                "product_name": "Modular ultralight pack system",
                "price": 250,
                "url": "https://example.com/signal1",
                "confidence": 0.78,
                "notes": "Growing Reddit discussion, Kickstarter projects emerging"
            },
            {
                "signal_name": "Sustainable recycled nylon shells",
                "signal_type": "retail",
                "market": "CH",
                "product_name": "Recycled shell jackets",
                "price": 180,
                "url": "https://example.com/signal2",
                "confidence": 0.85,
                "notes": "Decathlon launched; competitor analysis shows trend"
            },
            {
                "signal_name": "Modular pack customization",
                "signal_type": "social",
                "market": "DACH",
                "product_name": "Build-your-own pack kits",
                "price": 200,
                "url": "https://example.com/signal3",
                "confidence": 0.72,
                "notes": "TikTok creator unboxing, rising interest in customization"
            }
        ]
        
        st.subheader("Emerging Signals (from Agent 1)")
        
        for i, signal in enumerate(sample_signals):
            with st.expander(f"Signal {i+1}: {signal['signal_name']} ({signal['confidence']:.0%} confidence)"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Type", signal["signal_type"])
                    st.metric("Market", signal["market"])
                
                with col2:
                    st.metric("Price (CHF)", signal.get("price", "N/A"))
                    st.metric("Confidence", f"{signal['confidence']:.0%}")
                
                with col3:
                    st.metric("Source", "Link")
                    st.write(signal.get("notes", ""))
                
                # Agent 2 analysis skeleton
                st.divider()
                st.markdown("**Agent 2 Analysis (ready to build):**")
                
                # This is where Agent 2 logic would go
                if "ultralight" in signal["signal_name"].lower():
                    if "ultralight" in profile.get("strategic_expansion_focus", "").lower():
                        st.success("✅ Strong strategic alignment - matches expansion focus")
                    elif "ultralight" in profile.get("strategic_assortment_gaps", "").lower():
                        st.success("✅ Fills strategic gap - needed for expansion plan")
                    elif "ultralight" in profile.get("current_assortment_gaps", "").lower():
                        st.info("ℹ️ Fills current gap - immediate opportunity")
                    else:
                        st.warning("⚠️ No clear gap match - assess custom fit")
                
                st.button(f"Analyze signal {i+1} with Agent 2", key=f"analyze_{i}")


# ============================================================================
# PAGE 3: Dashboard
# ============================================================================

elif page == "Dashboard":
    st.header("📊 Recommender System Status")
    st.markdown("Overview of the complete pipeline.")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Agent 1", "Sourcing", delta="Ready")
    
    with col2:
        if "company_profile" in st.session_state:
            st.metric("Agent 3", "Profile Extracted", delta="✓")
        else:
            st.metric("Agent 3", "Awaiting Input", delta="⏳")
    
    with col3:
        st.metric("Agent 2", "Signal Analysis", delta="Ready")
    
    st.divider()
    
    st.subheader("System Architecture")
    st.markdown("""
    ```
    Agent 1: Sourcing
    ├─ Reddit, Kickstarter, Decathlon feeds
    ├─ Social media trends
    └─ → Outputs: Signals (opportunities)
    
    Agent 3: Company Profiling
    ├─ Website extraction
    ├─ Strategy document analysis
    └─ → Outputs: Structured company profile
    
    Agent 2: Signal Analysis & Personalization
    ├─ Matches signals to company gaps (current + strategic)
    ├─ Scores relevance, feasibility, strategic fit
    └─ → Outputs: Ranked, actionable recommendations
    
    Dashboard: Visualization & Decision Support
    └─ Shows signals, profiles, recommendations
    ```
    """)
    
    if "company_profile" in st.session_state:
        st.subheader("Current Company Profile")
        profile = st.session_state.company_profile
        st.json({
            "company_name": profile.get("company_name"),
            "positioning": profile.get("positioning"),
            "active_markets": profile.get("active_markets"),
            "strategic_focus": profile.get("strategic_expansion_focus"),
            "strategic_timeline": profile.get("strategic_timeline")
        })


# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown("""
**Outdoor Retail Recommender System** • Built with Streamlit + Claude API
- Agent 1: Sources emerging opportunities
- Agent 3: Extracts & profiles companies  
- Agent 2: Personalizes signals to company fit
""")
