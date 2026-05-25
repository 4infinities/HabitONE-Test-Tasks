#!/usr/bin/env python3
"""
05_assign_ids.py
Reads data/processed/all_brands.csv, assigns brand_id and product_id,
and splits into:

  data/processed/all_brands_ids.csv   — matched rows (brand_id + product_id)
  data/processed/unmatched_review.csv — unmatched rows (brand_id only, no product_id)
                                        grouped by brand for manual review

"Matched" means (brand, product_name) appears in more than one channel,
OR the brand only has one channel (nothing to match against → IDs assigned directly).

"Unmatched" means (brand, product_name) appears in only one channel
for a brand that has BOTH own_site and amazon rows.

Run:
  python scripts/05_assign_ids.py
"""

import csv
from collections import defaultdict
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

IN_FILE       = PROCESSED_DIR / "all_brands.csv"
OUT_MATCHED   = PROCESSED_DIR / "all_brands_ids.csv"
OUT_UNMATCHED = PROCESSED_DIR / "unmatched_review.csv"

BASE_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]
MATCHED_FIELDS   = ["brand_id", "product_id"] + BASE_FIELDS
UNMATCHED_FIELDS = ["brand_id", "product_id"] + BASE_FIELDS


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def load(path: Path) -> list[dict]:
    sep = detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def main() -> None:
    rows = load(IN_FILE)

    # ── 1. Brand IDs ──────────────────────────────────────────────────────────
    brand_order = []
    seen_brands = {}
    for r in rows:
        b = r["brand"].strip()
        if b not in seen_brands:
            seen_brands[b] = len(brand_order) + 1
            brand_order.append(b)
    brand_id_map: dict[str, int] = seen_brands  # brand_name → brand_id

    # ── 2. Identify which brands have both channels ────────────────────────────
    brand_channels: dict[str, set] = defaultdict(set)
    for r in rows:
        brand_channels[r["brand"].strip()].add(r["channel"].strip())

    dual_channel_brands = {b for b, ch in brand_channels.items()
                           if "own_site" in ch and "amazon" in ch}

    # ── 3. Group rows by (brand, product_name) ────────────────────────────────
    # key: (brand, product_name) → list of rows
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["brand"].strip(), r["product_name"].strip())
        groups[key].append(r)

    # ── 4. Classify each group as matched or unmatched ────────────────────────
    matched_rows:   list[dict] = []
    unmatched_rows: list[dict] = []

    product_counter = 0
    product_id_map: dict[tuple, int] = {}

    for (brand, pname), group_rows in groups.items():
        channels_in_group = {r["channel"].strip() for r in group_rows}
        is_dual_brand     = brand in dual_channel_brands
        cross_channel     = len(channels_in_group) > 1

        if not is_dual_brand or cross_channel:
            # Assign product_id
            key = (brand, pname)
            if key not in product_id_map:
                product_counter += 1
                product_id_map[key] = product_counter
            pid = product_id_map[key]
            bid = brand_id_map[brand]
            for r in group_rows:
                matched_rows.append({"brand_id": bid, "product_id": pid, **r})
        else:
            # Single-channel group for a dual-channel brand → unmatched
            bid = brand_id_map[brand]
            for r in group_rows:
                unmatched_rows.append({"brand_id": bid, "product_id": "", **r})

    # ── 5. Sort unmatched by brand_id then channel (site before amazon) ───────
    channel_order = {"own_site": 0, "amazon": 1, "ebay": 2}
    unmatched_rows.sort(key=lambda r: (
        r["brand_id"],
        channel_order.get(r["channel"].strip(), 9),
        r["product_name"],
    ))

    # ── 6. Write outputs ──────────────────────────────────────────────────────
    with open(OUT_MATCHED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MATCHED_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(matched_rows)

    with open(OUT_UNMATCHED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=UNMATCHED_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(unmatched_rows)

    # ── 7. Summary ────────────────────────────────────────────────────────────
    print(f"Input rows : {len(rows)}")
    print(f"Brands     : {len(brand_id_map)}  (dual-channel: {len(dual_channel_brands)})")
    print(f"Products assigned IDs : {product_counter}")
    print(f"\nMatched    : {len(matched_rows):>4} rows -> {OUT_MATCHED.name}")
    print(f"Unmatched  : {len(unmatched_rows):>4} rows -> {OUT_UNMATCHED.name}")

    if unmatched_rows:
        from collections import Counter
        counts = Counter(r["brand"] for r in unmatched_rows)
        print("\nUnmatched by brand:")
        for brand, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {brand}: {cnt}")


if __name__ == "__main__":
    main()
