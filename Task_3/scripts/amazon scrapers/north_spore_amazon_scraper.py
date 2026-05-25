#!/usr/bin/env python3
"""
north_spore_amazon_scraper.py
Scrapes North Spore functional-coffee products from their Amazon storefront.

North Spore's primary business is mushroom cultivation (grow kits, spawn,
substrate, plugs). Their coffee line (mushroom-infused ground coffee / cocoa)
is a small subset. Filtering is two-layered:
  1. ACCEPT_KW allowlist — drop anything that doesn't mention coffee/cocoa/cacao.
  2. SKIP_KW blocklist — drop grow kits, spawn, and cultivation supplies even
     if a title contains an incidental coffee keyword.

The store entry point is a pre-filtered /search?terms=cocoa URL; the scraper
also crawls the full storefront and all category sub-pages so nothing is missed.
Output: data/raw/north_spore_amazon.csv

Usage:
  python "scripts/amazon scrapers/north_spore_amazon_scraper.py"           # full run
  python "scripts/amazon scrapers/north_spore_amazon_scraper.py" --pilot   # seed ASIN only, no file written
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from amazon_scraper_template import AmazonScraperBase

# Entry point: store search pre-filtered to cocoa products
_SEARCH_URL = (
    "https://www.amazon.com/stores/page/6A3F863D-C950-4476-A647-656570ED3EDB"
    "/search?terms=cocoa"
)
# Full storefront root (no filter) — may expose additional coffee SKUs
_STORE_ROOT = (
    "https://www.amazon.com/stores/page/6A3F863D-C950-4476-A647-656570ED3EDB"
)
# Additional keyword searches inside the store
_EXTRA_SEARCHES = [
    "https://www.amazon.com/stores/page/6A3F863D-C950-4476-A647-656570ED3EDB"
    "/search?terms=coffee",
    "https://www.amazon.com/stores/page/6A3F863D-C950-4476-A647-656570ED3EDB"
    "/search?terms=cacao",
    "https://www.amazon.com/stores/page/6A3F863D-C950-4476-A647-656570ED3EDB"
    "/search?terms=mocha",
]


class NorthSporeScraper(AmazonScraperBase):
    BRAND          = "North Spore"
    SEED_ASIN      = "B0F8C8F5TL"
    STOREFRONT_URL = _SEARCH_URL
    EXTRA_STOREFRONT_URLS = [_STORE_ROOT] + _EXTRA_SEARCHES
    MAIN_UUID      = "6A3F863D-C950-4476-A647-656570ED3EDB"
    OUT_FILENAME   = "north_spore_amazon.csv"
    # North Spore's coffee line is ground coffee per their product descriptions
    DEFAULT_FORMAT = "ground"
    # Sub-pages are crawled inside get_asins_from_storefront; skip auto-discovery
    # to avoid double-crawling the same UUIDs.
    AUTO_DISCOVER_SUBPAGES = False

    # ── Narrow allowlist: only coffee-adjacent products pass ──────────────────
    ACCEPT_KW = [
        "coffee", "cocoa", "cacao", "mocha", "latte",
    ]

    # ── Block list: cultivation / grow-kit / spawn terminology ────────────────
    # Merged on top of the base SKIP_KW list.
    SKIP_KW = AmazonScraperBase.SKIP_KW + [
        # grow kits & supplies
        "grow kit", "growing kit", "mushroom kit", "starter kit", "cultivation kit",
        "spawn", "plug spawn", "grain spawn", "sawdust spawn",
        "substrate", "straw substrate", "hardwood substrate",
        "inoculat", "mycelium", "spore syringe", "liquid culture", "syringe",
        "block", "log", "dowel",
        # fungi that never appear in their coffee line
        "oyster mushroom", "shiitake", "wine cap", "chicken of the woods",
        "maitake", "enoki", "cremini", "portobello",
        # growing accessories
        "humidity tent", "grow bag", "fruiting chamber",
        # general non-food
        "apparel", "t-shirt", "mug", "gift card", "frother", "kettle", "shaker",
        "book", "guide", "journal", "poster",
    ]

    EXTRA_FORMAT_KW = {
        "ground":  ["ground coffee", "ground beans", "whole bean", "brew", "french press",
                    "pour over", "drip"],
        "instant": ["instant", "powder", "powdered", "soluble"],
        "packet":  ["packet", "sachet", "single serve", "stick pack"],
        "creamer": ["creamer", "creme"],
    }

    EXTRA_INGREDIENT_KW = {
        "mushroom blend": ["fruiting body", "mushroom blend", "multi mushroom",
                           "mushroom complex", "10 mushroom", "7 mushroom"],
        "lion's mane":    ["lion's mane", "lion mane"],
        "chaga":          ["chaga"],
        "reishi":         ["reishi"],
        "cordyceps":      ["cordyceps"],
        "turkey tail":    ["turkey tail"],
    }

    # ── Storefront crawl: main page + all category sub-pages ─────────────────

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

    # ── Two-layer filter ──────────────────────────────────────────────────────

    def is_merch(self, title: str) -> bool:
        # Layer 1: base merch check (apparel, gift cards, etc.) + our SKIP_KW blocklist
        if super().is_merch(title):
            return True
        low = title.lower()
        # Layer 2: must contain at least one coffee-adjacent keyword to be kept
        return not any(k in low for k in self.ACCEPT_KW)


if __name__ == "__main__":
    NorthSporeScraper().run(pilot="--pilot" in sys.argv)
