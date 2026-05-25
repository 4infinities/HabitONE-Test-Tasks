#!/usr/bin/env python3
"""
06_fill_unmatched_ids.py
Auto-assigns product_ids to rows in unmatched_review.csv that have no product_id yet.

Grouping rule: same brand + name that differs only in serving-count/size tokens
→ same product_id.  Different product concept → different product_id.

New IDs start above the max existing product_id found across all_brands_ids.csv
and the already-filled rows in unmatched_review.csv.

Usage:
  python scripts/06_fill_unmatched_ids.py
"""

import csv
import re
from pathlib import Path

ROOT          = Path(__file__).parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
ALL_BRANDS_IDS   = PROCESSED_DIR / "all_brands_ids.csv"
UNMATCHED_REVIEW = PROCESSED_DIR / "unmatched_review.csv"

# Tokens that indicate only a size/count variant — strip these before comparing names
_SIZE_PATTERNS = [
    r"\b\d+\s*(?:servings?|count|ct|pack|pk|oz|lb|lbs|g|kg|fl\.?\s*oz)\b",
    r"\b\d+-count\b",
    r"\b\d+\s*x\s*\d+",   # e.g. "2 x 30"
    r"\(\s*\d+[^)]*\)",   # parenthetical "(30 ct)" etc.
    r",\s*\d+\s*(?:servings?|count|ct|pack|pk|oz|lb)",
]
_SIZE_RE = re.compile("|".join(_SIZE_PATTERNS), re.IGNORECASE)


def normalise_name(name: str) -> str:
    name = _SIZE_RE.sub(" ", name)
    name = re.sub(r"\s{2,}", " ", name).strip().lower()
    return name


def detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def load_csv(path: Path) -> list[dict]:
    sep = detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def main() -> None:
    ids_rows      = load_csv(ALL_BRANDS_IDS)
    unmatched_rows = load_csv(UNMATCHED_REVIEW)
    sep           = detect_sep(UNMATCHED_REVIEW)
    fieldnames    = list(unmatched_rows[0].keys()) if unmatched_rows else []

    # Find current max product_id across both files
    all_pids = [
        int(r["product_id"])
        for r in ids_rows + unmatched_rows
        if r.get("product_id", "").strip()
    ]
    next_id = (max(all_pids) + 1) if all_pids else 1

    # Build normalised-name → product_id map from all already-filled rows
    # Include ids_rows so new own_site rows match existing Amazon product_ids
    name_to_pid: dict[tuple[str, str], int] = {}
    for r in ids_rows + unmatched_rows:
        pid = r.get("product_id", "").strip()
        if pid:
            key = (r["brand"].strip(), normalise_name(r["product_name"]))
            name_to_pid.setdefault(key, int(pid))

    # Assign missing product_ids
    assigned = 0
    for r in unmatched_rows:
        if r.get("product_id", "").strip():
            continue
        key = (r["brand"].strip(), normalise_name(r["product_name"]))
        if key not in name_to_pid:
            name_to_pid[key] = next_id
            next_id += 1
        r["product_id"] = str(name_to_pid[key])
        assigned += 1

    # Write back
    with open(UNMATCHED_REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=sep)
        w.writeheader()
        w.writerows(unmatched_rows)

    print(f"Assigned {assigned} new product_ids (next_id stopped at {next_id - 1})")
    print(f"unmatched_review.csv: {len(unmatched_rows)} rows, all product_ids filled")


if __name__ == "__main__":
    main()
