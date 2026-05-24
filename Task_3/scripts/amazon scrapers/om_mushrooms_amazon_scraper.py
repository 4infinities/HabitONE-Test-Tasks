#!/usr/bin/env python3
"""
om_mushrooms_amazon_scraper.py
Scrapes Om Mushrooms Amazon storefront (4 category sections).
Keeps only coffee / matcha / cacao / creamer products.
Output: data/raw/om_mushrooms_amazon.csv

Usage:
  python scripts/om_mushrooms_amazon_scraper.py           # full run
  python scripts/om_mushrooms_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
from amazon_scraper_template import AmazonScraperBase


class OmMushroomsScraper(AmazonScraperBase):
    BRAND          = "Om Mushrooms"
    SEED_ASIN      = "B09G9B95D2"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/84AF68CB-A532-4E0F-BB1C-5200B9E28AC4"
        "?ingress=2&lp_context_asin=B09FD8C16B"
    )
    OUT_FILENAME   = "om_mushrooms_amazon.csv"
    DEFAULT_FORMAT = "instant"

    # Only keep coffee-adjacent items; everything else (pure supplements) is skipped
    ACCEPT_KW = ["coffee", "matcha", "cacao", "cocoa", "creamer", "latte"]

    EXTRA_FORMAT_KW = {
        "creamer": ["creamer"],
        "instant": ["coffee", "cacao", "cocoa", "matcha", "latte"],
    }

    def is_merch(self, title: str) -> bool:
        if super().is_merch(title):
            return True
        low = title.lower()
        return not any(k in low for k in self.ACCEPT_KW)

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Collect ASINs from the main store page + all sub-pages (4 category sections)."""
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)

        # Each category section is a separate stores/page/UUID sub-page
        sub_uuids = re.findall(
            r"/stores/(?:[^/\"]+/)?page/([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})",
            html,
        )
        main_uuid = "84AF68CB-A532-4E0F-BB1C-5200B9E28AC4"
        sub_uuids = [u for u in dict.fromkeys(sub_uuids) if u != main_uuid]

        for uuid in sub_uuids:
            sub_url = f"https://www.amazon.com/stores/page/{uuid}"
            self.safe_print(f"  Fetching sub-page: {sub_url}")
            sub_html = self.fetch_html(sub_url)
            if sub_html:
                asins += re.findall(r"/dp/([A-Z0-9]{10})", sub_html)
            time.sleep(3)

        return list(dict.fromkeys(asins))


if __name__ == "__main__":
    OmMushroomsScraper().run(pilot="--pilot" in sys.argv)
