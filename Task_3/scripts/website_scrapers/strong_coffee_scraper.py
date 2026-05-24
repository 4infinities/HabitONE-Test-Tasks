#!/usr/bin/env python3
"""
strong_coffee_scraper.py — Scraper for strongcoffeecompany.com.

Catalog: https://strongcoffeecompany.com/collections/all
Output:  data/raw/strong_coffee_individual.csv (overwrites)

Strategy: inherits ShopifyScraperBase (requests + Shopify JSON API).
  - Subscription: auto-detected per product via /products/{handle}.js
  - Volume variants (e.g. "30 Servings", "60 Servings") → separate rows
  - Multi-bag variants (e.g. "3 Bags $34/Bag") → separate rows, total price/volume
  - SERVING_SIZE_LATTE = 30.0g (confirmed: 15 servings × 30g = 450g on PB Coco)
  - serving_size_g NULL for non-latte instant (often not labeled)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from shopify_scraper_template import ShopifyScraperBase

SERVING_SIZE_LATTE = 30.0  # confirmed from reference product
BAG_SERVINGS       = 15    # servings per single bag for multi-bag variants


class StrongCoffeeScraper(ShopifyScraperBase):
    BRAND        = "Strong Coffee Co."
    BASE         = "https://strongcoffeecompany.com"
    COLLECTION   = "all"
    OUT_FILENAME = "strong_coffee_individual.csv"
    DEFAULT_FORMAT = "instant"

    SKIP_HANDLE_RE = re.compile(
        r"^labl-"
        r"|^new-customer-box$"
        r"|bundle"                  # matches anywhere per memory bug note
        r"|starter-kit"
        r"|gift-card"
        r"|sample-pack"
        r"|^rawdawg-"               # plain beans, no adaptogens
        r"|^matcha-"
        r"|^gummy-"
        r"|^booster-|^coffee-booster$"
        r"|norcal-classic"
        r"|-shipment-2$"
        r"|^vanilla-hazelnut-latte-starter"
        r"|^strong-legacy-bundle"
        r"|-shirt$|-shirt-|-tee$|-tee-|^logo-sticker"
        r"|crew-neck|crop-top|-hoodie|-shorts|-hat$"
        r"|-competition-t$|rodeo-club|desert-city|caffeine-cow"
        r"|^heart-of-a-lion|^the-sands-of-time|sand-desert|^miir-"
        r"|^strong-social-club|^the-official-desert|^womens-crop"
    )

    EXTRA_SKIP_KW = ["matcha", "gummy drops", "caffeine cowboy", "rodeo club"]

    EXTRA_FORMAT_KW = {
        "packet": ["travel pack", "travel box"],
    }

    # ──────────────────────────────────────────────────────────────────────

    def _parse_variant_title(self, v_title: str) -> tuple[int | None, int]:
        """Returns (serving_count, bag_count)."""
        m = re.search(r"(\d+)\s*servings?", v_title, re.IGNORECASE)
        if m:
            return int(m.group(1)), 1
        m = re.search(r"(\d+)\s*bags?", v_title, re.IGNORECASE)
        if m:
            bags = int(m.group(1))
            return bags * BAG_SERVINGS, bags
        return None, 1

    def _extract_serving_size_body(self, body: str) -> float | None:
        m = re.search(r"serving size[:\s]+(\d+\.?\d*)\s*g", body, re.IGNORECASE)
        return float(m.group(1)) if m else None

    def build_rows(self, handle: str, product: dict,
                   session: requests.Session) -> list[dict]:
        title    = product.get("title", "")
        body_raw = product.get("body_html") or ""
        body     = re.sub(r"<[^>]+>", " ", body_raw)

        if self.is_skip(title):
            print(f"    SKIP: {title}")
            return []

        variants = product.get("variants", [])
        if not variants:
            return []

        fmt        = self.infer_format(title)
        ingredient = self.infer_ingredient(title, body)
        product_url = f"{self.BASE}/products/{handle}"

        is_latte = any(kw in title.lower() for kw in ["latte", "collagen latte"])
        serving_size_g = SERVING_SIZE_LATTE if is_latte else self._extract_serving_size_body(body)

        # Fetch sub % once per handle — same plan applies to all variants
        # Pass None as single_price: get_sub_pct via product.js doesn't need it
        sub_pct = self.get_sub_pct(session, handle)

        rows = []
        for v in variants:
            price = float(v.get("price", 0) or 0)
            if price <= 0:
                continue

            v_title = v.get("title", "Default Title")
            serving_count, _ = self._parse_variant_title(v_title)
            if serving_count is None:
                serving_count = self.extract_serving_count(title, body)

            volume_g = round(serving_count * serving_size_g, 1) if (serving_count and serving_size_g) else None
            sp       = round(price / serving_count, 2) if serving_count else None

            rows.append(self._make_row(
                title=title, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=price, discount_pct=0,
                serving_price=sp, url=product_url, purchase_type="single",
            ))

            if sub_pct is not None:
                sub_price = round(price * (1 - sub_pct / 100), 2)
                sub_sp    = round(sub_price / serving_count, 2) if serving_count else None
                rows.append(self._make_row(
                    title=title, fmt=fmt, ingredient=ingredient,
                    serving_size_g=serving_size_g, serving_count=serving_count,
                    volume_g=volume_g, price=sub_price, discount_pct=sub_pct,
                    serving_price=sub_sp, url=product_url, purchase_type="subscription",
                ))

        return rows


if __name__ == "__main__":
    StrongCoffeeScraper().run()
