#!/usr/bin/env python3
"""
clevr_scraper.py — Clevr Blends own-site scraper (clevrblends.com).
Strategy: Playwright + custom subscription widget (.c-product-form__selling-plan).
All products are instant SuperLatte powder. 8-serving minis have no subscription.
Output: data/raw/clevr_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright_base import PlaywrightScraperBase

from playwright.sync_api import TimeoutError as PlaywrightTimeout


class ClevrScraper(PlaywrightScraperBase):
    BRAND          = "Clevr"
    BASE           = "https://clevrblends.com"
    COLLECTION     = "all"
    OUT_FILENAME   = "clevr_individual.csv"
    DEFAULT_FORMAT = "instant"

    SKIP_HANDLE_RE = re.compile(
        r"^[a-z0-9]{8,12}$|2-pack|3-pack|bundle|kit-3|quarterly|upgrade-to"
        r"|-page$|superlattes-with-benefits|the-starter-kit|the-clevr-collection"
        r"|the-ultimate-kit|latte-lovers-kit|limited-edition-matcha-set"
        r"|supertea-hydration-bundle|chai-lovers|gold-scoop-kit|golden-scoop-kit"
        r"|10-voucher"
    )
    EXTRA_SKIP_KW = [
        "tote", "bandana", "hoodie", "frother", "thermos", "shaker",
        "scoop", "gift card", "mug", "measuring", "magnesium",
    ]

    # ── Clevr-specific helpers ─────────────────────────────────────────────

    def _read_clevr_prices(self, page) -> dict:
        result = {}
        sp = page.query_selector(".c-product-form__selling-plan") or \
             page.query_selector("[class*='selling-plan']")
        if sp:
            text   = sp.inner_text().strip()
            prices = re.findall(r"\$(\d+\.?\d*)", text)
            disc   = re.search(r"SAVE\s+(\d+)%", text, re.IGNORECASE)
            if len(prices) >= 2:
                single_p, sub_p = float(prices[0]), float(prices[1])
                pct = float(disc.group(1)) if disc else round((single_p - sub_p) / single_p * 100, 1)
                result["single"] = single_p
                result["subscription"] = (sub_p, pct)
            elif prices:
                result["single"] = float(prices[0])
            return result

        for sel in ["[class*='price--regular']", ".price", "[class*='price']"]:
            el = page.query_selector(sel)
            if el:
                m = re.search(r"\$(\d+\.?\d*)", el.inner_text())
                if m:
                    result["single"] = float(m.group(1))
                    return result
        return result

    def _get_serving_count(self, body_text: str, handle: str) -> int | None:
        m = re.search(r"(\d+)\s*servings?", body_text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val
        m = re.search(r"-(\d+)-serv", handle)
        if m:
            return int(m.group(1))
        return None

    def scrape_product(self, page, handle: str, rows: list[dict]) -> None:
        url = f"{self.BASE}/products/{handle}"
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
        except PlaywrightTimeout:
            self.log.error("timeout | %s", url)
            return

        name_el = page.query_selector("h1")
        if not name_el:
            return
        product_name = name_el.inner_text().strip().replace("\n", " ")
        if product_name == "404" or len(product_name) < 3:
            return

        if self.is_skip(product_name):
            print(f"    SKIP: {product_name}")
            return

        desc_el = page.query_selector("[class*='description']")
        desc    = desc_el.inner_text() if desc_el else ""
        ingredient    = self.infer_ingredient(product_name, desc)
        body_text     = page.query_selector("body").inner_text()
        serving_count = self._get_serving_count(body_text, handle)

        prices = self._read_clevr_prices(page)
        if not prices:
            print(f"    SKIP (no price): {product_name}")
            return

        if "single" in prices:
            price = prices["single"]
            sp = round(price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=product_name, fmt="instant", ingredient=ingredient,
                serving_size_g=None, serving_count=serving_count, volume_g=None,
                price=price, discount_pct=0, serving_price=sp,
                url=url, purchase_type="single",
            ))
        if "subscription" in prices:
            price, discount = prices["subscription"]
            sp = round(price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=product_name, fmt="instant", ingredient=ingredient,
                serving_size_g=None, serving_count=serving_count, volume_g=None,
                price=price, discount_pct=discount, serving_price=sp,
                url=url, purchase_type="subscription",
            ))


if __name__ == "__main__":
    ClevrScraper().run()
