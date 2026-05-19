"""Revenue distribution for pre-existing cohort — payers only (pre_test_user_data.csv)."""

import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))
input_path = os.path.join(script_dir, 'pre_test_user_data.csv')
output_dir = os.path.join(script_dir, 'outputs')
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'pre_test_revenue_distribution.png')


def pareto_table(revenue, label):
    rev = np.sort(np.array(revenue, dtype=float))[::-1]
    total = rev.sum()
    n = len(rev)
    if total == 0 or n == 0:
        print(f"=== {label}: no revenue ===\n")
        return
    cum = np.cumsum(rev)
    print(f"=== {label} (n={n:,}, total={total:,.2f}) ===")
    print(f"{'Top user %':>12} | {'Users':>8} | {'Revenue %':>10}")
    print("-" * 38)
    for pct in [0.1, 0.5, 1, 2, 5, 10, 20, 50]:
        k = max(1, int(np.ceil(n * pct / 100)))
        share = cum[k - 1] / total * 100
        print(f"{pct:>11.1f}% | {k:>8} | {share:>9.2f}%")
    idx80 = int(np.searchsorted(cum, 0.8 * total)) + 1
    print(f"80% revenue from top {idx80} users ({idx80 / n * 100:.2f}% of payers)\n")


if not os.path.exists(input_path):
    print(f"ERROR: {input_path} not found. Run 02_aa_check.py first.")
    exit(1)

df = pd.read_csv(input_path)
df['total_revenue'] = df['revenue_before'] + df['revenue_after']

# Payers only: exclude users with zero total revenue
payers = df[df['total_revenue'] > 0].copy()
print(f"Cohort: {len(df):,} users -> payers only: {len(payers):,} ({len(payers)/len(df)*100:.1f}%)\n")

for col in ['revenue_before', 'revenue_after', 'total_revenue']:
    s = payers[col]
    print(f"{col}: mean={s.mean():.2f}, median={s.median():.2f}, max={s.max():.2f}")

print("\n--- Pareto (payers only, non-zero revenue) ---\n")
pareto_table(payers['total_revenue'].values, 'total_revenue')
pareto_table(
    payers.loc[payers['revenue_before'] > 0, 'revenue_before'].values,
    'revenue_before (paid in window)',
)
pareto_table(
    payers.loc[payers['revenue_after'] > 0, 'revenue_after'].values,
    'revenue_after (paid in window)',
)

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Histogram: total revenue among payers
ax = axes[0]
ax.hist(np.log10(payers['total_revenue']), bins=40, color='steelblue', edgecolor='white', alpha=0.85)
ax.set_xlabel('log10(total revenue per user)')
ax.set_ylabel('Count')
ax.set_title(f'Revenue distribution (payers only, n={len(payers)})')

# Boxplot: positive revenue in each window only
ax = axes[1]
box_data = [
    payers.loc[payers['revenue_before'] > 0, 'revenue_before'],
    payers.loc[payers['revenue_after'] > 0, 'revenue_after'],
]
bp = ax.boxplot(
    box_data,
    tick_labels=['Before Jul 23', 'After Jul 23'],
    showfliers=False,
    patch_artist=True,
)
for patch, color in zip(bp['boxes'], ['#6baed6', '#fd8d3c']):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_yscale('log')
ax.set_ylabel('Revenue (log scale)')
ax.set_title(
    f'Boxplot: paid in window (n={len(box_data[0])} / {len(box_data[1])})'
)

fig.suptitle('Pre-existing cohort: payers only (zeros excluded)', fontsize=11)
fig.tight_layout()
fig.savefig(output_path, dpi=150)
plt.close()

print(f"Saved: {output_path}")
