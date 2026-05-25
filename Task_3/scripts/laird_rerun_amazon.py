#!/usr/bin/env python3
"""
laird_rerun_amazon.py — Re-scrape Laird Superfood Amazon into a clean isolated folder.
Inherits all scraping logic from amazon scrapers/laird_amazon_scraper.py.
Narrow filter: keep only coffee / cocoa / cacao / creamer products.
Output: data/laird_rerun/laird_amazon_raw.csv
"""

import sys
from pathlib import Path

ROOT      = Path(__file__).parent.parent
RERUN_DIR = ROOT / "data" / "laird_rerun"
RERUN_DIR.mkdir(parents=True, exist_ok=True)

# Allow laird_amazon_scraper's imports to resolve (needs both scripts/ and amazon scrapers/)
sys.path.insert(0, str(Path(__file__).parent / "amazon scrapers"))
sys.path.insert(0, str(Path(__file__).parent))

# amazon_scraper_template.RAW_DIR resolves to scripts/data/raw (two parents up from
# scripts/amazon scrapers/), which doesn't exist. Patch it before any class is instantiated.
import amazon_scraper_template as _amz_tpl  # noqa: E402
_amz_tpl.RAW_DIR = ROOT / "data" / "raw"
(ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)

from laird_amazon_scraper import LairdScraper as _LairdAmazonBase  # noqa: E402

_NARROW_KW = ["coffee", "cocoa", "cacao", "creamer", "instafuel", "dark roast", "espresso"]
_BUNDLE_KW = ["bundle", "kit", "set"]


class LairdRerunAmazonScraper(_LairdAmazonBase):
    def __init__(self) -> None:
        super().__init__()
        self.out_file = RERUN_DIR / "laird_amazon_raw.csv"

    def infer_format(self, text: str) -> str:
        low = text.lower()
        if any(kw in low for kw in _BUNDLE_KW):
            return "bundle"
        return super().infer_format(text)

    def is_merch(self, title: str) -> bool:
        if super().is_merch(title):
            return True
        low = title.lower()
        if any(kw in low for kw in _BUNDLE_KW):
            return False
        fmt = self.infer_format(title)
        if fmt == "creamer":
            return False
        return not any(kw in low for kw in _NARROW_KW)


if __name__ == "__main__":
    import sys as _sys
    LairdRerunAmazonScraper().run(pilot="--pilot" in _sys.argv)
