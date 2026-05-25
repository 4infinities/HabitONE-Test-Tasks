#!/usr/bin/env python3
"""
07_cleanup_ids.py
Fixes brand/product naming issues in both processed CSVs:

  1. Normalises brand names (aliases → canonical)
  2. Rebuilds canonical brand_id for each brand (one stable ID per brand)
  3. For each product_id, keeps the shortest product_name across all rows
  4. Rewrites all_brands_ids.csv and unmatched_review.csv in-place

Run ONCE after 05_assign_ids.py + 06_fill_unmatched_ids.py, then re-run 02_load_db.py.
"""

import csv
from collections import defaultdict
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
IDS_FILE      = PROCESSED_DIR / "all_brands_ids.csv"
UNMATCHED     = PROCESSED_DIR / "unmatched_review.csv"

# Brand name aliases → canonical name
BRAND_ALIASES: dict[str, str] = {
    "Strong Coffee Company": "Strong Coffee Co.",
    "Clevr Blends":          "Clevr Blends",   # keep as-is; "Clevr" → below
    "Clevr":                 "Clevr Blends",
    "IQJOE":                 "IQJOE",
    "IQBAR":                 "IQBAR",
}


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def load_csv(path: Path) -> list[dict]:
    sep = detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    sep = detect_sep(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=sep)
        w.writeheader()
        w.writerows(rows)


def canonical_brand(name: str) -> str:
    return BRAND_ALIASES.get(name.strip(), name.strip())


def main() -> None:
    ids_rows = load_csv(IDS_FILE)
    unm_rows = load_csv(UNMATCHED)

    # ── 1. Apply brand name normalisation ────────────────────────────────────
    for r in ids_rows + unm_rows:
        r["brand"] = canonical_brand(r["brand"])

    # ── 2. Build canonical brand_id map ──────────────────────────────────────
    # Priority: IDs from all_brands_ids.csv (these were assigned by 05_assign_ids.py
    # and are considered stable). One brand → one ID (pick smallest seen).
    brand_to_id: dict[str, int] = {}
    for r in ids_rows:
        b = r["brand"]
        bid = int(r["brand_id"])
        if b not in brand_to_id or bid < brand_to_id[b]:
            brand_to_id[b] = bid

    # Brands that only appear in unmatched get a fresh ID above current max
    next_id = (max(brand_to_id.values()) + 1) if brand_to_id else 1
    for r in unm_rows:
        b = r["brand"]
        if b not in brand_to_id:
            brand_to_id[b] = next_id
            next_id += 1

    # Apply canonical brand_ids to all rows
    for r in ids_rows + unm_rows:
        r["brand_id"] = str(brand_to_id[r["brand"]])

    # ── 3. Shortest product_name per product_id ───────────────────────────────
    pid_shortest: dict[str, str] = {}
    for r in ids_rows + unm_rows:
        pid  = r.get("product_id", "").strip()
        name = r.get("product_name", "").strip()
        if not pid or not name:
            continue
        if pid not in pid_shortest or len(name) < len(pid_shortest[pid]):
            pid_shortest[pid] = name

    for r in ids_rows + unm_rows:
        pid = r.get("product_id", "").strip()
        if pid and pid in pid_shortest:
            r["product_name"] = pid_shortest[pid]

    # ── 4. Write back ─────────────────────────────────────────────────────────
    write_csv(IDS_FILE,  ids_rows, list(ids_rows[0].keys()))
    write_csv(UNMATCHED, unm_rows, list(unm_rows[0].keys()))

    print(f"Brands canonical: {len(brand_to_id)}")
    print(f"Product names normalised: {len(pid_shortest)} unique product_ids")
    print(f"all_brands_ids.csv  : {len(ids_rows)} rows")
    print(f"unmatched_review.csv: {len(unm_rows)} rows")

    # Summary of brand name changes
    aliases_applied = {k: v for k, v in BRAND_ALIASES.items() if k != v}
    if aliases_applied:
        print("\nBrand aliases applied:")
        for old, new in aliases_applied.items():
            print(f"  {old!r} -> {new!r}")


if __name__ == "__main__":
    main()
