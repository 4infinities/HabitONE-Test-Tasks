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
import time
from amazon_scraper_template import AmazonScraperBase


class MudWtrScraper(AmazonScraperBase):
    BRAND          = "MudWtr"
    SEED_ASIN      = "B0D1J7XPJK"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/page/8EFFF509-F011-4BCD-8FEC-19E97079FE49"
        "?ingress=2&lp_context_asin=B0D1J7XPJK"
    )
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
        """Collect ASINs from main page + all category sub-pages."""
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)

        main_uuid = "8EFFF509-F011-4BCD-8FEC-19E97079FE49"
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
    MudWtrScraper().run(pilot="--pilot" in sys.argv)
