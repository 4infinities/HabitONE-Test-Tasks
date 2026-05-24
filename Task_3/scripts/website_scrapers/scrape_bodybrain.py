#!/usr/bin/env python3
"""
scrape_bodybrain.py — BodyBrain Coffee own-site scraper.
Strategy: JSON API for collection handles (Playwright fallback); Playwright for product pages.
Subscription via Seal Subscriptions widget (.sls-option-container).
Output: data/raw/bodybrain_individual.csv
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright_base import PlaywrightScraperBase

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout

# selectors to try when clicking subscription option
_SUB_CLICK = [
    "input[value='subscription']",
    "input[id*='subscribe']",
    "input[name='selling_plan']",
    "[data-selling-plan-id]",
    "label:has-text('Subscribe & Save')",
    "label:has-text('Subscribe')",
    ".rc-option--subscribe",
    "[class*='subscription-option']",
    "[class*='subscribe-save']",
]


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    t = text.strip().replace("\xa0", " ")
    if re.search(r"\b(PLN|EUR|GBP|CAD|AUD|MXN|BRL|RUB)\b", t, re.IGNORECASE):
        return None
    m = re.search(r"\$\s*(\d[\d,]*\.?\d*)", t)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"(\d[\d,]*)\s*\$", t)
    if m:
        raw = m.group(1).replace(",", ".")
        try:
            val = float(raw)
        except ValueError:
            return None
        if val > 500 and "." not in raw:
            val = round(val / 100, 2)
        return val if val > 0 else None
    return None


class BodyBrainScraper(PlaywrightScraperBase):
    BRAND          = "BodyBrain Coffee"
    BASE           = "https://bodybraincoffee.com"
    COLLECTION     = "frontpage"
    OUT_FILENAME   = "bodybrain_individual.csv"
    DEFAULT_FORMAT = "packet"  # BodyBrain catalog is packet-only

    EXTRA_SKIP_KW  = []

    # ── Collection handles: JSON API first, Playwright fallback ───────────

    def get_handles_playwright(self, page) -> list[str]:
        handles = self._get_handles_json()
        if handles:
            print(f"Found {len(handles)} products via JSON API")
            return handles
        print("JSON API blocked — walking collection with Playwright")
        return self._get_handles_pw(page)

    def _get_handles_json(self) -> list[str]:
        session = requests.Session()
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        handles = []
        page = 1
        while True:
            url = f"{self.BASE}/collections/{self.COLLECTION}/products.json?limit=250&page={page}"
            try:
                r = session.get(url, timeout=15)
                if r.status_code != 200:
                    return []
                products = r.json().get("products", [])
                if not products:
                    break
                handles.extend(p["handle"] for p in products if p.get("handle"))
                if len(products) < 250:
                    break
                page += 1
            except Exception:
                return []
        return handles

    def _get_handles_pw(self, page) -> list[str]:
        col_url = f"{self.BASE}/collections/{self.COLLECTION}"
        seen: set[str] = set()
        urls: list[str] = []
        page_num = 1
        while True:
            nav_url = col_url if page_num == 1 else f"{col_url}?page={page_num}"
            try:
                page.goto(nav_url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            hrefs = page.eval_on_selector_all(
                "a[href*='/products/']",
                "els => [...new Set(els.map(e => e.href.split('?')[0]))]",
            )
            new = [h for h in hrefs if "/products/" in h and h not in seen]
            if not new:
                break
            seen.update(new)
            urls.extend(new)
            if not page.query_selector("a[rel='next'], .pagination__next, a.next"):
                break
            page_num += 1
        # convert full URLs → handles
        return [u.rstrip("/").split("/products/")[-1] for u in urls]

    # ── Product page ───────────────────────────────────────────────────────

    def scrape_product(self, page, handle: str, rows: list[dict]) -> None:
        url = f"{self.BASE}/products/{handle}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector(".sls-option-container.sls-active", timeout=10000)
        except Exception:
            time.sleep(4)

        html = page.content()
        soup = BeautifulSoup(html, "lxml")

        name_el = soup.select_one("h1.product__title, h1.product-single__title, h1[itemprop='name'], h1")
        name = " ".join(name_el.get_text(strip=True).split()) if name_el else ""
        if not name:
            return

        if self.is_skip(name):
            print(f"    SKIP: {name}")
            return

        desc_el = soup.select_one(
            ".product__description, .product-single__description, "
            "[itemprop='description'], .rte, .product-description"
        )
        desc = " ".join(desc_el.get_text(" ", strip=True).split()) if desc_el else ""
        text_all = f"{name} {desc}"

        # ── Seal Subscriptions widget ──────────────────────────────────────
        single_price = sub_price = sub_discount = None
        one_time_el = soup.select_one(".sls-option-container.sls-active")
        sub_el      = soup.select_one(".sls-option-container:not(.sls-active)")

        if one_time_el:
            for money in one_time_el.select("span.money"):
                p = _parse_price(money.get_text(strip=True))
                if p and 0 < p < 2000:
                    single_price = p
                    break
        if sub_el:
            price_el = sub_el.select_one(".sls-selling-plan-group-price, .sls-total-price")
            if price_el:
                p = _parse_price(price_el.get_text(strip=True))
                if p:
                    sub_price = p
            badge = sub_el.select_one(".sls-savings-badge")
            if badge:
                m = re.search(r"(\d+)\s*%", badge.get_text())
                if m:
                    sub_discount = int(m.group(1))

        # ── Fallback: native Shopify price ─────────────────────────────────
        if single_price is None:
            for sel in [".price__regular .price-item--regular", ".price-item--regular",
                        ".price-item", "span.money"]:
                el = soup.select_one(sel)
                if el:
                    p = _parse_price(el.get_text(strip=True))
                    if p and 0 < p < 2000:
                        single_price = p
                        break

        if sub_discount and single_price and sub_price is None:
            sub_price = round(single_price * (1 - sub_discount / 100), 2)
        if sub_price and single_price and sub_discount is None:
            sub_discount = round((1 - sub_price / single_price) * 100)

        # ── Click fallback for non-Seal sites ──────────────────────────────
        if sub_price is None:
            for sel in _SUB_CLICK:
                try:
                    el = page.query_selector(sel)
                    if not el:
                        continue
                    el.click()
                    page.wait_for_timeout(800)
                    sub_soup = BeautifulSoup(page.content(), "lxml")
                    for money_el in sub_soup.select("span.money"):
                        candidate = _parse_price(money_el.get_text(strip=True))
                        if candidate and single_price and candidate < single_price:
                            sub_price = candidate
                            sub_discount = round((1 - sub_price / single_price) * 100)
                            break
                    if sub_price:
                        break
                except Exception:
                    continue

        # ── Serving / volume ───────────────────────────────────────────────
        serving_count = self.extract_serving_count(text_all)
        m = re.search(r"serving size[:\s]+(\d+\.?\d*)\s*g", text_all, re.IGNORECASE)
        serving_size_g = float(m.group(1)) if m else None
        if serving_size_g and serving_count:
            volume_g = round(serving_size_g * serving_count, 1)
        else:
            m = re.search(r"(\d+\.?\d*)\s*oz\b", text_all, re.IGNORECASE)
            volume_g = round(float(m.group(1)) * 28.3495, 1) if m else None

        fmt        = self.infer_format(text_all)
        ingredient = self.infer_ingredient(text_all)

        sp = round(single_price / serving_count, 2) if (single_price and serving_count) else None
        rows.append(self._make_row(
            title=name, fmt=fmt, ingredient=ingredient,
            serving_size_g=serving_size_g, serving_count=serving_count,
            volume_g=volume_g, price=single_price or 0, discount_pct=0,
            serving_price=sp, url=url, purchase_type="single",
        ))
        if sub_price:
            sp_sub = round(sub_price / serving_count, 2) if serving_count else None
            rows.append(self._make_row(
                title=name, fmt=fmt, ingredient=ingredient,
                serving_size_g=serving_size_g, serving_count=serving_count,
                volume_g=volume_g, price=sub_price, discount_pct=sub_discount or 0,
                serving_price=sp_sub, url=url, purchase_type="subscription",
            ))

        sub_info = f"sub={sub_price} ({sub_discount}%)" if sub_price else "no sub"
        print(f"    {name} | single={single_price} | {sub_info}")


if __name__ == "__main__":
    BodyBrainScraper().run()
