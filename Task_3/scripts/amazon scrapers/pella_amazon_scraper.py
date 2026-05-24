#!/usr/bin/env python3
"""
pella_amazon_scraper.py
Pella Nutrition storefront: main page + category sub-pages discovered automatically.
Output: data/raw/pella_amazon.csv

Usage:
  python scripts/pella_amazon_scraper.py           # full run
  python scripts/pella_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
from amazon_scraper_template import AmazonScraperBase


class PellaScraper(AmazonScraperBase):
    BRAND          = "Pella Nutrition"
    SEED_ASIN      = "B0B5VH84J4"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/PellaNutrition/page/6EA7EB2F-A467-4AEB-94E8-3794ED80CDBF"
        "?lp_asin=B0B5VH84J4&ref_=ast_bln"
    )
    OUT_FILENAME   = "pella_amazon.csv"
    DEFAULT_FORMAT = "instant"  # 7-mushroom blend powders

    EXTRA_FORMAT_KW = {
        "instant": ["mushroom coffee", "instant", "powder", "powdered", "blend"],
        "capsule": ["capsule", "supplement", "pill"],
        "packet":  ["packet", "sachet", "single serve", "stick"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle", "shaker",
    ]

    MAIN_UUID = "6EA7EB2F-A467-4AEB-94E8-3794ED80CDBF"

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Collect ASINs from main store page + all category sub-pages (buttons)."""
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)

        sub_uuids = re.findall(
            r"/stores/(?:[^/\"]+/)?page/([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})",
            html,
        )
        sub_uuids = [u for u in dict.fromkeys(sub_uuids) if u != self.MAIN_UUID]

        for uuid in sub_uuids:
            sub_url = f"https://www.amazon.com/stores/page/{uuid}"
            self.safe_print(f"  Fetching sub-page: {sub_url}")
            sub_html = self.fetch_html(sub_url)
            if sub_html:
                asins += re.findall(r"/dp/([A-Z0-9]{10})", sub_html)
            time.sleep(3)

        return list(dict.fromkeys(asins))


if __name__ == "__main__":
    PellaScraper().run(pilot="--pilot" in sys.argv)
