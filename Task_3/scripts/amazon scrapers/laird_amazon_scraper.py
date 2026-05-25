#!/usr/bin/env python3
"""
laird_amazon_scraper.py
Scrapes Laird Superfood Amazon catalog via search result pages (storefront is JS-rendered).
Output: data/raw/laird_amazon.csv

Usage:
  python scripts/laird_amazon_scraper.py           # full run
  python scripts/laird_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys

from bs4 import BeautifulSoup
from amazon_scraper_template import AmazonScraperBase

_SEARCH_URLS = [
    "https://www.amazon.com/s?k=laird+superfood&i=grocery-intl-ship",
    "https://www.amazon.com/s?k=laird+superfood&i=grocery-intl-ship&page=2",
    "https://www.amazon.com/s?k=laird+superfood+creamer&i=grocery-intl-ship",
    "https://www.amazon.com/s?k=laird+superfood+instafuel&i=grocery-intl-ship",
]


class LairdScraper(AmazonScraperBase):
    BRAND          = "Laird Superfood"
    SEED_ASIN      = "B088PB9B1L"
    STOREFRONT_URL = _SEARCH_URLS[0]
    EXTRA_STOREFRONT_URLS = _SEARCH_URLS[1:]   # base class iterates all 4 independently
    OUT_FILENAME   = "laird_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "creamer": ["creamer", "superfood creamer", "original creamer"],
        "instant": ["instafuel"],
        "ground":  ["ground coffee"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "shaker", "hydrate", "hydration", "protein bar", "snack bar",
        "electrolyte", "superfood bar",
    ]

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Parse search result cards; only keep ASINs where brand name contains 'laird'."""
        soup = BeautifulSoup(html, "lxml")
        asins = []
        for card in soup.select('[data-component-type="s-search-result"]'):
            asin = card.get("data-asin", "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin):
                continue
            title_el = card.select_one("h2 span")
            title = title_el.get_text(strip=True) if title_el else ""
            if "laird" in title.lower():
                asins.append(asin)
        return asins



if __name__ == "__main__":
    LairdScraper().run(pilot="--pilot" in sys.argv)
