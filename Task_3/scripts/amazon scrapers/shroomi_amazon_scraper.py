#!/usr/bin/env python3
"""
shroomi_amazon_scraper.py
Scrapes all Shroomi products from their Amazon storefront.
Output: data/raw/shroomi_amazon.csv

Usage:
  python scripts/shroomi_amazon_scraper.py           # full run
  python scripts/shroomi_amazon_scraper.py --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
from amazon_scraper_template import AmazonScraperBase


class ShroomiScraper(AmazonScraperBase):
    BRAND          = "Shroomi"
    SEED_ASIN      = "B0921ML8NR"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/Shroomi/page/6852FD24-BA12-4F1B-B3A4-4F7B8FA7ED06"
        "?lp_asin=B0921ML8NR&ref_=ast_bln"
    )
    OUT_FILENAME   = "shroomi_amazon.csv"
    DEFAULT_FORMAT = "instant"

    EXTRA_FORMAT_KW = {
        "packet": ["variety", "sampler", "single serve"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["10 mushroom", "7 mushroom", "organic mushroom"],
    }

    MAIN_UUID = "6852FD24-BA12-4F1B-B3A4-4F7B8FA7ED06"

    def get_asins_from_storefront(self, html: str) -> list[str]:
        """Collect ASINs from main store page + all category sub-pages."""
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
    ShroomiScraper().run(pilot="--pilot" in sys.argv)
