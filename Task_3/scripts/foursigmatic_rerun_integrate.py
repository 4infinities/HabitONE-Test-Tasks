#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
foursigmatic_rerun_integrate.py — one-shot integration.

Steps:
  1. Extract all Four Sigmatic rows from unmatched_review.csv
  2. Match Amazon names -> site canonical names (same logic as match script)
  3. Assign new global product_ids (max+1 across both files)
  4. Move all FS rows to all_brands_ids.csv with brand_id=4
  5. Remove FS rows from unmatched_review.csv
  6. Keep existing pids 15-28 in all_brands_ids untouched

Run:
  python scripts/foursigmatic_rerun_integrate.py
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT      = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
ALL_IDS   = PROCESSED / "all_brands_ids.csv"
UNMATCHED = PROCESSED / "unmatched_review.csv"

FS_BRAND    = "Four Sigmatic"
FS_BRAND_ID = "4"

FIELDS = [
    "brand_id", "product_id", "brand", "product_name", "format",
    "serving_size_g", "serving_count", "volume_g", "price_usd",
    "discount_pct", "serving_price", "key_ingredient",
    "channel", "url", "date_collected", "purchase_type",
]

# ── Matching logic (same as foursigmatic_rerun_match.py) ─────────────────────

_STOP = {
    "four", "sigmatic", "organic", "mushroom", "coffee", "arabica",
    "with", "and", "for", "the", "of", "in", "by", "from",
    "your", "that", "this", "more", "plus", "made",
    "blend", "extract", "powder", "mix", "superfood", "functional",
    "serving", "servings", "count", "pack", "size", "large", "small",
    "great", "taste", "smooth", "energy", "support",
    "process", "swiss", "water", "roasted", "beans",
    "high", "dose", "adaptogen", "gourmet", "grade", "certified",
    "think", "prime",
}

_ANCHOR = {
    "focus", "calm", "gut", "health", "balance", "boys", "original",
    "latte", "espresso", "brew", "cacao", "cocoa", "reishi", "chai",
}

_TYPO = {"originnal": "original"}

_FORMAT_COMPAT = {
    frozenset({"instant", "packet"}),
    frozenset({"ground", "whole"}),
}

_INCOMPATIBLE_PAIRS = [
    ("half", "caffeine"),
    ("decaf", "caffeine"),
]

_SUBBRAND = {"max", "boost"}


def _kw(name: str, apply_typo: bool = False) -> set[str]:
    name = name.lower()
    if apply_typo:
        for wrong, right in _TYPO.items():
            name = name.replace(wrong, right)
    words = re.findall(r"[a-z]+", name)
    return {w for w in words if len(w) >= 3 and w not in _STOP}


def _fmt_compat(a: str, b: str) -> bool:
    if not a or not b or a == b:
        return True
    return frozenset({a, b}) in _FORMAT_COMPAT


def _incompatible(a_kw: set, s_kw: set) -> bool:
    for w1, w2 in _INCOMPATIBLE_PAIRS:
        if (w1 in a_kw and w2 in s_kw) or (w2 in a_kw and w1 in s_kw):
            return True
    if "cold" in a_kw and "brew" in a_kw and "brew" not in s_kw:
        return True
    for sb in _SUBBRAND:
        if (sb in a_kw) != (sb in s_kw):
            return True
    return False


def _best_site_match(amz_row: dict, site_rows: list[dict]) -> str | None:
    a_kw      = _kw(amz_row["product_name"])
    a_fmt     = amz_row["format"].lower()
    a_anchors = a_kw & _ANCHOR

    best_name, best_score, best_ratio = None, 0, 0.0

    for s in site_rows:
        s_fmt = s["format"].lower()
        if not _fmt_compat(a_fmt, s_fmt):
            continue
        s_kw      = _kw(s["product_name"], apply_typo=True)
        s_anchors = s_kw & _ANCHOR
        if a_anchors and s_anchors and not (a_anchors & s_anchors):
            continue
        if _incompatible(a_kw, s_kw):
            continue
        shared = a_kw & s_kw
        score  = len(shared)
        ratio  = score / max(len(s_kw), 1)
        if score > best_score or (score == best_score and ratio > best_ratio):
            best_score, best_ratio, best_name = score, ratio, s["product_name"]

    if best_name is None or best_score < 1:
        return None
    s_kw   = _kw(best_name, apply_typo=True)
    shared = a_kw & s_kw
    if best_score == 1:
        if not (s_kw and s_kw.issubset(a_kw) and (shared & _ANCHOR)):
            return None
    elif not (shared & _ANCHOR) and best_score < 3:
        return None
    return best_name


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def main() -> None:
    all_rows = _load(ALL_IDS)
    unm_rows = _load(UNMATCHED)

    # Global max product_id across both files
    max_pid = max(
        (int(r["product_id"]) for r in all_rows + unm_rows
         if r.get("product_id", "").strip().isdigit()),
        default=0,
    )
    print(f"Global max product_id: {max_pid}")

    # Separate FS rows from unmatched_review
    fs_unm     = [r for r in unm_rows if FS_BRAND in r.get("brand", "")]
    non_fs_unm = [r for r in unm_rows if FS_BRAND not in r.get("brand", "")]
    print(f"FS rows in unmatched_review: {len(fs_unm)}")

    # Group FS unmatched rows by existing product_id
    by_pid: dict[str, list[dict]] = defaultdict(list)
    for r in fs_unm:
        by_pid[r["product_id"]].append(r)

    # Classify by channels
    both_chan: list[str] = []
    site_only: list[str] = []
    amz_only:  list[str] = []
    for pid, rows in by_pid.items():
        chans = {r["channel"] for r in rows}
        if "own_site" in chans and "amazon" in chans:
            both_chan.append(pid)
        elif "own_site" in chans:
            site_only.append(pid)
        else:
            amz_only.append(pid)

    # Build site canonical index
    site_reprs = [
        {"product_name": by_pid[pid][0]["product_name"],
         "format":       by_pid[pid][0]["format"],
         "pid":          pid}
        for pid in site_only
    ]

    # Match Amazon -> site
    amz_to_site: dict[str, str] = {}
    for amz_pid in amz_only:
        amz_repr     = by_pid[amz_pid][0]
        matched_name = _best_site_match(amz_repr, site_reprs)
        if matched_name:
            site_pid = next(s["pid"] for s in site_reprs if s["product_name"] == matched_name)
            amz_to_site[amz_pid] = site_pid

    matched_site_pids = set(amz_to_site.values())

    print(f"Matched Amazon pids -> site pids: {len(amz_to_site)}")
    print(f"Unique matched site pids: {len(matched_site_pids)}")

    # ── Assign new global product_ids ─────────────────────────────────────────
    next_pid = max_pid + 1
    old_to_new: dict[str, str] = {}   # old (unmatched_review) pid -> new global pid

    # 1. Both-channel groups
    for pid in both_chan:
        old_to_new[pid] = str(next_pid)
        next_pid += 1

    # 2. Site pids that have Amazon matches (canonical group)
    for site_pid in sorted(matched_site_pids, key=lambda x: int(x) if x.isdigit() else 0):
        old_to_new[site_pid] = str(next_pid)
        next_pid += 1

    # 3. Unmatched site pids
    for pid in site_only:
        if pid not in matched_site_pids:
            old_to_new[pid] = str(next_pid)
            next_pid += 1

    # 4. Amazon pids that matched a site pid → use the site pid's new global id
    for amz_pid, site_pid in amz_to_site.items():
        old_to_new[amz_pid] = old_to_new[site_pid]

    # 5. Unmatched Amazon pids
    for pid in amz_only:
        if pid not in amz_to_site:
            old_to_new[pid] = str(next_pid)
            next_pid += 1

    print(f"New product_ids range: {max_pid + 1} .. {next_pid - 1}")

    # ── Build new rows ─────────────────────────────────────────────────────────
    # For matched groups: Amazon rows get site canonical product_name
    # For site-only canonical names: use site product_name (correcting typo)
    canonical_name: dict[str, str] = {}   # site_pid -> canonical name

    for site_pid in matched_site_pids | set(p for p in site_only if p not in matched_site_pids):
        raw = by_pid[site_pid][0]["product_name"]
        # Apply typo correction to the stored canonical name
        fixed = raw
        for wrong, right in _TYPO.items():
            fixed = fixed.lower().replace(wrong, right).title() if wrong in raw.lower() else raw
        canonical_name[site_pid] = fixed

    new_fs_rows: list[dict] = []

    for old_pid, rows in by_pid.items():
        new_pid = old_to_new[old_pid]

        # Determine canonical product_name for this group
        if old_pid in amz_to_site:
            # Amazon group matched to site → use site canonical name
            site_pid = amz_to_site[old_pid]
            canon    = canonical_name[site_pid]
        elif old_pid in canonical_name:
            canon = canonical_name[old_pid]
        else:
            # Amazon-only, no match → keep Amazon name
            canon = rows[0]["product_name"]

        for r in rows:
            new_row = {
                "brand_id":   FS_BRAND_ID,
                "product_id": new_pid,
                "brand":      FS_BRAND,
                "product_name": canon,
                **{k: r.get(k, "").strip() for k in FIELDS[3:]},
            }
            new_fs_rows.append(new_row)

    # ── Write all_brands_ids ──────────────────────────────────────────────────
    output_ids = all_rows + new_fs_rows

    with open(ALL_IDS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(output_ids)

    # ── Write unmatched_review (FS rows removed) ──────────────────────────────
    with open(UNMATCHED, "w", newline="", encoding="utf-8") as f:
        # Preserve original columns from unmatched_review
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(non_fs_unm)

    print(f"\nWrote {len(output_ids)} rows to all_brands_ids.csv")
    print(f"  Existing (unchanged): {len(all_rows)}")
    print(f"  New FS rows added   : {len(new_fs_rows)}")
    print(f"\nUnmatched_review: {len(non_fs_unm)} rows (removed {len(fs_unm)} FS rows)")
    print(f"New product_ids: {max_pid + 1}..{next_pid - 1}")


if __name__ == "__main__":
    main()
