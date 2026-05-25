#!/usr/bin/env python3
"""
everyday_dose_scraper.py — Scraper for Everyday Dose medium-roast-coffee collection.

Catalog: https://everydaydose.com/collections/medium-roast-coffee
Output:  data/raw/everyday_dose_individual.csv (overwrites)

Strategy: inherits ShopifyScraperBase (requests + Shopify JSON API).
  - HTML pages blocked by Cloudflare; JSON API works fine
  - Subscription: 11% discount (confirmed from reference product, 2026-05-23)
  - serving_size_g: 7.3g (from user reference: 219g / 30 servings)
  - Deduplication: some products appear multiple times in collection HTML
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests
from shopify_scraper_template import ShopifyScraperBase

SERVING_SIZE_G  = 7.3   # confirmed: 219g / 30 servings
SUB_DISCOUNT_PCT = 11.0  # confirmed from reference product, 2026-05-23

SKIP_HANDLE_RE = re.compile(
    r"^[a-z0-9]{8,12}$"   # random alphanumeric redirect handles
    r"|dose-rewards"
    r"|no-ship"
    r"|-test$"
    r"|bfcm"
)

SKIP_TITLE_KEYWORDS = [
    "frother", "shaker", "tote", "mug", "vessel", "glass", "tumbler",
    "sticker", "planner", "poster", "magnet", "plushy", "spoon",
    "gift card", "hoodie", "sweats", "sun catcher",
]

INGREDIENT_KEYWORDS = [
    "lion's mane", "lions mane", "chaga", "reishi", "cordyceps", "turkey tail",
    "ashwagandha", "rhodiola", "l-theanine", "theanine", "tongkat ali", "collagen",
]


class EverydayDoseScraper(ShopifyScraperBase):
    BRAND            = "Everyday Dose"
    BASE             = "https://everydaydose.com"
    COLLECTION       = "medium-roast-coffee"
    OUT_FILENAME     = "everyday_dose_individual.csv"
    DEFAULT_FORMAT   = "instant"
    SUB_DISCOUNT_PCT = SUB_DISCOUNT_PCT
    SKIP_HANDLE_RE   = SKIP_HANDLE_RE
    EXTRA_SKIP_KW    = SKIP_TITLE_KEYWORDS
    EXTRA_INGREDIENT_KW = INGREDIENT_KEYWORDS
    DEDUPLICATE      = True

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        title    = product.get("title", "")
        body_raw = product.get("body_html") or ""
        body     = re.sub(r"<[^>]+>", " ", body_raw)

        if self.is_skip(title):
            print(f"    SKIP (merch): {title}")
            return []

        variants = product.get("variants", [])
        if not variants:
            return []

        single_price = float(variants[0].get("price", 0) or 0)
        if single_price <= 0:
            print(f"    SKIP (zero price): {title}")
            return []

        fmt           = self.infer_format(title)
        ingredient    = self.infer_ingredient(title, body)
        serving_count = self.extract_serving_count(title, body)
        product_url   = f"{self.BASE}/products/{handle}"

        if serving_count:
            serving_size_g = SERVING_SIZE_G
            volume_g       = round(serving_count * SERVING_SIZE_G, 1)
        else:
            serving_size_g = None
            volume_g       = None

        sp_single = round(single_price / serving_count, 2) if serving_count else None
        rows = [self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=single_price, discount_pct=0,
            serving_price=sp_single, url=product_url, purchase_type="single",
        )]

        sub_price = round(single_price * (1 - SUB_DISCOUNT_PCT / 100), 2)
        sp_sub    = round(sub_price / serving_count, 2) if serving_count else None
        rows.append(self._make_row(
            title=title, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=sub_price, discount_pct=SUB_DISCOUNT_PCT,
            serving_price=sp_sub, url=product_url, purchase_type="subscription",
        ))

        return rows

    def infer_format(self, title: str) -> str:
        t_low = title.lower()
        if any(kw in t_low for kw in ["starter kit", "free kit", "bundle", "free starter"]):
            return "bundle"
        if re.search(r"\d+\s*servings?\s*(?:of\s*)?(?:coffee|matcha)", title, re.IGNORECASE):
            return "instant"
        return super().infer_format(title)


if __name__ == "__main__":
    EverydayDoseScraper().run()
