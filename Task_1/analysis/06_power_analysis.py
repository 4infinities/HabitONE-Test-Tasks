"""
Step 6: Power analysis for main A/B hypothesis.
Primary: payments_per_user. Secondary: RPU.
Alpha=0.05, Power=0.80, MDE=10%.
"""

import numpy as np
import os
import pandas as pd
from scipy import stats

from constants import SCRIPT_DIR, build_ab_user_revenue, load_all_payments, load_mobile_payments

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
ALPHA = 0.05
POWER_TARGET = 0.80
MDE = 0.10


def required_n(mean_c, std_c, mde=MDE, alpha=ALPHA, power=POWER_TARGET):
    delta = mean_c * mde
    if delta == 0 or std_c == 0:
        return float("nan")
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return int(np.ceil(2 * z ** 2 * std_c ** 2 / delta ** 2))


def obs_power(mean_c, std_c, n, mde=MDE, alpha=ALPHA):
    delta = mean_c * mde
    if delta == 0 or std_c == 0:
        return float("nan")
    z_a = stats.norm.ppf(1 - alpha / 2)
    ncp = (delta / std_c) * np.sqrt(n / 2)
    return float(1 - stats.norm.cdf(z_a - ncp) + stats.norm.cdf(-z_a - ncp))


def power_row(scenario, metric, ctrl, test):
    mean_c, std_c = ctrl.mean(), ctrl.std(ddof=1)
    n_c, n_t = len(ctrl), len(test)
    req = required_n(mean_c, std_c)
    return {
        "scenario": scenario,
        "metric": metric,
        "baseline_mean": mean_c,
        "baseline_std": std_c,
        "mde_absolute": mean_c * MDE,
        "required_n": req,
        "actual_n_control": n_c,
        "actual_n_test": n_t,
        "powered": (n_c >= req and n_t >= req) if not np.isnan(req) else False,
        "obs_power_at_mde": obs_power(mean_c, std_c, min(n_c, n_t)),
        "obs_effect_pct": (test.mean() / mean_c - 1) if mean_c != 0 else float("nan"),
    }


def run_scenario(df, label):
    ab = build_ab_user_revenue(df)
    ctrl, test = ab[ab["split_group"] == 0], ab[ab["split_group"] == 1]
    return [
        power_row(label, "payments_per_user", ctrl["payment_count"].astype(float), test["payment_count"].astype(float)),
        power_row(label, "RPU", ctrl["revenue"], test["revenue"]),
    ]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = run_scenario(load_mobile_payments(), "mobile") + run_scenario(load_all_payments(), "all_devices")
    out = pd.DataFrame(rows)

    print("\n=== POWER ANALYSIS  (MDE=10%, alpha=0.05, power=0.80) ===")
    print(out.to_string(index=False))

    path = os.path.join(OUTPUT_DIR, "power_table.csv")
    out.to_csv(path, index=False, float_format="%.6f")
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
