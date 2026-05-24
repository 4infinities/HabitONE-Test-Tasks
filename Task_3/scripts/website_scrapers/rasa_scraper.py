#!/usr/bin/env python3
"""
rasa_scraper.py — Rasa own-site scraper (wearerasa.com).
Strategy: Playwright + Skio subscription widget.
Size variants (radio buttons, e.g. "8 oz - 30 Servings") → separate rows per click.
DEFAULT_FORMAT = "ground" (most Rasa products are brewed herb blends).
Output: data/raw/rasa_individual.csv
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright_base import PlaywrightScraperBase

from playwright.sync_api import TimeoutError as PlaywrightTimeout


class RasaScraper(PlaywrightScraperBase):
    BRAND          = "Rasa"
    BASE           = "https://wearerasa.com"
    COLLECTION     = "all-products"
    OUT_FILENAME   = "rasa_individual.csv"
    DEFAULT_FORMAT = "ground"

    EXTRA_SKIP_KW = [
        "tote", "bag clip", "straw", "hat", "tee", "shirt", "wrap",
        "french press", "gift card", "denim", "spoon", "mug",
        "matcha", "cacao", "hot chocolate", "hydration", "electrolyte",
        "hibiscus", "tonic", "peppermint", "chai", "raspberry",
        "calm", "magnificent mushrooms",
    ]
    EXTRA_FORMAT_KW = {
        "packet": ["taster", "variety pack", "sampler"],
        "creamer": ["add-in"],
    }

    # ── Rasa-specific helpers ──────────────────────────────────────────────

    def _parse_variant_label(self, text: str) -> tuple[float | None, int | None]:
        """Parse '8 oz  - 30 Servings' → (volume_g, serving_count)."""
        serving_count = None
        m = re.search(r"(\d+)\s*servings?", text, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:
                serving_count = val
        volume_g = None
        m = re.search(r"(\d+\.?\d*)\s*(lb|lbs|oz|g)\b", text, re.IGNORECASE)
        if m:
            val, unit = float(m.group(1)), m.group(2).lower()
            if unit in ("oz",):
                volume_g = round(val * 28.3495, 1)
            elif unit in ("lb", "lbs"):
                volume_g = round(val * 453.592, 1)
            else:
                volume_g = val
        return volume_g, serving_count

    def _read_skio(self, page) -> dict:
        result = {}
        for inp in page.query_selector_all("input.skio-group-input"):
            id_ = inp.get_attribute("id") or ""
            label_el = page.query_selector(f'label[for="{id_}"]')
            if not label_el:
                continue
            text = label_el.inner_text().strip()
            kind = "subscription" if "selling-plan" in id_ else "single"
            prices = re.findall(r"\$(\d+\.?\d*)", text)
            if not prices:
                continue
            price = float(prices[0])
            sp = float(prices[1]) if len(prices) >= 2 else None
            if kind == "subscription":
                disc = re.search(r"SAVE\s+(\d+)%", text, re.IGNORECASE)
                result["subscription"] = (price, sp, float(disc.group(1)) if disc else 0.0)
            else:
                result["single"] = (price, sp)
        return result

    def _collect_rows(self, page, product_name, url, fmt, ingredient,
                      rows, volume_g=None, serving_count=None):
        skio = self._read_skio(page)
        if not skio:
            el = page.query_selector(".price-serving, .skio-price, .price")
            if el:
                m = re.search(r"\$(\d+\.?\d*)", el.inner_text())
                if m:
                    price = float(m.group(1))
                    sp = round(price / serving_count, 2) if serving_count else None
                    serving_size_g = round(volume_g / serving_count, 2) if (volume_g and serving_count) else None
                    rows.append(self._make_row(
                        title=product_name, fmt=fmt, ingredient=ingredient,
                        serving_size_g=serving_size_g, serving_count=serving_count,
                        volume_g=volume_g, price=price, discount_pct=0,
                        serving_price=sp, url=url, purchase_type="single",
                    ))
            return

        serving_size_g = round(volume_g / serving_count, 2) if (volume_g and serving_count) else None

        if "single" in skio:
            price, sp = skio["single"]
            if not sp and serving_count:
                sp = round(price / serving_count, 2)
            rows.append(self._make_row(
                title=product_name, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=price, discount_pct=0,
                serving_price=sp, url=url, purchase_type="single",
            ))
        if "subscription" in skio:
            price, sp, discount = skio["subscription"]
            if not sp and serving_count:
                sp = round(price / serving_count, 2)
            rows.append(self._make_row(
                title=product_name, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=price, discount_pct=discount,
                serving_price=sp, url=url, purchase_type="subscription",
            ))

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
        product_name = name_el.inner_text().strip()

        if self.is_skip(product_name):
            print(f"    SKIP: {product_name}")
            return

        desc_el = page.query_selector(
            ".product__description, .product-single__description, [class*='description']"
        )
        desc = desc_el.inner_text() if desc_el else ""
        fmt        = self.infer_format(product_name)
        ingredient = self.infer_ingredient(product_name, desc)

        variant_inputs = page.query_selector_all("input[type=radio][class*=variant__input]")
        if not variant_inputs:
            self._collect_rows(page, product_name, url, fmt, ingredient, rows)
            return

        for inp in variant_inputs:
            val    = inp.get_attribute("value") or ""
            inp_id = inp.get_attribute("id") or ""
            label_el = page.query_selector(f'label[for="{inp_id}"]') if inp_id else None
            if label_el:
                label_el.click()
                page.wait_for_timeout(1000)
            else:
                inp.click()
                page.wait_for_timeout(1000)
            volume_g, serving_count = self._parse_variant_label(val)
            self._collect_rows(page, product_name, page.url, fmt, ingredient,
                               rows, volume_g=volume_g, serving_count=serving_count)


if __name__ == "__main__":
    RasaScraper().run()
