#!/usr/bin/env python3
"""
patch_brand.py
Replace all rows for a given brand+channel in all_brands.csv with fresh data
from a new raw CSV — without re-running the full 04_filter_merge pipeline.

Useful after re-running a single brand's scraper.

Usage:
  python scripts/patch_brand.py --brand "Four Sigmatic" --channel amazon --file data/raw/four_sigmatic_amazon.csv
  python scripts/patch_brand.py --brand "Ryze" --channel own_site --file data/raw/ryze_individual.csv

What it does:
  1. Removes existing rows for (brand, channel) from all_brands.csv
  2. Loads the new raw CSV, normalises columns
  3. Runs name-matching (amazon rows → site names) using existing site rows in all_brands.csv
  4. Classifies each row (keep / review / reject)
  5. Appends kept rows to all_brands.csv
  6. Appends review/reject rows to rejected.csv
  7. Prints a summary of changes
"""

import argparse
import csv
import re
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

ALL_BRANDS = PROCESSED_DIR / "all_brands.csv"
REJECTED   = PROCESSED_DIR / "rejected.csv"

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

KEEP_KW = [
    "coffee", "matcha", "creamer", "latte", "cacao", "cocoa",
    "mocha", "espresso", "chai", "chagaccino",
    "dark roast", "medium roast", "light roast",
]
REJECT_KW = ["capsule", "pill", "tablet", "softgel", "gummy", "gummies", "tincture"]

_MATCH_STOP = {
    "mushroom", "organic", "with", "and", "for", "the", "of", "in", "by",
    "blend", "extract", "powder", "mix", "superfood", "functional",
    "serving", "servings", "count", "pack", "size", "large", "small",
    "from", "your", "that", "this", "more", "plus", "made", "great",
    "taste", "smooth", "energy", "support", "boost",
}


# ── I/O ───────────────────────────────────────────────────────────────────────

def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def load_csv(path: Path) -> list[dict]:
    sep = detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def normalise(row: dict) -> dict:
    if "url" not in row and "source_url" in row:
        row["url"] = row.pop("source_url")
    return {k: (row.get(k) or "").strip() for k in CSV_FIELDS}


# ── Filter ────────────────────────────────────────────────────────────────────

def classify(row: dict) -> str:
    name    = row["product_name"].lower()
    fmt     = row["format"].lower()
    channel = row["channel"]

    if not row["product_name"]:
        return "review"

    has_keep   = any(k in name for k in KEEP_KW)
    has_reject = any(k in name for k in REJECT_KW) or fmt == "capsule"

    if channel != "amazon":
        if has_reject:
            return "reject"
        if has_keep:
            return "keep"
        return "review"

    if has_keep and not has_reject:
        return "keep"
    if has_keep and has_reject:
        return "review"
    if has_reject:
        return "reject"
    return "review"


# ── Name matching ─────────────────────────────────────────────────────────────

def _kw(name: str) -> set:
    words = re.findall(r"[a-z]+", name.lower())
    return {w for w in words if len(w) >= 4 and w not in _MATCH_STOP}


def _safe_int(val: str) -> int | None:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def best_site_name(amazon_row: dict, site_rows: list[dict]) -> str | None:
    a_sc  = _safe_int(amazon_row["serving_count"])
    a_fmt = amazon_row["format"].lower()
    a_kw  = _kw(amazon_row["product_name"])

    best_name, best_score = None, 0
    for s in site_rows:
        s_sc = _safe_int(s["serving_count"])
        if a_sc and s_sc and a_sc != s_sc:
            continue
        s_fmt = s["format"].lower()
        if a_fmt and s_fmt and a_fmt != s_fmt:
            continue
        score = len(a_kw & _kw(s["product_name"]))
        if score > best_score:
            best_score, best_name = score, s["product_name"]

    return best_name if best_score >= 1 else None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand",   required=True,  help='Brand name, e.g. "Four Sigmatic"')
    parser.add_argument("--channel", required=True,  help="amazon | own_site | ebay")
    parser.add_argument("--file",    required=True,  help="Path to new raw CSV")
    args = parser.parse_args()

    brand_key   = args.brand.lower().strip()
    channel_key = args.channel.strip()
    new_file    = Path(args.file)

    if not new_file.exists():
        print(f"ERROR: file not found: {new_file}")
        return

    # ── 1. Load all_brands.csv, split out the rows being replaced ─────────────
    existing = load_csv(ALL_BRANDS)
    kept_other = [r for r in existing
                  if not (r["brand"].lower().strip() == brand_key
                          and r["channel"].strip() == channel_key)]
    removed = len(existing) - len(kept_other)

    # Site rows for this brand (used for Amazon name matching)
    site_rows = [r for r in existing
                 if r["brand"].lower().strip() == brand_key
                 and r["channel"].strip() != "amazon"]

    print(f"Replacing {removed} existing rows for [{args.brand}] / [{channel_key}]")
    print(f"  Site rows available for name matching: {len(site_rows)}")

    # ── 2. Load and normalise new raw CSV ─────────────────────────────────────
    raw_rows = [normalise(r) for r in load_csv(new_file)]
    print(f"  New raw rows loaded: {len(raw_rows)}")

    # ── 3. Name matching for amazon rows ──────────────────────────────────────
    n_matched = 0
    if channel_key == "amazon" and site_rows:
        for row in raw_rows:
            matched = best_site_name(row, site_rows)
            if matched and matched != row["product_name"]:
                row["product_name"] = matched
                n_matched += 1
        print(f"  Name matches (Amazon → site): {n_matched}")

    # ── 4. Classify ───────────────────────────────────────────────────────────
    new_kept    = [r for r in raw_rows if classify(r) == "keep"]
    new_review  = [r for r in raw_rows if classify(r) == "review"]
    new_reject  = [r for r in raw_rows if classify(r) == "reject"]

    print(f"  Classification → keep: {len(new_kept)}  review: {len(new_review)}  reject: {len(new_reject)}")

    # ── 5. Rewrite all_brands.csv ─────────────────────────────────────────────
    with open(ALL_BRANDS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(kept_other)
        w.writerows(new_kept)

    print(f"\nall_brands.csv: {len(kept_other) + len(new_kept)} rows  "
          f"(was {len(existing)}, removed {removed}, added {len(new_kept)})")

    # ── 6. Append to rejected.csv ─────────────────────────────────────────────
    if new_review or new_reject:
        # Remove old rejected rows for this brand+channel first
        old_rejected = load_csv(REJECTED) if REJECTED.exists() else []
        rej_sep = detect_sep(REJECTED) if REJECTED.exists() else ";"
        kept_rej = [r for r in old_rejected
                    if not (r.get("brand","").lower().strip() == brand_key
                            and r.get("channel","").strip() == channel_key)]

        with open(REJECTED, "w", newline="", encoding="utf-8") as f:
            fields = CSV_FIELDS + ["status"]
            w = csv.DictWriter(f, fieldnames=fields, delimiter=rej_sep)
            w.writeheader()
            w.writerows(kept_rej)
            for r in new_review:
                w.writerow({**r, "status": "review"})
            for r in new_reject:
                w.writerow({**r, "status": "reject"})

        print(f"rejected.csv: added {len(new_review)} review + {len(new_reject)} reject rows")

    print("\nDone. Re-run 05_assign_ids.py to update all_brands_ids.csv and unmatched_review.csv.")


if __name__ == "__main__":
    main()
