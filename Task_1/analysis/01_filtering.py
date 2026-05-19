import pandas as pd
import numpy as np
import os

from constants import TEST_START

# Load data
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(script_dir, '..', 'Raw Data.csv')
df = pd.read_csv(csv_path)

# Convert dates
df['date_reg'] = pd.to_datetime(df['date_reg'])
df['date_payment'] = pd.to_datetime(df['date_payment'], errors='coerce')

# CLAUDE.md: inspect platform x system before deciding on mobile filter
print("=== Platform x System inspection ===")
print("Unique platform values:", sorted(df['platform'].dropna().unique().tolist()))
print("Unique system values:  ", sorted(df['system'].dropna().unique().tolist()))
print("\nCross-tab (platform x system):")
print(df.groupby(['platform', 'system']).size().reset_index(name='count').to_string(index=False))

print("=== Step 1: Data Filtering ===")
print(f"Original dataset: {len(df)} rows")

# Reference check on desktop/other users
# Only consider users registered on or after TEST_START for A/B assignment bias check
print("\n--- Reference Check: Desktop/Other Users ---")
print(f"Test boundary (TEST_START): {TEST_START}")
desktop_other = df[df['platform'].isin(['desktop', 'other']) & (df['date_reg'] >= TEST_START)]
print(f"Desktop/other users (registered on or after {TEST_START.date()}): {len(desktop_other)} rows")
if len(desktop_other) > 0:
    # Check if desktop/other shows difference between groups
    desktop_other_successful = desktop_other[desktop_other['successful_payment'] == 1]
    desktop_other_grouped = desktop_other.groupby('split_group').agg(
        total_users=('id_user', 'nunique')
    ).reset_index()
    rev_by_group = desktop_other_successful.groupby('split_group')['amount'].sum().rename('total_revenue')
    pay_by_group = desktop_other_successful.groupby('split_group')['id_user'].nunique().rename('paying_users')
    desktop_other_grouped = desktop_other_grouped.join(rev_by_group, on='split_group').join(pay_by_group, on='split_group').fillna(0)

    if len(desktop_other_grouped) == 2:  # Both groups present
        desktop_other_grouped['rpu'] = desktop_other_grouped['total_revenue'] / desktop_other_grouped['total_users']
        desktop_other_grouped['conversion_rate'] = desktop_other_grouped['paying_users'] / desktop_other_grouped['total_users']

        print("Desktop/other users by group:")
        print(desktop_other_grouped[['split_group', 'rpu', 'conversion_rate']])

        # Calculate differences
        control = desktop_other_grouped[desktop_other_grouped['split_group'] == 0].iloc[0]
        test = desktop_other_grouped[desktop_other_grouped['split_group'] == 1].iloc[0]

        rpu_diff = test['rpu'] - control['rpu']
        conv_diff = test['conversion_rate'] - control['conversion_rate']

        print(f"\nRPU difference (test - control): {rpu_diff:.4f}")
        print(f"Conversion rate difference (test - control): {conv_diff:.4f}")

        rpu_rel = abs(rpu_diff / control['rpu']) if control['rpu'] != 0 else float('inf')
        conv_rel = abs(conv_diff / control['conversion_rate']) if control['conversion_rate'] != 0 else float('inf')
        print(f"RPU relative diff: {rpu_rel:.1%} | Conversion relative diff: {conv_rel:.1%}")
        if rpu_rel < 0.05 and conv_rel < 0.02:
            print("PASS: Desktop/other shows NO meaningful difference - randomization appears valid")
        else:
            print("WARN: Desktop/other shows a difference - potential systematic bias in assignment")
    else:
        print("Desktop/other users only in one group - cannot compare")
else:
    print("No desktop/other users found")

# Filter to mobile-only for main analysis
print("\n--- Filtering to Mobile Users ---")
mobile_df = df[df['platform'].str.lower().isin(['mobile', 'android', 'ios'])].copy()
print(f"Mobile users: {len(mobile_df)} rows ({(len(mobile_df)/len(df))*100:.1f}% of total)")

# Save filtered data for subsequent steps
output_path = os.path.join(script_dir, 'mobile_data.csv')
mobile_df.to_csv(output_path, index=False)
print(f"Mobile data saved to: {output_path}")

print("\nMobile data summary:")
print(f"  Date range: {mobile_df['date_reg'].min()} to {mobile_df['date_reg'].max()}")
print(f"  Split group distribution:")
print(mobile_df['split_group'].value_counts())
print(f"  Proportions: {mobile_df['split_group'].value_counts(normalize=True)}")
