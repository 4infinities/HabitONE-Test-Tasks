#!/usr/bin/env python3
"""
la_republica_amazon_scraper.py
La Republica storefront: multiple category sub-pages + per-product twister variants.
Sub-page UUIDs are discovered from the main store HTML automatically.
Twister variants on each product page are handled by the base class run() loop.
Output: data/raw/la_republica_amazon.csv

Usage:
  python scripts/la_republica_amazon_scraper.py           # full run
  python scripts/la_republica_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import time
from amazon_scraper_template import AmazonScraperBase


class LaRepublicaScraper(AmazonScraperBase):
    BRAND          = "La Republica"
    SEED_ASIN      = "B078XR2R6B"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/LaRepublica/page/08A24069-1E8E-4D1A-8CF3-A472F005748D"
        "?lp_asin=B078XR2R6B&ref_=ast_bln"
    )
    OUT_FILENAME           = "la_republica_amazon.csv"
    DEFAULT_FORMAT         = "ground"  # La Republica is primarily ground/instant mushroom coffee
    AUTO_DISCOVER_SUBPAGES = False      # get_asins_from_storefront already handles sub-pages

    EXTRA_FORMAT_KW = {
        "instant": ["instant", "powder", "powdered", "mushroom coffee powder"],
        "ground":  ["ground", "whole bean", "organic ground"],
        "packet":  ["single serve", "packet", "sachet"],
        "capsule": ["capsule", "supplement"],
    }

    SKIP_KW = [
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle", "shaker",
    ]

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Collect ASINs from main store page + all category sub-pages."""
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)

        main_uuid = "08A24069-1E8E-4D1A-8CF3-A472F005748D"
        sub_uuids = re.findall(
            r"/stores/(?:[^/\"]+/)?page/([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})",
            html,
        )
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
    LaRepublicaScraper().run(pilot="--pilot" in sys.argv)
