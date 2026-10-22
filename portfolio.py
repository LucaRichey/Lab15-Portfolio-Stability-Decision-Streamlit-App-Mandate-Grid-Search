"""
portfolio.py — Multi-Asset Portfolio Risk & Return Engine
Meridian Foundation Reserve Analysis

Author: Luca Richey
Course: FIN 43900 (AI Finance Applications, Purdue University)
Lab 14: Portfolio Baselines

Standard library only. Computes portfolio expected return, covariance matrix,
portfolio volatility, inverse-volatility weighting, and mandate reserve eligibility
entirely from editable inputs.
"""

import math
import sys
from typing import List, Dict, Tuple, Any, Optional, Union

# ==============================================================================
# EDITABLE INPUTS
# ==============================================================================

# Four asset sleeves with expected return and standalone volatility (in percent)
# and reserve eligibility according to Lab 13 mandate rules.
SLEEVES = [
    {
        "name": "Treasury bills",
        "short_name": "bills",
        "expected_return": 3.5,  # 3.5%
        "volatility": 0.5,       # 0.5%
        "reserve_eligible": True,
    },
    {
        "name": "Treasury 10-year note",
        "short_name": "10-year",
        "expected_return": 4.3,  # 4.3%
        "volatility": 7.0,       # 7.0%
        "reserve_eligible": True,
    },
    {
        "name": "Investment-grade bond fund",
        "short_name": "IG",
        "expected_return": 5.0,  # 5.0%
        "volatility": 6.0,       # 6.0%
        "reserve_eligible": False,
    },
    {
        "name": "Global equity index fund",
        "short_name": "equity",
        "expected_return": 8.0,  # 8.0%
        "volatility": 16.0,      # 16.0%
        "reserve_eligible": False,
    },
]

# Pairwise correlation matrix among the four sleeves:
# Order: [Bills, 10-year, IG bonds, Equity]
CORRELATION_MATRIX = [
    [1.00,  0.10,  0.05,  0.00],
    [0.10,  1.00,  0.80, -0.10],
    [0.05,  0.80,  1.00,  0.25],
    [0.00, -0.10,  0.25,  1.00],
]

# Investment Objective Return (in percent)
# CPI + 4.0%, with CPI estimated at 2.5% -> 6.50%
OBJECTIVE_RETURN = 6.5


# ==============================================================================
# VALIDATION ENGINE
# ==============================================================================

def validate_correlation_matrix(corr_matrix: List[List[float]], tolerance: float = 1e-6) -> None:
    """
    Validate that the correlation matrix is:
    1. Square and non-empty.
    2. Symmetrical: corr[i][j] == corr[j][i].
    3. Bounded: every correlation entry lies within [-1.0, 1.0].
    4. Unit diagonal: corr[i][i] == 1.0.

    Refuses execution by raising ValueError with a descriptive diagnostic message
    if any condition is violated.
    """
    n = len(corr_matrix)
    if n == 0:
        raise ValueError("Correlation matrix cannot be empty.")

    for i in range(n):
        if len(corr_matrix[i]) != n:
            raise ValueError(
                f"Correlation matrix must be square ({n}x{n}), but row {i} has length {len(corr_matrix[i])}."
            )

    # Check bounds and symmetry
    for i in range(n):
        for j in range(n):
            val = corr_matrix[i][j]
            if val < -1.0 - tolerance or val > 1.0 + tolerance:
                raise ValueError(
                    f"Invalid correlation value {val:.4f} at cell ({i}, {j}). "
                    f"All correlation values must lie strictly between -1.0 and +1.0. Refusing to run."
                )

            diff = abs(corr_matrix[i][j] - corr_matrix[j][i])
            if diff > tolerance:
                raise ValueError(
                    f"Correlation matrix is not symmetric: "
                    f"cell ({i}, {j}) = {corr_matrix[i][j]:.4f} != cell ({j}, {i}) = {corr_matrix[j][i]:.4f}. "
                    f"Difference = {diff:.6f}. Refusing to run."
                )

        # Diagonal check
        diag_diff = abs(corr_matrix[i][i] - 1.0)
        if diag_diff > tolerance:
            raise ValueError(
                f"Correlation diagonal at ({i}, {i}) must be 1.00, found {corr_matrix[i][i]:.4f}. Refusing to run."
            )


# ==============================================================================
# RISK & RETURN COMPUTATION ENGINE (REUSABLE FUNCTIONS)
# ==============================================================================

def build_covariance_matrix(
    corr_matrix: List[List[float]],
    volatilities: List[float]
) -> List[List[float]]:
    """
    Build the covariance matrix as Cov[i, j] = Correlation[i, j] * Volatility[i] * Volatility[j].

    If volatilities are supplied in percent (e.g. 6.0 and 16.0), the covariance
    entries are in percent-squared units (%^2).
    """
    n = len(volatilities)
    cov = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            cov[i][j] = corr_matrix[i][j] * volatilities[i] * volatilities[j]
    return cov


def normalize_weights(weights: List[float]) -> List[float]:
    """
    Normalize portfolio weights to decimal fractions summing to 1.0.
    Accepts weights entered as percentages (e.g. [40.0, 60.0]) or decimals (e.g. [0.4, 0.6]).
    """
    total = sum(weights)
    if total <= 0:
        raise ValueError(f"Total weight sum must be positive, got {total}.")
    return [w / total for w in weights]


def compute_equal_weights(n: int) -> List[float]:
    """
    Compute equal weights for n assets: each weight = 1.0 / n (in decimal fraction).
    """
    if n <= 0:
        raise ValueError(f"Number of assets n must be positive, got {n}.")
    return [1.0 / n] * n


def compute_inverse_volatility_weights(volatilities: List[float]) -> List[float]:
    """
    Compute inverse-volatility weights:
    Each weight is proportional to 1 / volatility_i, scaled so that sum(weights) = 1.0.
    """
    inverses = []
    for v in volatilities:
        if v <= 0:
            raise ValueError(f"Volatility must be strictly positive for inverse-volatility weighting, got {v}.")
        inverses.append(1.0 / v)
    total_inverse = sum(inverses)
    return [inv / total_inverse for inv in inverses]


def portfolio_return(weights: List[float], expected_returns: List[float]) -> float:
    """
    Compute expected portfolio return:
    E[R_p] = sum_i (w_i * E[R_i])

    Weights are converted to fractions summing to 1.0.
    Returns portfolio expected return in percent.
    """
    w_norm = normalize_weights(weights)
    return sum(w * r for w, r in zip(w_norm, expected_returns))


def portfolio_variance(weights: List[float], cov_matrix: List[List[float]]) -> float:
    """
    Compute portfolio variance from weights and covariance matrix:
    Var[R_p] = sum_i sum_j (w_i * w_j * Cov[i, j])

    Weights are normalized to decimal fractions summing to 1.0.
    Returns portfolio variance in percent-squared (%^2).
    """
    w_norm = normalize_weights(weights)
    n = len(w_norm)
    total_var = 0.0
    for i in range(n):
        for j in range(n):
            total_var += w_norm[i] * w_norm[j] * cov_matrix[i][j]
    return total_var


def portfolio_volatility(weights: List[float], cov_matrix: List[List[float]]) -> float:
    """
    Compute portfolio volatility (standard deviation):
    sigma_p = sqrt(Var[R_p])

    Returns volatility in percent.
    """
    var = portfolio_variance(weights, cov_matrix)
    # Guard against infinitesimal floating point negatives
    return math.sqrt(max(0.0, var))


def reserve_eligible_weight(weights: List[float], reserve_flags: List[bool]) -> float:
    """
    Compute total percentage weight allocated to reserve-eligible sleeves.
    Returns percentage between 0.0% and 100.0%.
    """
    w_norm = normalize_weights(weights)
    res_share = sum(w for w, flag in zip(w_norm, reserve_flags) if flag)
    return res_share * 100.0


def evaluate_portfolio(
    name: str,
    weights: List[float],
    sleeves: List[Dict[str, Any]],
    cov_matrix: List[List[float]],
    objective_return: float = 6.5
) -> Dict[str, Any]:
    """
    Evaluate all risk, return, reserve, and objective metrics for a candidate portfolio.
    """
    w_norm = normalize_weights(weights)
    w_pct = [w * 100.0 for w in w_norm]
    exp_returns = [s["expected_return"] for s in sleeves]
    reserve_flags = [s["reserve_eligible"] for s in sleeves]

    p_ret = portfolio_return(w_norm, exp_returns)
    p_vol = portfolio_volatility(w_norm, cov_matrix)
    res_w = reserve_eligible_weight(w_norm, reserve_flags)
    meets_obj = p_ret >= (objective_return - 1e-5)

    return {
        "name": name,
        "weights_norm": w_norm,
        "weights_pct": w_pct,
        "expected_return": p_ret,
        "volatility": p_vol,
        "reserve_eligible_pct": res_w,
        "meets_objective": meets_obj,
    }


def generate_long_only_weights(n_assets: int, step_pct: float = 5.0) -> List[List[float]]:
    """
    Generate all long-only portfolio weight combinations in discrete steps summing to 100%.
    For step_pct = 5.0%, partitions 20 discrete units across n_assets.
    """
    if n_assets <= 0:
        return []
    if n_assets > 8:
        raise ValueError(
            f"Discrete 5-point grid search supports up to 8 assets (mandate specifies 3-6 assets). "
            f"Received {n_assets} assets. Please select a subset of 3-6 assets."
        )
    total_steps = int(round(100.0 / step_pct))

    def _partitions(n: int, remaining: int):
        if n == 1:
            yield (remaining,)
            return
        for i in range(remaining + 1):
            for p in _partitions(n - 1, remaining - i):
                yield (i,) + p

    return [[step * step_pct for step in p] for p in _partitions(n_assets, total_steps)]


def search_lowest_risk_mix(
    expected_returns: Union[List[float], List[Dict[str, Any]]],
    cov_matrix: List[List[float]],
    reserve_flags: Optional[List[bool]] = None,
    objective_return: float = 6.5,
    min_reserve: float = 3.0,
    step_pct: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """
    Search every long-only mix of the assets in 5-point steps (0%, 5%, ..., 100%).
    Keeps mixes whose expected return is at least the objective and whose
    reserve-eligible weight is at least a minimum, and returns the one with
    the lowest volatility, or None (nothing) if no mix meets the objective.
    """
    # Allow passing sleeves dictionary list as first argument
    if expected_returns and isinstance(expected_returns[0], dict):
        sleeves_data = expected_returns
        exp_rets = [float(s["expected_return"]) for s in sleeves_data]
        res_flags = [bool(s.get("reserve_eligible", False)) for s in sleeves_data]
    else:
        exp_rets = [float(r) for r in expected_returns]
        if reserve_flags is None:
            res_flags = [False] * len(exp_rets)
        else:
            res_flags = [bool(f) for f in reserve_flags]

    n = len(exp_rets)
    if n == 0:
        return None

    candidate_weights = generate_long_only_weights(n, step_pct=step_pct)

    best_mix: Optional[Dict[str, Any]] = None
    min_volatility = float("inf")
    tol = 1e-7

    for w_pct in candidate_weights:
        w_dec = [w / 100.0 for w in w_pct]

        # Expected return check
        exp_ret = portfolio_return(w_dec, exp_rets)
        if exp_ret < objective_return - tol:
            continue

        # Reserve-eligible weight check
        res_w = reserve_eligible_weight(w_dec, res_flags)
        if res_w < min_reserve - tol:
            continue

        # Portfolio volatility
        vol = portfolio_volatility(w_dec, cov_matrix)

        if vol < min_volatility - 1e-9:
            min_volatility = vol
            best_mix = {
                "weights_pct": w_pct,
                "expected_return": exp_ret,
                "volatility": vol,
                "reserve_eligible_pct": res_w,
            }

    return best_mix


def estimate_from_prices(
    csv_source: Any,
    last_36: bool = False,
) -> Dict[str, Any]:
    """
    Estimate portfolio parameters from a CSV of monthly prices.
    CSV format requirements: date first, oldest first, one column per ticker.

    Computes:
      - Monthly returns from prices: (P_t - P_{t-1}) / P_{t-1}
      - Annualized mean: mean monthly return * 12 (in percent)
      - Annualized volatility: sample standard deviation (ddof=1) * sqrt(12) (in percent)
      - Pairwise correlation matrix of monthly returns
      - Covariance matrix using build_covariance_matrix
      - Evaluates on all months or only the last 36 monthly returns.
    """
    import pandas as pd

    if isinstance(csv_source, pd.DataFrame):
        df = csv_source.copy()
    else:
        df = pd.read_csv(csv_source)

    # Date first: if first column is date/text, index on it
    first_col = df.columns[0]
    if not pd.api.types.is_numeric_dtype(df[first_col]) or "date" in str(first_col).lower():
        df = df.set_index(first_col)

    df = df.dropna(how="all")

    # Monthly returns from prices
    returns = df.pct_change().dropna()

    if last_36:
        returns = returns.tail(36)

    tickers = list(returns.columns)

    # Mean * 12 (in percent)
    mean_ann = returns.mean() * 12.0 * 100.0
    expected_returns = [float(mean_ann[t]) for t in tickers]

    # Std dev * sqrt(12) (in percent)
    std_ann = returns.std(ddof=1) * math.sqrt(12.0) * 100.0
    volatilities = [float(std_ann[t]) for t in tickers]

    # Correlations
    corr_df = returns.corr()
    corr_matrix = [[float(corr_df.loc[t1, t2]) for t2 in tickers] for t1 in tickers]

    validate_correlation_matrix(corr_matrix)
    cov_matrix = build_covariance_matrix(corr_matrix, volatilities)

    return {
        "tickers": tickers,
        "expected_returns": expected_returns,
        "volatilities": volatilities,
        "corr_matrix": corr_matrix,
        "cov_matrix": cov_matrix,
        "n_months": len(returns),
    }


# ==============================================================================
# MAIN EXECUTION ROUTINE
# ==============================================================================

def run_portfolio_analysis() -> None:
    """
    Main driver:
    1. Validates the correlation matrix.
    2. Builds the covariance matrix.
    3. Defines the three canonical baselines:
       - Benchmark (40% IG bond fund, 60% Global equity index fund)
       - Equal weight (25% each across the four sleeves)
       - Inverse volatility (weights inversely proportional to standalone volatility)
    4. Computes all risk, return, reserve, and objective metrics.
    5. Formats and prints the verified output table.
    """
    # Step 1: Validate correlation matrix (refuses execution on violation)
    validate_correlation_matrix(CORRELATION_MATRIX)

    # Step 2: Extract sleeve vectors and build covariance matrix
    volatilities = [s["volatility"] for s in SLEEVES]
    cov_matrix = build_covariance_matrix(CORRELATION_MATRIX, volatilities)

    # Step 3: Define the three baselines
    # Weights ordered as: [bills, 10-year, IG, equity]
    portfolios_to_price = [
        ("Benchmark", [0.0, 0.0, 40.0, 60.0]),
        ("Equal weight", compute_equal_weights(len(SLEEVES))),
        ("Inverse volatility", compute_inverse_volatility_weights(volatilities)),
    ]

    results = []
    for name, raw_weights in portfolios_to_price:
        evaluated = evaluate_portfolio(
            name=name,
            weights=raw_weights,
            sleeves=SLEEVES,
            cov_matrix=cov_matrix,
            objective_return=OBJECTIVE_RETURN
        )
        results.append(evaluated)

    # Step 4: Display detailed results
    print("=" * 86)
    print("PORTFOLIO BASELINES RISK & RETURN ENGINE — MERIDIAN FOUNDATION".center(86))
    print(f"Objective Hurdle: {OBJECTIVE_RETURN:.2f}% (CPI 2.5% + 4.0% net real return)".center(86))
    print("=" * 86)
    print()

    # Formatted Verification Table matching Section V
    col_port = 20
    col_wts = 34
    col_ret = 8
    col_vol = 12
    col_res = 18
    col_obj = 12

    header = (
        f"{'Portfolio':<{col_port}} "
        f"{'Weights: bills / 10-year / IG / equity':<{col_wts}} "
        f"{'Return':>{col_ret}} "
        f"{'Volatility':>{col_vol}} "
        f"{'Reserve-eligible':>{col_res}} "
        f"{'Meets 6.5%?':>{col_obj}}"
    )
    print(header)
    print("-" * len(header))

    for res in results:
        w_str = " / ".join(f"{w:.1f}" for w in res["weights_pct"])
        obj_str = "yes" if res["meets_objective"] else "no"
        row = (
            f"{res['name']:<{col_port}} "
            f"{w_str:<{col_wts}} "
            f"{res['expected_return']:>{col_ret}.2f} "
            f"{res['volatility']:>{col_vol}.2f} "
            f"{res['reserve_eligible_pct']:>{col_res}.1f} "
            f"{obj_str:>{col_obj}}"
        )
        print(row)

    print("=" * len(header))
    print()

    # Additional diagnostic printouts
    print("Individual Portfolio Diagnostic Breakdowns:")
    for res in results:
        obj_text = "PASSED" if res["meets_objective"] else "FAILED"
        print(f"  [{res['name']}]")
        for s, w in zip(SLEEVES, res["weights_pct"]):
            print(f"    - {s['name']} ({s['short_name']}): {w:.1f}%")
        print(f"    Expected Return:  {res['expected_return']:.2f}%")
        print(f"    Volatility:       {res['volatility']:.2f}%")
        print(f"    Reserve-Eligible: {res['reserve_eligible_pct']:.1f}%")
        print(f"    Meets Objective:  {obj_text} (Target: {OBJECTIVE_RETURN:.2f}%)")
        print()


if __name__ == "__main__":
    try:
        run_portfolio_analysis()
    except ValueError as e:
        print(f"\n[ENGINE REFUSAL ERROR]: {e}", file=sys.stderr)
        sys.exit(1)

