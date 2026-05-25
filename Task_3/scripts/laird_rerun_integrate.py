#!/usr/bin/env python3
"""
laird_rerun_integrate.py — одноразовый скрипт интеграции.

Шаги:
  1. Загружает data/laird_rerun/laird_matched.csv + laird_unmatched.csv
  2. Ремапит локальные product_id (1-16) на глобальные (max+1 ...)
  3. Присваивает product_id строкам из unmatched по product_name
  4. Добавляет brand_id=8 (Laird Superfood) всем новым строкам
  5. Загружает data/processed/all_brands_ids.csv
  6. Удаляет старые строки Laird Superfood
  7. Вставляет новые строки
  8. Перезаписывает all_brands_ids.csv

Run:
  python scripts/laird_rerun_integrate.py
"""

import csv
from pathlib import Path

ROOT          = Path(__file__).parent.parent
RERUN_DIR     = ROOT / "data" / "laird_rerun"
PROCESSED_DIR = ROOT / "data" / "processed"
ALL_IDS_FILE  = PROCESSED_DIR / "all_brands_ids.csv"

FIELDS = [
    "brand_id", "product_id", "brand", "product_name", "format",
    "serving_size_g", "serving_count", "volume_g", "price_usd",
    "discount_pct", "serving_price", "key_ingredient",
    "channel", "url", "date_collected", "purchase_type",
]

LAIRD_BRAND    = "Laird Superfood"
LAIRD_BRAND_ID = "8"


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
        sep = ";" if line.count(";") > line.count(",") else ","
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def main() -> None:
    # ── 1. Load all_brands_ids to find current max product_id ─────────────
    all_rows = _load(ALL_IDS_FILE)
    non_laird = [r for r in all_rows if r["brand"].strip() != LAIRD_BRAND]
    old_laird_count = len(all_rows) - len(non_laird)

    max_pid = max(
        (int(r["product_id"]) for r in all_rows if r.get("product_id", "").strip().isdigit()),
        default=0,
    )
    print(f"all_brands_ids: {len(all_rows)} rows, max product_id={max_pid}")
    print(f"  Removing {old_laird_count} old Laird rows")

    next_pid = max_pid + 1

    # ── 2. Load laird_matched — remap local product_ids to global ─────────
    matched = _load(RERUN_DIR / "laird_matched.csv")
    local_ids = sorted({r["product_id"].strip() for r in matched if r["product_id"].strip()},
                       key=lambda x: int(x) if x.isdigit() else 0)
    local_to_global: dict[str, str] = {}
    for lid in local_ids:
        local_to_global[lid] = str(next_pid)
        next_pid += 1

    print(f"\nMatched: {len(matched)} rows, {len(local_ids)} local product_ids")
    print(f"  Remapped local IDs: {local_ids[0]}..{local_ids[-1]} -> "
          f"{local_to_global[local_ids[0]]}..{local_to_global[local_ids[-1]]}")

    matched_rows: list[dict] = []
    for r in matched:
        pid = local_to_global.get(r["product_id"].strip(), "")
        matched_rows.append({
            "brand_id":   LAIRD_BRAND_ID,
            "product_id": pid,
            **{k: r.get(k, "").strip() for k in FIELDS[2:]},
        })

    # ── 3. Load laird_unmatched — assign product_ids by product_name ──────
    unmatched = _load(RERUN_DIR / "laird_unmatched.csv")
    name_to_pid: dict[str, str] = {}
    for r in unmatched:
        name = r["product_name"].strip()
        if name not in name_to_pid:
            name_to_pid[name] = str(next_pid)
            next_pid += 1

    print(f"\nUnmatched: {len(unmatched)} rows, {len(name_to_pid)} unique product names")
    print(f"  New IDs: {list(name_to_pid.values())[0]}..{list(name_to_pid.values())[-1]}")

    unmatched_rows: list[dict] = []
    for r in unmatched:
        name = r["product_name"].strip()
        unmatched_rows.append({
            "brand_id":   LAIRD_BRAND_ID,
            "product_id": name_to_pid[name],
            **{k: r.get(k, "").strip() for k in FIELDS[2:]},
        })

    # ── 4. Merge and write ─────────────────────────────────────────────────
    new_laird = matched_rows + unmatched_rows
    output = non_laird + new_laird

    with open(ALL_IDS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(output)

    print(f"\nWrote {len(output)} rows to {ALL_IDS_FILE.name}")
    print(f"  Non-Laird : {len(non_laird)}")
    print(f"  New Laird : {len(new_laird)} ({len(matched_rows)} matched + {len(unmatched_rows)} unmatched)")
    print(f"  product_ids used: {max_pid + 1}..{next_pid - 1}")


if __name__ == "__main__":
    main()
