"""Retail Radar dashboard — Scout Agent sourced signals + the agent's reasoning trace.

Run:  streamlit run Source/Agents/scout_agent/dashboard.py
Reads the artifacts written by `python -m Source.Agents.scout_agent`.
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

# Artifacts live at <repo>/out regardless of where Streamlit is launched.
ROOT = Path(__file__).resolve().parents[3]

st.set_page_config(page_title="Outdoor Retail Radar — Scout", layout="wide")
st.title("🧭 Outdoor Retail Radar — Scout Agent")
st.caption("Real-world demand signals for a Swiss / DACH outdoor retailer, in the Signal Row contract shape.")

SIG = str(ROOT / "out" / "signals.csv")
TRACE = str(ROOT / "out" / "trace.json")

if not os.path.exists(SIG):
    st.warning("No output yet. Run:  `python -m Source.Agents.scout_agent --market DACH`")
    st.stop()

sig = pd.read_csv(SIG).fillna("")

tab1, tab2 = st.tabs(["Sourced signals", "Reasoning trace"])

with tab1:
    c1, c2, c3 = st.columns(3)
    c1.metric("Signals sourced", len(sig))
    c2.metric("Signal types", sig["signal_type"].nunique() if "signal_type" in sig else 0)
    c3.metric("Markets covered", sig["market"].nunique() if "market" in sig else 0)

    # Filters
    f1, f2 = st.columns(2)
    types = sorted(sig["signal_type"].unique()) if "signal_type" in sig else []
    markets = sorted(sig["market"].unique()) if "market" in sig else []
    pick_t = f1.multiselect("signal_type", types, default=types)
    pick_m = f2.multiselect("market", markets, default=markets)
    view = sig.copy()
    if pick_t:
        view = view[view["signal_type"].isin(pick_t)]
    if pick_m:
        view = view[view["market"].isin(pick_m)]

    st.dataframe(
        view.sort_values("signal_score", ascending=False) if "signal_score" in view else view,
        use_container_width=True,
        column_config={"url": st.column_config.LinkColumn("url")},
    )
    st.download_button("Download signals.csv", sig.to_csv(index=False), "signals.csv", "text/csv")

with tab2:
    if os.path.exists(TRACE):
        for ev in json.load(open(TRACE, encoding="utf-8")):
            kind = ev.get("kind")
            if kind == "thinking":
                st.markdown(f"🧠 *{ev['text']}*")
            elif kind == "text":
                st.markdown(ev["text"])
            elif kind == "tool_use":
                st.code(f"{ev['name']}({json.dumps(ev['input'])})", language="python")
            elif kind == "web_search":
                st.code(f"web_search({json.dumps(ev['input'])})", language="python")
    else:
        st.info("No trace.json found.")
