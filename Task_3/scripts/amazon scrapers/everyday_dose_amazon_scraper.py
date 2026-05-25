#!/usr/bin/env python3
"""
everyday_dose_amazon_scraper.py
Scrapes Everyday Dose Amazon catalog via search result pages (storefront is JS-rendered).
Matcha products are not linked from the main storefront, so a dedicated matcha search
URL is included in _SEARCH_URLS.
Output: data/raw/everyday_dose_amazon.csv

Usage:
  python scripts/everyday_dose_amazon_scraper.py           # full run
  python scripts/everyday_dose_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
import random

from bs4 import BeautifulSoup
from amazon_scraper_template import AmazonScraperBase

_SEARCH_URLS = [
    "https://www.amazon.com/s?k=everyday+dose+mushroom+coffee&i=grocery-intl-ship",
    "https://www.amazon.com/s?k=everyday+dose+matcha&i=grocery-intl-ship",
    "https://www.amazon.com/s?k=everyday+dose&i=grocery-intl-ship",
]


class EverydayDoseScraper(AmazonScraperBase):
    BRAND          = "Everyday Dose"
    SEED_ASIN      = "B0CD2RCND5"
    STOREFRONT_URL = _SEARCH_URLS[0]   # run() fetches this and passes HTML to get_asins_from_storefront
    OUT_FILENAME   = "everyday_dose_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "packet": ["stick pack", "stick"],
    }

    EXTRA_INGREDIENT_KW = {
        "collagen": ["collagen"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "shaker", "protein bar", "snack bar", "electrolyte",
    ]

    def _asins_from_search_html(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        asins = []
        for card in soup.select('[data-component-type="s-search-result"]'):
            asin = card.get("data-asin", "").strip()
            if not re.fullmatch(r"[A-Z0-9]{10}", asin):
                continue
            title_el = card.select_one("h2 span")
            title = title_el.get_text(strip=True) if title_el else ""
            if "everyday dose" in title.lower():
                asins.append(asin)
        return asins

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Collect ASINs from all search pages, filtering by brand name in card title."""
        asins = self._asins_from_search_html(html)
        for url in _SEARCH_URLS[1:]:
            self.safe_print(f"  Fetching search page: {url[:80]}")
            page_html = self.fetch_html(url)
            if page_html:
                asins.extend(a for a in self._asins_from_search_html(page_html) if a not in asins)
            time.sleep(random.uniform(3, 5))
        return list(dict.fromkeys(asins))

    def _is_everyday_dose(self, title: str) -> bool:
        # Real brand titles start with "Everyday Dose"; mid-title = third-party descriptor
        return title.lower().startswith("everyday dose")

    def is_merch(self, title: str) -> bool:
        if not self._is_everyday_dose(title):
            return True
        return super().is_merch(title)

    def get_asins_from_twister(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else ""
        if not self._is_everyday_dose(title):
            return []
        return super().get_asins_from_twister(html)


if __name__ == "__main__":
    EverydayDoseScraper().run(pilot="--pilot" in sys.argv)
