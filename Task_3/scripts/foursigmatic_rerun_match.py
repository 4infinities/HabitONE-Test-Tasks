#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
foursigmatic_rerun_match.py
Reads all Four Sigmatic rows from unmatched_review.csv, matches Amazon
names to site canonical names, outputs matched + unmatched lists.

Usage:
  python scripts/foursigmatic_rerun_match.py
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT      = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"

UNMATCHED_FILE = PROCESSED / "unmatched_review.csv"

FS_BRAND = "Four Sigmatic"

# Words to strip when comparing names
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

# Product-line / category anchor words — meaningful discriminators
_ANCHOR = {
    "focus", "calm", "gut", "health", "balance", "boys", "original",
    "latte", "espresso", "brew", "cacao", "cocoa", "reishi", "chai",
}

# Typo corrections for site names
_TYPO = {
    "originnal": "original",
}

# Formats considered compatible for matching
_FORMAT_COMPAT = {
    frozenset({"instant", "packet"}),
    frozenset({"ground", "whole"}),
}

# Keyword pairs that are INCOMPATIBLE (one in Amazon, the opposite in site)
# If both words appear (one per side), reject the match.
_INCOMPATIBLE_PAIRS = [
    ("half",  "caffeine"),   # "half caf" vs "high caffeine" — different caffeine levels
    ("decaf", "caffeine"),   # decaf vs caffeinated
]

# Sub-brand keywords: if one side has it, the other must too (or reject)
_SUBBRAND = {"max", "boost"}


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


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
    """Return True if the two keyword sets signal opposite product variants."""
    for w1, w2 in _INCOMPATIBLE_PAIRS:
        if (w1 in a_kw and w2 in s_kw) or (w2 in a_kw and w1 in s_kw):
            return True
    # Cold brew: if Amazon name has cold+brew but site doesn't have brew
    if "cold" in a_kw and "brew" in a_kw and "brew" not in s_kw:
        return True
    # Sub-brand mismatch: e.g. "Focus Max" must match "Focus Max", not "Focus"
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

        # Both names have anchor keywords but no anchor in common → skip
        if a_anchors and s_anchors and not (a_anchors & s_anchors):
            continue

        if _incompatible(a_kw, s_kw):
            continue

        shared = a_kw & s_kw
        score  = len(shared)
        # Tiebreaker: prefer site name where more of its keywords are covered
        ratio  = score / max(len(s_kw), 1)

        if score > best_score or (score == best_score and ratio > best_ratio):
            best_score, best_ratio, best_name = score, ratio, s["product_name"]

    if best_name is None or best_score < 1:
        return None
    s_kw   = _kw(best_name, apply_typo=True)
    shared = a_kw & s_kw
    # Allow score=1 if all site keywords are covered by Amazon name (subset match)
    # and the shared keyword is an anchor — signals unambiguous product identity.
    if best_score == 1:
        if not (s_kw and s_kw.issubset(a_kw) and (shared & _ANCHOR)):
            return None
    # General threshold: without shared anchor, require score >= 3
    elif not (shared & _ANCHOR) and best_score < 3:
        return None
    return best_name


def main() -> None:
    unmatched = _load(UNMATCHED_FILE)

    fs_rows = [r for r in unmatched if FS_BRAND in r.get("brand", "")]
    print(f"Four Sigmatic rows in unmatched_review: {len(fs_rows)}")

    by_pid: dict[str, list[dict]] = defaultdict(list)
    for r in fs_rows:
        by_pid[r["product_id"]].append(r)

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

    print(f"  Both-channel pids : {len(both_chan)} -> {both_chan}")
    print(f"  Site-only pids    : {len(site_only)}")
    print(f"  Amazon-only pids  : {len(amz_only)}")

    site_reprs: list[dict] = []
    for pid in site_only:
        r = by_pid[pid][0]
        site_reprs.append({
            "product_name": r["product_name"],
            "format":       r["format"],
            "pid":          pid,
        })

    amz_to_site: dict[str, str] = {}
    print("\n=== Proposed Amazon -> Site matches ===")
    for amz_pid in amz_only:
        amz_repr     = by_pid[amz_pid][0]
        matched_name = _best_site_match(amz_repr, site_reprs)
        if matched_name:
            site_pid = next(s["pid"] for s in site_reprs if s["product_name"] == matched_name)
            amz_to_site[amz_pid] = site_pid
            print(f"  AMZ pid={amz_pid:>3}: {amz_repr['product_name'][:55]}")
            print(f"       -> pid={site_pid:>3}: {matched_name}")

    print(f"\nMatched   : {len(amz_to_site)} Amazon pids -> site pids")

    unmatched_amz  = [p for p in amz_only  if p not in amz_to_site]
    unmatched_site = [p for p in site_only if p not in amz_to_site.values()]

    print(f"\nUnmatched Amazon pids ({len(unmatched_amz)}):")
    for p in unmatched_amz:
        r = by_pid[p][0]
        print(f"  pid={p:>3} fmt={r['format']:>8} | {r['product_name'][:65]}")

    print(f"\nUnmatched site pids ({len(unmatched_site)}):")
    for p in unmatched_site:
        r = by_pid[p][0]
        print(f"  pid={p:>3} fmt={r['format']:>8} | {r['product_name'][:65]}")

    print(f"\nBoth-channel (pre-matched): {both_chan}")


if __name__ == "__main__":
    main()
