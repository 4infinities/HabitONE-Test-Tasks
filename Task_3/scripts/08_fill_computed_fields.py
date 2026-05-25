#!/usr/bin/env python3
"""
08_fill_computed_fields.py
Fills in computable missing fields in both processed CSVs:
  - serving_price = price_usd / serving_count  (where both present, serving_price absent)
  - volume_g      = serving_size_g * serving_count (where both present, volume_g absent)

Does NOT impute or guess — only fills where source values exist.
"""

import csv
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
FILES = [
    PROCESSED_DIR / "all_brands_ids.csv",
    PROCESSED_DIR / "unmatched_review.csv",
]


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def flt(v: str) -> float | None:
    try:
        return float(v) if v and v.strip() else None
    except ValueError:
        return None


def main() -> None:
    for path in FILES:
        sep = detect_sep(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            rows = list(csv.DictReader(f, delimiter=sep))
            fieldnames = rows[0].keys() if rows else []

        sp_filled = 0
        vg_filled = 0

        for r in rows:
            price      = flt(r.get("price_usd"))
            sc         = flt(r.get("serving_count"))
            ss         = flt(r.get("serving_size_g"))
            sp         = flt(r.get("serving_price"))
            vg         = flt(r.get("volume_g"))

            if sp is None and price is not None and sc and sc > 0:
                r["serving_price"] = f"{price / sc:.4f}"
                sp_filled += 1

            if vg is None and ss is not None and sc is not None and sc > 0:
                r["volume_g"] = f"{ss * sc:.2f}"
                vg_filled += 1

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=sep)
            w.writeheader()
            w.writerows(rows)

        print(f"{path.name}: serving_price filled={sp_filled}, volume_g filled={vg_filled}")


if __name__ == "__main__":
    main()
