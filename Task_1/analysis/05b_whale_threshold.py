"""
Step 5b: Whale Threshold Sensitivity Table
For each cumulative revenue % threshold, shows what % of PAYERS generates it
and the minimum spend ($X) needed to be in that group — for both scenarios.
Run after 05_whale_analysis.py (requires mobile_data.csv).
"""

import os

import pandas as pd

from constants import SCRIPT_DIR, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
THRESHOLDS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


def payer_sensitivity(ab, label):
    payers = ab[ab["revenue"] > 0]["revenue"].sort_values(ascending=False).values
    total_rev = payers.sum()
    n_payers = len(payers)
    cumrev = payers.cumsum()

    rows = []
    for t in THRESHOLDS:
        idx = int((cumrev < t * total_rev).sum())
        n_whales = min(idx + 1, n_payers)
        rows.append({
            "cum_rev_pct": f"{t:.0%}",
            f"pct_payers_{label}": f"{n_whales / n_payers:.2%}",
            f"n_payers_{label}": n_whales,
            f"min_spend_{label}": round(payers[n_whales - 1], 2),
        })
    return pd.DataFrame(rows).set_index("cum_rev_pct")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    table = payer_sensitivity(build_ab_user_revenue(load_mobile_payments()), "mobile").join(
        payer_sensitivity(build_ab_user_revenue(load_all_payments()), "all")
    )

    print("\nWhale Threshold Sensitivity Table")
    print("(based on PAYERS only; AB-test cohort, post-test revenue)\n")
    print(table.to_string())

    out = os.path.join(OUTPUT_DIR, "whale_threshold_sensitivity.csv")
    table.to_csv(out)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
