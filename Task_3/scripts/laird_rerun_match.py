#!/usr/bin/env python3
"""
laird_rerun_match.py — Match Laird site vs Amazon rerun data.
Loads data/laird_rerun/laird_site_raw.csv + laird_amazon_raw.csv,
applies the narrow coffee/cocoa/cacao/creamer filter,
matches Amazon product names → canonical site names,
assigns product_id, and writes:
  data/laird_rerun/laird_matched.csv
  data/laird_rerun/laird_unmatched.csv

Logic adapted from scripts/04_filter_merge.py and scripts/05_assign_ids.py.
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT      = Path(__file__).parent.parent
RERUN_DIR = ROOT / "data" / "laird_rerun"

SITE_FILE   = RERUN_DIR / "laird_site_raw.csv"
AMAZON_FILE = RERUN_DIR / "laird_amazon_raw.csv"
OUT_MATCHED   = RERUN_DIR / "laird_matched.csv"
OUT_UNMATCHED = RERUN_DIR / "laird_unmatched.csv"

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]
OUT_FIELDS = ["product_id"] + CSV_FIELDS

_NARROW_KW = ["coffee", "cocoa", "cacao", "creamer", "instafuel", "dark roast", "espresso"]
_BUNDLE_KW = ["bundle", "kit", "set"]

_MATCH_STOP = {
    "mushroom", "organic", "with", "and", "for", "the", "of", "in", "by",
    "blend", "extract", "powder", "mix", "superfood", "functional",
    "serving", "servings", "count", "pack", "size", "large", "small",
    "from", "your", "that", "this", "more", "plus", "made", "great",
    "taste", "smooth", "energy", "support", "boost", "laird",
}


# ── I/O ───────────────────────────────────────────────────────────────────────

def _detect_sep(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        line = f.readline()
    return ";" if line.count(";") > line.count(",") else ","


def _load(path: Path) -> list[dict]:
    sep = _detect_sep(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=sep))


def _normalise(row: dict) -> dict:
    if "url" not in row and "source_url" in row:
        row["url"] = row.pop("source_url")
    return {k: (row.get(k) or "").strip() for k in CSV_FIELDS}


# ── Filter ─────────────────────────────────────────────────────────────────────

def _is_target(row: dict) -> bool:
    if row["format"] in ("creamer", "bundle"):
        return True
    low = row["product_name"].lower()
    if any(kw in low for kw in _BUNDLE_KW):
        return True
    return any(kw in low for kw in _NARROW_KW)


# ── Name matching (from 04_filter_merge.py) ───────────────────────────────────

def _kw(name: str) -> set:
    words = re.findall(r"[a-z]+", name.lower())
    return {w for w in words if len(w) >= 4 and w not in _MATCH_STOP}


def _safe_int(val: str) -> int | None:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _best_site_name(amazon_row: dict, site_rows: list[dict]) -> str | None:
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


# ── ID assignment (from 05_assign_ids.py) ─────────────────────────────────────

def _assign_ids(site_rows: list[dict], amazon_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    all_rows = site_rows + amazon_rows
    has_both_channels = bool(site_rows) and bool(amazon_rows)

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        groups[r["product_name"]].append(r)

    matched: list[dict]   = []
    unmatched: list[dict] = []
    pid_counter = 0
    pid_map: dict[str, int] = {}

    for pname, group in groups.items():
        channels = {r["channel"] for r in group}
        cross_channel = len(channels) > 1

        if not has_both_channels or cross_channel:
            if pname not in pid_map:
                pid_counter += 1
                pid_map[pname] = pid_counter
            pid = pid_map[pname]
            for r in group:
                matched.append({"product_id": pid, **r})
        else:
            for r in group:
                unmatched.append({"product_id": "", **r})

    channel_order = {"own_site": 0, "amazon": 1}
    unmatched.sort(key=lambda r: (channel_order.get(r["channel"], 9), r["product_name"]))
    return matched, unmatched


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not SITE_FILE.exists():
        print(f"Missing: {SITE_FILE}\nRun laird_rerun_site.py first.")
        return
    if not AMAZON_FILE.exists():
        print(f"Missing: {AMAZON_FILE}\nRun laird_rerun_amazon.py first.")
        return

    raw_site   = [_normalise(r) for r in _load(SITE_FILE)]
    raw_amazon = [_normalise(r) for r in _load(AMAZON_FILE)]

    site_rows   = [r for r in raw_site   if _is_target(r)]
    amazon_rows = [r for r in raw_amazon if _is_target(r)]

    print(f"Site   : {len(raw_site)} raw → {len(site_rows)} kept")
    print(f"Amazon : {len(raw_amazon)} raw → {len(amazon_rows)} kept")

    # Match Amazon names → site canonical names
    n_matched = 0
    for row in amazon_rows:
        matched_name = _best_site_name(row, site_rows)
        if matched_name and matched_name != row["product_name"]:
            print(f"  MATCH: {row['product_name'][:55]}")
            print(f"      → {matched_name}")
            row["product_name"] = matched_name
            n_matched += 1

    print(f"\nName matches: {n_matched}")

    matched, unmatched = _assign_ids(site_rows, amazon_rows)

    with open(OUT_MATCHED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(matched)

    with open(OUT_UNMATCHED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(unmatched)

    print(f"\nMatched   : {len(matched):>3} rows → {OUT_MATCHED.name}")
    print(f"Unmatched : {len(unmatched):>3} rows → {OUT_UNMATCHED.name}")


if __name__ == "__main__":
    main()
