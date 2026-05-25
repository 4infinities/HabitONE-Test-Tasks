#!/usr/bin/env python3
"""
laird_rerun_site.py — Re-scrape Laird Superfood own site into a clean isolated folder.
Inherits all scraping logic from website_scrapers/laird_scraper.py.
Narrow filter: keep only coffee / cocoa / cacao / creamer products.
Output: data/laird_rerun/laird_site_raw.csv
"""

import sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
RERUN_DIR = ROOT / "data" / "laird_rerun"
RERUN_DIR.mkdir(parents=True, exist_ok=True)

# Allow LairdScraper's own imports to resolve
sys.path.insert(0, str(Path(__file__).parent))

from website_scrapers.laird_scraper import LairdScraper  # noqa: E402

_NARROW_KW = ["coffee", "cocoa", "cacao", "creamer", "instafuel", "dark roast", "espresso"]
_BUNDLE_KW = ["bundle", "kit", "set"]


class LairdRerunSiteScraper(LairdScraper):
    def __init__(self) -> None:
        super().__init__()
        self.out_file = RERUN_DIR / "laird_site_raw.csv"

    def build_rows(self, handle, product, session):
        rows = super().build_rows(handle, product, session)
        result = []
        for r in rows:
            if _is_bundle(r["product_name"]):
                r["format"] = "bundle"
                result.append(r)
            elif _is_target(r["product_name"], r["format"]):
                result.append(r)
        if rows and not result:
            self._p(f"    NARROW-FILTER dropped: {rows[0]['product_name'][:60]}")
        return result


def _is_bundle(name: str) -> bool:
    low = name.lower()
    return any(kw in low for kw in _BUNDLE_KW)


def _is_target(name: str, fmt: str) -> bool:
    if fmt == "creamer":
        return True
    low = name.lower()
    return any(kw in low for kw in _NARROW_KW)


if __name__ == "__main__":
    LairdRerunSiteScraper().run()
