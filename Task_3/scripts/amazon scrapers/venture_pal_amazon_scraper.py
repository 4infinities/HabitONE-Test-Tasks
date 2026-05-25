#!/usr/bin/env python3
"""
venture_pal_amazon_scraper.py
Scrapes VenturePal functional-coffee/wellness products from their Amazon storefront.
VenturePal sells a broad catalog (outdoor gear, bottles, bags, etc.); only
coffee/mushroom/adaptogen/supplement products are kept via ACCEPT_KW allowlist.
Clickable catalog sub-pages are crawled; size/flavor variants are discovered
via twister on each product page.
Output: data/raw/venture_pal_amazon.csv

Usage:
  python "scripts/amazon scrapers/venture_pal_amazon_scraper.py"           # full run
  python "scripts/amazon scrapers/venture_pal_amazon_scraper.py" --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase


class VenturePalScraper(AmazonScraperBase):
    BRAND          = "VenturePal"
    SEED_ASIN      = "B0DDCJFFBM"
    STOREFRONT_URL = (
        "https://www.amazon.com/stores/VenturePal/page/E2ECD27B-B348-4358-8B7E-FE05F9A549F6"
    )
    MAIN_UUID      = "E2ECD27B-B348-4358-8B7E-FE05F9A549F6"
    OUT_FILENAME   = "venture_pal_amazon.csv"
    DEFAULT_FORMAT = "instant"

    # Only keep functional coffee / mushroom / adaptogen / supplement products
    ACCEPT_KW = [
        "coffee", "mushroom", "adaptogen", "nootropic", "lion's mane", "lion mane",
        "reishi", "chaga", "cordyceps", "ashwagandha", "rhodiola", "collagen",
        "powder", "instant", "supplement", "creamer", "latte", "matcha",
    ]

    # Extend the base merch skip list with VenturePal's non-coffee product lines
    SKIP_KW = AmazonScraperBase.SKIP_KW + [
        "water bottle", "tumbler", "flask", "backpack", "bag", "pouch",
        "hydration", "electrolyte", "protein bar", "snack", "kettle",
        "blender", "shaker bottle", "journal", "notebook", "towel",
        "resistance band", "yoga", "foam roller", "massage",
    ]

    EXTRA_FORMAT_KW = {
        "capsule": ["capsule", "pill", "softgel", "supplement"],
        "packet":  ["packet", "sachet", "single serve", "stick pack"],
        "instant": ["powder", "instant", "mushroom coffee", "blend"],
        "creamer": ["creamer", "creme"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["mushroom blend", "multi mushroom", "mushroom complex",
                           "10 mushroom", "7 mushroom", "6 mushroom", "5 mushroom"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "chaga":          ["chaga"],
        "reishi":         ["reishi"],
        "cordyceps":      ["cordyceps"],
        "adaptogen":      ["ashwagandha", "rhodiola", "adaptogen"],
        "collagen":       ["collagen"],
        "mct":            ["mct"],
    }

    # Override: crawl clickable catalog sub-pages before returning ASINs
    def get_asins_from_storefront(self, html: str) -> list[str]:
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)

        sub_uuids = re.findall(
            r"/stores/(?:[^/\"]+/)?page/"
            r"([A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12})",
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

    # Override: apply ACCEPT_KW allowlist on top of base merch check
    def is_merch(self, title: str) -> bool:
        if super().is_merch(title):
            return True
        low = title.lower()
        return not any(k in low for k in self.ACCEPT_KW)


if __name__ == "__main__":
    VenturePalScraper().run(pilot="--pilot" in sys.argv)
