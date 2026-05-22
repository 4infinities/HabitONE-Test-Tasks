"""Shared dates and cohort helpers for the A/B analysis pipeline."""

import os
import pandas as pd

# Test boundary: 2021-07-23 00:00 — A/B registrations start here.
# Pre-existing cohort: date_reg < TEST_START. A/B body: date_reg >= TEST_START.
TEST_START = pd.Timestamp("2021-07-23 00:00:00")

# Payments counted only from July 24 — first full day after experiment start.
PAYMENT_START = pd.Timestamp("2021-07-24 00:00:00")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOBILE_DATA_PATH = os.path.join(SCRIPT_DIR, "mobile_data.csv")
RAW_DATA_PATH = os.path.join(SCRIPT_DIR, "..", "Raw Data.csv")


def load_all_payments():
    """Load Raw Data.csv (all platforms) with parsed datetimes."""
    if not os.path.exists(RAW_DATA_PATH):
        raise FileNotFoundError(f"{RAW_DATA_PATH} not found.")
    df = pd.read_csv(RAW_DATA_PATH)
    df["date_reg"] = pd.to_datetime(df["date_reg"])
    df["date_payment"] = pd.to_datetime(df["date_payment"], errors="coerce")
    return df


def load_mobile_payments():
    """Load mobile_data.csv with parsed datetimes."""
    if not os.path.exists(MOBILE_DATA_PATH):
        raise FileNotFoundError(
            f"{MOBILE_DATA_PATH} not found. Run 01_filtering.py first."
        )
    df = pd.read_csv(MOBILE_DATA_PATH)
    df["date_reg"] = pd.to_datetime(df["date_reg"])
    df["date_payment"] = pd.to_datetime(df["date_payment"], errors="coerce")
    return df


def user_table(df):
    """One row per user: registration time and split assignment."""
    return (
        df.groupby("id_user")
        .agg(date_reg=("date_reg", "min"), split_group=("split_group", "first"))
        .reset_index()
    )


def pre_existing_ids(df):
    """Mobile users registered before the test (never saw new UI)."""
    return set(user_table(df).loc[user_table(df)["date_reg"] < TEST_START, "id_user"])


def ab_test_ids(df):
    """Mobile A/B test body: registered on or after TEST_START."""
    return set(user_table(df).loc[user_table(df)["date_reg"] >= TEST_START, "id_user"])


def successful_payments(df, user_ids=None, payment_start=None, payment_end=None):
    """Payment rows: successful only, optional user filter and date window."""
    mask = df["date_payment"].notna() & (df["successful_payment"] == 1)
    if user_ids is not None:
        mask &= df["id_user"].isin(user_ids)
    payments = df.loc[mask]
    if payment_start is not None:
        payments = payments[payments["date_payment"] >= payment_start]
    if payment_end is not None:
        payments = payments[payments["date_payment"] < payment_end]
    return payments


def build_ab_user_revenue(df):
    """One row per AB-test user: revenue and payment_count (0 for non-payers)."""
    ut = user_table(df)
    ab_ut = ut[ut["date_reg"] >= TEST_START].dropna(subset=["split_group"]).copy()
    ab_ut["split_group"] = ab_ut["split_group"].astype(int)
    pay = successful_payments(df, user_ids=set(ab_ut["id_user"]), payment_start=PAYMENT_START)
    ab_ut["revenue"] = ab_ut["id_user"].map(pay.groupby("id_user")["amount"].sum()).fillna(0.0)
    ab_ut["payment_count"] = ab_ut["id_user"].map(pay.groupby("id_user").size()).fillna(0).astype(int)
    return ab_ut


def cohort_metrics(df, user_ids, payment_start=None, payment_end=None):
    """RPU and conversion for a fixed user cohort in a payment window."""
    cohort_size = len(user_ids)
    if cohort_size == 0:
        return None

    payments = successful_payments(
        df, user_ids=user_ids, payment_start=payment_start, payment_end=payment_end
    )
    user_revenue = payments.groupby("id_user")["amount"].sum()
    paying_users = len(user_revenue)
    total_revenue = user_revenue.sum()

    return {
        "cohort_users": cohort_size,
        "paying_users": paying_users,
        "total_revenue": total_revenue,
        "rpu": total_revenue / cohort_size,
        "conversion_rate": paying_users / cohort_size,
        "arpu_payers": total_revenue / paying_users if paying_users > 0 else float("nan"),
        "payments_per_user": len(payments) / cohort_size,
    }
