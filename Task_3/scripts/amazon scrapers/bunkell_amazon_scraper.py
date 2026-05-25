#!/usr/bin/env python3
"""
bunkell_amazon_scraper.py
Scrapes all Bunkell products from Amazon via search results (storefront is JS-rendered).
Output: data/raw/bunkell_amazon.csv

Usage:
  python scripts/bunkell_amazon_scraper.py           # full run
  python scripts/bunkell_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup
from amazon_scraper_template import AmazonScraperBase

_SEARCH_URLS = [
    "https://www.amazon.com/s?k=bunkell",
    "https://www.amazon.com/s?k=bunkell&page=2",
]


class BunkellScraper(AmazonScraperBase):
    BRAND          = "Bunkell"
    SEED_ASIN      = "B0DHP915W6"
    STOREFRONT_URL = _SEARCH_URLS[0]
    EXTRA_STOREFRONT_URLS = _SEARCH_URLS[1:]
    OUT_FILENAME   = "bunkell_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "capsule": ["capsule", "pill", "supplement"],
        "packet":  ["packet", "sachet", "single serve", "stick"],
        "instant": ["powder", "instant", "mushroom coffee", "blend"],
        "creamer": ["creamer"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["7 mushroom", "10 mushroom", "multi mushroom", "mushroom complex"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "adaptogen":      ["ashwagandha", "rhodiola", "adaptogen"],
    }

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Parse search result cards; only keep ASINs from Bunkell brand cards."""
        soup = BeautifulSoup(html, "lxml")
        asins = []
        for card in soup.select('[data-component-type="s-search-result"]'):
            asin = card.get("data-asin", "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin):
                continue
            title_el = card.select_one("h2 span")
            title = title_el.get_text(strip=True) if title_el else ""
            if "bunkell" in title.lower():
                asins.append(asin)
        return asins


if __name__ == "__main__":
    BunkellScraper().run(pilot="--pilot" in sys.argv)
