"""
Step 5c: Whale RPU by group (control vs test).
Whale = payer whose total post-test revenue >= cutoff derived from the combined
cohort such that whales generate 75% of payer revenue.
Threshold is computed once per scenario so the definition is identical across groups.
Run after 05_whale_analysis.py (requires mobile_data.csv).
"""

import os

import pandas as pd

from constants import SCRIPT_DIR, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
WHALE_THRESHOLD_PCT = 0.75


def whale_cutoff(ab):
    payers = ab[ab["revenue"] > 0]["revenue"].sort_values(ascending=False).values
    cumrev = payers.cumsum()
    idx = int((cumrev < WHALE_THRESHOLD_PCT * payers.sum()).sum())
    return payers[min(idx, len(payers) - 1)]


def group_metrics(ab, cutoff, grp, grp_name):
    sub = ab[ab["split_group"] == grp]
    n_total = len(sub)
    whales = sub[sub["revenue"] >= cutoff]
    n_whales = len(whales)
    whale_rev = whales["revenue"].sum()
    total_rev = sub["revenue"].sum()
    n_payers = int((sub["revenue"] > 0).sum())
    return {
        "group": grp_name,
        "n_total": n_total,
        "n_whales": n_whales,
        "whale_pct_of_payers": n_whales / n_payers if n_payers > 0 else float("nan"),
        "whale_revenue": whale_rev,
        "whale_pct_of_revenue": whale_rev / total_rev if total_rev > 0 else float("nan"),
        "whale_RPU": whale_rev / n_total,
        "whale_ARPU": whale_rev / n_whales if n_whales > 0 else float("nan"),
        "cutoff": cutoff,
    }


def run_scenario(df, label):
    ab = build_ab_user_revenue(df)
    cutoff = whale_cutoff(ab)

    print(f"\n{'='*55}")
    print(f"WHALE RPU: {label}  (cutoff: ${cutoff:,.2f})")
    print(f"{'='*55}")

    rows = [group_metrics(ab, cutoff, grp, name) for grp, name in [(0, "Control"), (1, "Test")]]
    result = pd.DataFrame(rows).set_index("group")
    result["vs_control"] = (result["whale_RPU"] / result["whale_RPU"].iloc[0]) - 1

    print(result[[
        "n_total", "n_whales", "whale_pct_of_payers",
        "whale_revenue", "whale_pct_of_revenue",
        "whale_RPU", "whale_ARPU", "vs_control",
    ]].to_string(float_format=lambda x: f"{x:,.2f}" if abs(x) > 1 else f"{x:.2%}"))

    return result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    mobile_result = run_scenario(load_mobile_payments(), "Mobile Only")
    all_result = run_scenario(load_all_payments(), "All Devices")

    mobile_result["scenario"] = "mobile"
    all_result["scenario"] = "all"

    out = os.path.join(OUTPUT_DIR, "whale_rpu.csv")
    pd.concat([mobile_result, all_result]).to_csv(out, float_format="%.4f")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
