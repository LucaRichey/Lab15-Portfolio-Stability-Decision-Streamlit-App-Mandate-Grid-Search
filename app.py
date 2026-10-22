"""
app.py — Portfolio Stability Decision & Lowest-Risk Allocation App

Built for FIN 43900 (AI Finance Applications, Purdue University)
Session 15: Portfolio Stability Decision
Student: Luca Richey

Imports optimization and estimation functions and Meridian inputs directly
from portfolio.py (reusing engine math without duplicate calculations).
"""

import sys
import os
import subprocess

# Auto-launcher: if the user clicks the "Run" button in VS Code / IDE (or runs `python app.py`),
# this automatically detects that it's outside Streamlit, finds the Python environment
# with Streamlit installed, and launches `streamlit run app.py`.
def _ensure_streamlit_runner():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is not None:
            return  # Already running inside Streamlit server, proceed normally
    except Exception:
        pass

    candidates = [
        sys.executable,
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3",
        "python3",
    ]
    chosen_python = None
    for p in candidates:
        try:
            res = subprocess.run([p, "-c", "import streamlit"], capture_output=True)
            if res.returncode == 0:
                chosen_python = p
                break
        except Exception:
            continue

    if not chosen_python:
        chosen_python = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"

    print("=" * 70)
    print("  LAUNCHING STREAMLIT WEB APP VIA:", chosen_python)
    print("  Your browser will open automatically at: http://localhost:8501")
    print("=" * 70)

    cmd = [
        chosen_python,
        "-m",
        "streamlit",
        "run",
        os.path.abspath(__file__),
        "--browser.gatherUsageStats",
        "false",
    ]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    sys.exit(0)

if __name__ == "__main__":
    _ensure_streamlit_runner()

import importlib
import math
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd

# Always reload portfolio to pick up on-the-fly edits (e.g. correlation matrix test)
import portfolio
importlib.reload(portfolio)

from portfolio import (
    SLEEVES,
    CORRELATION_MATRIX,
    OBJECTIVE_RETURN,
    build_covariance_matrix,
    portfolio_return,
    portfolio_volatility,
    reserve_eligible_weight,
    search_lowest_risk_mix,
    estimate_from_prices,
)

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & HEADER
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Portfolio Stability & Risk Engine",
    page_icon="⚖️",
    layout="wide",
)

st.title("Portfolio Stability & Risk Engine")
st.markdown("*built with AI help, a learning demonstration, not investment advice.*")

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.header("Mandate & Universe Controls")

# Objective (start 6.5%)
objective_input = st.sidebar.number_input(
    "Return Objective (%):",
    min_value=0.0,
    max_value=30.0,
    value=float(OBJECTIVE_RETURN),
    step=0.1,
    format="%.2f",
    help="Target minimum annualized expected return (e.g. CPI + 4.0% = 6.50%).",
)

# Reserve minimum (start 3%)
reserve_min_input = st.sidebar.number_input(
    "Reserve Minimum (%):",
    min_value=0.0,
    max_value=100.0,
    value=3.0,
    step=0.5,
    format="%.1f",
    help="Minimum required weight allocated to reserve-eligible liquid assets.",
)

# Upload for prices.csv
uploaded_file = st.sidebar.file_uploader(
    "Upload prices.csv",
    type=["csv"],
    help="Upload monthly prices CSV (Date first, oldest first, one column per ticker).",
)

# Last-36-months switch
use_last_36 = st.sidebar.checkbox(
    "Use last 36 months only",
    value=False,
    help="Estimate annualized mean returns, volatilities, and correlations from the last 36 monthly returns.",
)

# -----------------------------------------------------------------------------
# LOAD BASELINE & ACTIVE INPUTS
# -----------------------------------------------------------------------------
# Mode A: Meridian Training Universe (Default when no file uploaded)
# Mode B: Uploaded CSV Universe
is_csv_mode = uploaded_file is not None

if not is_csv_mode:
    universe_label = "Meridian Training Universe (4 Sleeves)"
    asset_names = [s["name"] for s in SLEEVES]
    asset_shorts = [s["short_name"] for s in SLEEVES]
    default_returns = [float(s["expected_return"]) for s in SLEEVES]
    default_vols = [float(s["volatility"]) for s in SLEEVES]
    default_reserve_flags = [bool(s["reserve_eligible"]) for s in SLEEVES]
    
    # Meridian loaded covariance
    base_cov_matrix = build_covariance_matrix(CORRELATION_MATRIX, default_vols)
    current_cov_matrix = base_cov_matrix

    # As Loaded baseline inputs
    loaded_returns = default_returns[:]
    loaded_reserve_flags = default_reserve_flags[:]
    loaded_objective = float(OBJECTIVE_RETURN)
    loaded_min_reserve = 3.0
    loaded_cov = base_cov_matrix

else:
    universe_label = f"Uploaded CSV Universe ({uploaded_file.name})"
    
    # 1. Baseline estimation on ALL MONTHS (inputs as loaded)
    uploaded_file.seek(0)
    base_est = estimate_from_prices(uploaded_file, last_36=False)
    raw_tickers = base_est["tickers"]

    if len(raw_tickers) > 6:
        st.warning(
            f"⚠️ **Uploaded CSV contains {len(raw_tickers)} assets.**\n\n"
            f"The mandate requires a universe of **3 to 6 assets** (evaluating 5-point discrete steps on {len(raw_tickers)} assets "
            f"would generate over 41 quadrillion combinations). Please select between 3 and 6 assets to optimize below:"
        )
        selected_tickers = st.multiselect(
            "Select 3 to 6 assets to include:",
            options=raw_tickers,
            default=raw_tickers[:min(len(raw_tickers), 5)],
            max_selections=6,
        )
        if len(selected_tickers) < 2:
            st.error("Please select at least 2 assets to run optimization.")
            st.stop()
    else:
        selected_tickers = raw_tickers

    # Filter base_est to selected_tickers
    sel_indices = [raw_tickers.index(t) for t in selected_tickers]
    asset_shorts = selected_tickers
    asset_names = [f"Ticker {t}" for t in asset_shorts]
    base_all_returns = [round(base_est["expected_returns"][idx], 2) for idx in sel_indices]
    base_all_vols = [round(base_est["volatilities"][idx], 2) for idx in sel_indices]
    base_cov_matrix = [[base_est["cov_matrix"][r][c] for c in sel_indices] for r in sel_indices]
    
    # Default reserve flags for CSV tickers:
    def is_likely_reserve(ticker: str) -> bool:
        t_up = ticker.upper()
        return any(k in t_up for k in ["BIL", "IEF", "SHV", "SGOV", "TBIL", "CASH", "GOVT"])
    
    default_reserve_flags = [is_likely_reserve(t) for t in asset_shorts]

    # As Loaded baseline inputs (all months, default 6.5% objective, 3.0% reserve)
    loaded_returns = base_all_returns[:]
    loaded_reserve_flags = default_reserve_flags[:]
    loaded_objective = float(objective_input)
    loaded_min_reserve = float(reserve_min_input)
    loaded_cov = base_cov_matrix

    # 2. Current estimation (either all months or last 36 months)
    if use_last_36:
        uploaded_file.seek(0)
        curr_est = estimate_from_prices(uploaded_file, last_36=True)
        default_returns = [round(curr_est["expected_returns"][idx], 2) for idx in sel_indices]
        default_vols = [round(curr_est["volatilities"][idx], 2) for idx in sel_indices]
        current_cov_matrix = [[curr_est["cov_matrix"][r][c] for c in sel_indices] for r in sel_indices]
    else:
        default_returns = base_all_returns[:]
        default_vols = base_all_vols[:]
        current_cov_matrix = base_cov_matrix

# -----------------------------------------------------------------------------
# PAGE INPUT CONTROLS: EDITABLE RETURNS & RESERVE CHECKBOXES
# -----------------------------------------------------------------------------
st.subheader(f"Asset Inputs: {universe_label}")
if is_csv_mode:
    window_str = "Last 36 Months" if use_last_36 else "All Available Months"
    st.info(f"Loaded {len(asset_shorts)} assets from CSV using **{window_str}** parameter window.")

# Responsive grid layout: up to 4 assets per row
num_per_row = min(len(asset_shorts), 4)
edited_returns: List[float] = [0.0] * len(asset_shorts)
edited_reserve_flags: List[bool] = [False] * len(asset_shorts)

# Unique state key prefix based on data mode and 36-month toggle
state_prefix = f"{'csv' if is_csv_mode else 'meridian'}_{'36' if use_last_36 else 'all'}"

for row_start in range(0, len(asset_shorts), num_per_row):
    row_tickers = asset_shorts[row_start : row_start + num_per_row]
    cols = st.columns(len(row_tickers))
    for j, short in enumerate(row_tickers):
        idx = row_start + j
        with cols[j]:
            st.markdown(f"**{short}**")
            st.caption(f"{asset_names[idx]}")
            
            # Editable expected return box
            ret_val = st.number_input(
                "Expected Return (%)",
                value=float(default_returns[idx]),
                step=0.1,
                format="%.2f",
                key=f"{state_prefix}_ret_{short}_{idx}",
            )
            edited_returns[idx] = ret_val
            
            # Tick box per asset for reserve-eligible
            res_val = st.checkbox(
                "Reserve-eligible",
                value=bool(default_reserve_flags[idx]),
                key=f"{state_prefix}_res_{short}_{idx}",
            )
            edited_reserve_flags[idx] = res_val
            
            # Display standalone volatility for user reference
            st.caption(f"Vol: {default_vols[idx]:.2f}%")

st.divider()

# -----------------------------------------------------------------------------
# ENGINE SOLVER: AS LOADED vs CURRENT / EDITED
# -----------------------------------------------------------------------------

# 1. Solve "As Loaded" allocation
loaded_sol = search_lowest_risk_mix(
    expected_returns=loaded_returns,
    cov_matrix=loaded_cov,
    reserve_flags=loaded_reserve_flags,
    objective_return=loaded_objective,
    min_reserve=loaded_min_reserve,
    step_pct=5.0,
)

# 2. Solve "Current / Edited" allocation
current_sol = search_lowest_risk_mix(
    expected_returns=edited_returns,
    cov_matrix=current_cov_matrix,
    reserve_flags=edited_reserve_flags,
    objective_return=float(objective_input),
    min_reserve=float(reserve_min_input),
    step_pct=5.0,
)

# -----------------------------------------------------------------------------
# RESULTS DISPLAY & COMPARISON
# -----------------------------------------------------------------------------
st.subheader("Optimization Results & Stability Analysis")

col_loaded, col_current = st.columns(2)

with col_loaded:
    baseline_title = "Meridian Baseline (As Loaded)" if not is_csv_mode else "CSV Baseline (All Months, As Loaded)"
    st.markdown(f"### {baseline_title}")
    if loaded_sol is not None:
        weights_str = " / ".join(f"{w:.0f}" for w in loaded_sol["weights_pct"])
        st.metric(
            label=f"Mix ({' / '.join(asset_shorts)})",
            value=weights_str,
        )
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Expected Return", f"{loaded_sol['expected_return']:.2f}%")
        m_col2.metric("Portfolio Volatility", f"{loaded_sol['volatility']:.2f}%")
        m_col3.metric("Reserve-Eligible", f"{loaded_sol['reserve_eligible_pct']:.1f}%")
        
        # Sleeve weights breakdown
        loaded_df = pd.DataFrame({
            "Asset": asset_shorts,
            "Weight (%)": [f"{w:.1f}%" for w in loaded_sol["weights_pct"]],
            "Reserve Eligible": ["Yes" if f else "No" for f in loaded_reserve_flags],
        })
        st.dataframe(loaded_df, hide_index=True)
    else:
        st.error("no mix meets the objective")
        st.caption("No combination in 5-point steps met both the objective return and reserve minimum.")

with col_current:
    st.markdown("### Current Allocation (Edited / Active Window)")
    if current_sol is not None:
        curr_weights_str = " / ".join(f"{w:.0f}" for w in current_sol["weights_pct"])
        st.metric(
            label=f"Mix ({' / '.join(asset_shorts)})",
            value=curr_weights_str,
        )
        c_col1, c_col2, c_col3 = st.columns(3)
        c_col1.metric("Expected Return", f"{current_sol['expected_return']:.2f}%")
        c_col2.metric("Portfolio Volatility", f"{current_sol['volatility']:.2f}%")
        c_col3.metric("Reserve-Eligible", f"{current_sol['reserve_eligible_pct']:.1f}%")
        
        # Sleeve weights breakdown
        curr_df = pd.DataFrame({
            "Asset": asset_shorts,
            "Weight (%)": [f"{w:.1f}%" for w in current_sol["weights_pct"]],
            "Reserve Eligible": ["Yes" if f else "No" for f in edited_reserve_flags],
        })
        st.dataframe(curr_df, hide_index=True)
    else:
        st.error("no mix meets the objective")
        st.caption("No combination in 5-point steps met both the objective return and reserve minimum.")

st.divider()

# -----------------------------------------------------------------------------
# LARGEST WEIGHT CHANGE (ESTIMATION SENSITIVITY)
# -----------------------------------------------------------------------------
st.subheader("Stability Check: Largest Weight Change")

if loaded_sol is not None and current_sol is not None:
    w_loaded = loaded_sol["weights_pct"]
    w_curr = current_sol["weights_pct"]
    diffs = [c - l for l, c in zip(w_loaded, w_curr)]
    abs_diffs = [abs(d) for d in diffs]
    max_change = max(abs_diffs)
    max_idx = abs_diffs.index(max_change)
    max_asset = asset_shorts[max_idx]

    # Prominent callout
    if max_change > 0:
        st.warning(
            f"**Largest weight change: {max_change:.1f} points** ({max_asset}: "
            f"{w_loaded[max_idx]:.0f}% → {w_curr[max_idx]:.0f}%). "
            f"A one-point change in an estimate moved {max_change:.1f} points of capital."
        )
    else:
        st.success("**Largest weight change: 0.0 points.** Current inputs produce the exact baseline allocation.")

    # Side-by-side comparison table
    comp_df = pd.DataFrame({
        "Asset": asset_shorts,
        "As Loaded (%)": [f"{w:.1f}" for w in w_loaded],
        "Current (%)": [f"{w:.1f}" for w in w_curr],
        "Change (points)": [f"{d:+.1f}" for d in diffs],
    })
    st.table(comp_df)

elif loaded_sol is None and current_sol is None:
    st.info("Neither the baseline nor current inputs produce a feasible mix meeting the objective.")
elif loaded_sol is None:
    st.info("Baseline has no mix meeting the objective; current inputs found a feasible allocation.")
else:
    st.error("Current inputs produce no mix meeting the objective (baseline had a feasible mix).")

# -----------------------------------------------------------------------------
# DIAGNOSTIC FOOTER
# -----------------------------------------------------------------------------
st.caption(
    "FIN 43900 Multi-Asset Optimization Engine | Discrete 5-Point Long-Only Grid Search | "
    "Reuses `portfolio.py` mathematical primitives."
)
