#!/usr/bin/env python3
"""
04_filter_merge.py
Reads all raw CSVs from data/raw/ (excluding archive/ and known duplicates),
normalises columns, matches long Amazon product names to short site names,
filters rows by relevance, and writes:

  data/processed/all_brands.csv  — kept rows (coffee-adjacent products)
  data/processed/rejected.csv    — rejected / review rows (with status column)

Run:
  python scripts/04_filter_merge.py
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

# Skip files whose contents are superseded by a better version in the same folder
SKIP_FILES = {
    "ryze.csv",            # replaced by ryze_individual.csv
    "habitone_amazon.csv", # replaced by habitone_amazon_full.csv
}

# Brands that have no own-site scraper — skip name-matching for them
AMAZON_ONLY_BRANDS = {"bunkell", "taoters"}

# Products containing any of these keywords are coffee-adjacent → keep
KEEP_KW = [
    "coffee", "matcha", "creamer", "latte", "cacao", "cocoa",
    "mocha", "espresso", "chai", "chagaccino",
    "dark roast", "medium roast", "light roast",
]

# Products with any of these (and no KEEP_KW) are definitively non-coffee → reject
REJECT_KW = ["capsule", "pill", "tablet", "softgel", "gummy", "gummies", "tincture"]

# Words that are too generic to help match site names to Amazon names
_MATCH_STOP = {
    "mushroom", "organic", "with", "and", "for", "the", "of", "in", "by",
    "blend", "extract", "powder", "mix", "superfood", "functional",
    "serving", "servings", "count", "pack", "size", "large", "small",
    "from", "your", "that", "this", "more", "plus", "made", "great",
    "taste", "smooth", "energy", "support", "boost",
}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def load_csv(path: Path) -> list[dict]:
    sep = detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def normalise(row: dict) -> dict:
    """Keep only canonical CSV_FIELDS; handle column name aliases."""
    if "url" not in row and "source_url" in row:
        row["url"] = row.pop("source_url")
    return {k: (row.get(k) or "").strip() for k in CSV_FIELDS}


# ── Filtering ─────────────────────────────────────────────────────────────────

def classify(row: dict) -> str:
    """Return 'keep', 'reject', or 'review'."""
    name    = row["product_name"].lower()
    fmt     = row["format"].lower()
    channel = row["channel"]

    if not row["product_name"]:
        return "review"

    has_keep   = any(k in name for k in KEEP_KW)
    has_reject = any(k in name for k in REJECT_KW) or fmt == "capsule"

    if channel != "amazon":
        # Site rows: only reject on explicit REJECT_KW; no-signal → review
        if has_reject:
            return "reject"
        if has_keep:
            return "keep"
        return "review"

    # Amazon rows: require KEEP_KW to keep
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
    """
    Find the site product whose name best matches the Amazon row.
    Hard constraints: serving_count and format must agree (when both present).
    Score: number of shared meaningful keywords.
    Returns site product_name if score >= 1, else None.
    """
    a_sc  = _safe_int(amazon_row["serving_count"])
    a_fmt = amazon_row["format"].lower()
    a_kw  = _kw(amazon_row["product_name"])

    best_name, best_score = None, 0
    for s in site_rows:
        s_sc = _safe_int(s["serving_count"])
        if a_sc and s_sc and a_sc != s_sc:
            continue                             # serving count mismatch

        s_fmt = s["format"].lower()
        if a_fmt and s_fmt and a_fmt != s_fmt:
            continue                             # format mismatch

        score = len(a_kw & _kw(s["product_name"]))
        if score > best_score:
            best_score, best_name = score, s["product_name"]

    return best_name if best_score >= 1 else None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    files = sorted(f for f in RAW_DIR.glob("*.csv") if f.name not in SKIP_FILES)

    site_by_brand:   dict[str, list[dict]] = defaultdict(list)
    amazon_by_brand: dict[str, list[dict]] = defaultdict(list)

    for path in files:
        for raw in load_csv(path):
            row = normalise(raw)
            key = row["brand"].lower()
            if row["channel"] == "amazon":
                amazon_by_brand[key].append(row)
            else:
                site_by_brand[key].append(row)

    # Replace long Amazon product names with short site names
    n_matched = 0
    match_log: list[tuple[str, str, str]] = []  # (brand, old, new)
    for brand_key, a_rows in amazon_by_brand.items():
        if brand_key in AMAZON_ONLY_BRANDS:
            continue
        s_rows = site_by_brand.get(brand_key, [])
        if not s_rows:
            continue
        for row in a_rows:
            matched = best_site_name(row, s_rows)
            if matched and matched != row["product_name"]:
                match_log.append((row["brand"], row["product_name"][:60], matched))
                row["product_name"] = matched
                n_matched += 1

    # Merge all rows and classify
    kept: list[dict] = []
    rejected: list[dict] = []

    for rows in (*site_by_brand.values(), *amazon_by_brand.values()):
        for row in rows:
            status = classify(row)
            if status == "keep":
                kept.append(row)
            else:
                rejected.append({**row, "status": status})

    # Write outputs
    kept_path = PROCESSED_DIR / "all_brands.csv"
    with open(kept_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(kept)

    rej_path = PROCESSED_DIR / "rejected.csv"
    with open(rej_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS + ["status"])
        w.writeheader()
        w.writerows(rejected)

    # Summary
    n_reject = sum(1 for r in rejected if r["status"] == "reject")
    n_review = sum(1 for r in rejected if r["status"] == "review")
    print(f"\nLoaded {len(files)} files from {RAW_DIR}")
    print(f"Name matches (Amazon -> site): {n_matched}")
    print(f"\nOutput:")
    print(f"  kept   : {len(kept):>4} rows -> {kept_path}")
    print(f"  reject : {n_reject:>4} rows")
    print(f"  review : {n_review:>4} rows -> {rej_path}")

    if match_log:
        print(f"\nSample name matches (first 10):")
        for brand, old, new in match_log[:10]:
            print(f"  [{brand}]")
            print(f"    Amazon : {old}...")
            print(f"    -> Site: {new}")


if __name__ == "__main__":
    main()
