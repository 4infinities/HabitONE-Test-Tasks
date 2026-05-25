#!/usr/bin/env python3
"""
mudwtr_amazon_scraper.py
Scrapes MudWtr Amazon storefront (multiple category sub-pages).
Output: data/raw/mudwtr_amazon.csv

Usage:
  python scripts/mudwtr_amazon_scraper.py           # full run
  python scripts/mudwtr_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
from bs4 import BeautifulSoup
from amazon_scraper_template import AmazonScraperBase

# Amazon search pages include all MudWtr products via data-asin attributes
# in static HTML — more reliable than the JS-rendered brand storefront.
_SEARCH_URLS = [
    "https://www.amazon.com/s?k=mudwtr&i=grocery-intl-ship",
    "https://www.amazon.com/s?k=mudwtr&i=grocery-intl-ship&page=2",
]


class MudWtrScraper(AmazonScraperBase):
    BRAND          = "MudWtr"
    SEED_ASIN      = "B0D1J7XPJK"
    STOREFRONT_URL = _SEARCH_URLS[0]   # used only as fallback label; real discovery below
    OUT_FILENAME   = "mudwtr_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "creamer": ["creamer", "oat milk"],
        "instant": [":rise", ":rest", "cacao", "chai"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle",
        "shaker", "kit", "starter",
    ]

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """
        MudWtr's brand storefront is fully JS-rendered; curl_cffi only sees
        skeleton HTML. STOREFRONT_URL points to search page 1 — use that HTML
        directly, then fetch page 2.
        """
        asins = []
        for page_html in [html, self.fetch_html(_SEARCH_URLS[1])]:
            if not page_html:
                continue
            soup = BeautifulSoup(page_html, "lxml")
            for el in soup.find_all(attrs={"data-asin": True}):
                asin = el["data-asin"].strip()
                if re.fullmatch(r"[A-Z0-9]{10}", asin):
                    asins.append(asin)
        return list(dict.fromkeys(asins))

    def _is_mudwtr(self, title: str) -> bool:
        # Brand appears as "MUDWTR" or "MUD\WTR" on Amazon
        return bool(re.search(r"mud.?wtr", title, re.IGNORECASE))

    def is_merch(self, title: str) -> bool:
        """Skip non-MudWtr products that appear in search results."""
        if not self._is_mudwtr(title):
            return True
        return super().is_merch(title)

    def get_asins_from_twister(self, html: str) -> list[str]:
        """Only discover variants for MudWtr's own product pages."""
        from bs4 import BeautifulSoup as _BS
        soup = _BS(html, "lxml")
        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else ""
        if not self._is_mudwtr(title):
            return []
        return super().get_asins_from_twister(html)


if __name__ == "__main__":
    MudWtrScraper().run(pilot="--pilot" in sys.argv)
