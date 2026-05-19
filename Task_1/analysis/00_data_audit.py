import pandas as pd
import numpy as np

from constants import RAW_DATA_PATH

# Load raw_data file
df = pd.read_csv(RAW_DATA_PATH)

print("=== Data Loading & Initial Audit ===")
print(f"Dataset shape: {df.shape}")
print("\nColumn data types:")
print(df.dtypes)
print("\nMissing values count:")
print(df.isnull().sum())

# Check date ranges: date_reg, date_payment
# Convert to datetime
df['date_reg'] = pd.to_datetime(df['date_reg'])
df['date_payment'] = pd.to_datetime(df['date_payment'], errors='coerce')

print("\nDate range for registration (date_reg):")
print(f"  Min: {df['date_reg'].min()}")
print(f"  Max: {df['date_reg'].max()}")

print("\nDate range for payment (date_payment):")
print(f"  Min: {df['date_payment'].min()} (excluding NaT)")
print(f"  Max: {df['date_payment'].max()} (excluding NaT)")
print(f"  Number of NaT (missing) in date_payment: {df['date_payment'].isnull().sum()}")

# Verify split_group distribution
print("\nSplit group distribution:")
split_counts = df['split_group'].value_counts()
print(split_counts)
print(f"  Proportion: {split_counts / len(df)}")

# Check for users appearing in both groups (contamination check)
# Group by user and see if they have more than one unique split_group
user_split_groups = df.groupby('id_user')['split_group'].nunique()
contaminated_users = user_split_groups[user_split_groups > 1]
print(f"\nNumber of users appearing in both groups (contamination): {len(contaminated_users)}")
if len(contaminated_users) > 0:
    print("Contaminated user IDs (first 10):")
    print(contaminated_users.index[:10].tolist())
else:
    print("No contamination found.")