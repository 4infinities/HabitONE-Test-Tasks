#!/usr/bin/env python3
"""
amazon_scraper_template.py
Base class for all HabitONE Amazon brand scrapers.

Subclasses set class-level config attributes; all scraping logic lives here.
Usage in each brand scraper:
    class MyBrandScraper(AmazonScraperBase):
        BRAND          = "My Brand"
        SEED_ASIN      = "B0XXXXXXXX"
        STOREFRONT_URL = "https://www.amazon.com/stores/page/..."
        OUT_FILENAME   = "mybrand_amazon.csv"
        DEFAULT_FORMAT = "instant"

    if __name__ == "__main__":
        import sys
        MyBrandScraper().run(pilot="--pilot" in sys.argv)
"""

import csv
import re
import time
import random
import logging
import warnings
from datetime import date
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

_BASE_FORMAT_KW = {
    "pods":    ["k-cup", "k cup", "kcup", "keurig"],
    "packet":  ["packet", "sachet", "single-serve", "stick pack", "variety pack", "sampler"],
    "capsule": ["capsule", "pill", "softgel", "tablet"],
    "creamer": ["creamer", "creme"],
    "ground":  ["ground coffee", "ground beans", "whole bean", "brew", "french press"],
    "instant": ["instant", "powder", "powdered"],
}

_BASE_INGREDIENT_KW = {
    "lion's mane":    ["lion's mane", "lion mane"],
    "reishi":         ["reishi"],
    "chaga":          ["chaga"],
    "cordyceps":      ["cordyceps"],
    "mushroom blend": ["mushroom"],
    "adaptogen":      ["adaptogen", "ashwagandha", "rhodiola", "tulsi"],
    "collagen":       ["collagen"],
    "mct":            ["mct"],
}

_BASE_SKIP_KW = ["apparel", "t-shirt", "mug", "gift card", "frother", "kettle", "shaker"]


class AmazonScraperBase:
    # ── Override in each brand subclass ───────────────────────────────────
    BRAND          : str  = ""
    SEED_ASIN      : str  = ""
    STOREFRONT_URL : str  = ""
    OUT_FILENAME   : str  = ""    # e.g. "strong_coffee_amazon.csv"
    DEFAULT_FORMAT : str  = "instant"

    EXTRA_FORMAT_KW        : dict = {}   # merged on top of _BASE_FORMAT_KW
    EXTRA_INGREDIENT_KW    : dict = {}   # merged on top of _BASE_INGREDIENT_KW
    SKIP_KW                : list = _BASE_SKIP_KW
    EXTRA_STOREFRONT_URLS  : list = []   # additional store/search pages scraped before product loop
    AUTO_DISCOVER_SUBPAGES : bool = True # set False if subclass handles sub-pages inside get_asins_from_storefront
    # ──────────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self.today    = date.today().isoformat()
        self.out_file = RAW_DIR / self.OUT_FILENAME

        self.log = logging.getLogger(self.BRAND or __name__)
        if not self.log.handlers:
            h = logging.FileHandler(RAW_DIR / "scrape_errors.log")
            h.setFormatter(logging.Formatter(f"%(asctime)s | {self.BRAND} | %(message)s"))
            self.log.addHandler(h)
            self.log.setLevel(logging.ERROR)

        self._base_headers = {
            "accept-language": "en-US,en;q=0.9",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "upgrade-insecure-requests": "1",
        }

        # pods must stay at front so k-cup titles don't fall through to "instant"
        self._format_kw = {**_BASE_FORMAT_KW}
        for k, v in self.EXTRA_FORMAT_KW.items():
            self._format_kw.setdefault(k, [])
            self._format_kw[k] = list(dict.fromkeys(self._format_kw[k] + v))

        self._ingredient_kw = {**_BASE_INGREDIENT_KW, **self.EXTRA_INGREDIENT_KW}

    # ── Utilities ──────────────────────────────────────────────────────────

    def safe_print(self, s: str) -> None:
        print(s.encode("cp1251", errors="replace").decode("cp1251"))

    def infer_format(self, text: str) -> str:
        low = text.lower()
        for fmt, kws in self._format_kw.items():
            if any(k in low for k in kws):
                return fmt
        return self.DEFAULT_FORMAT

    def infer_ingredient(self, text: str) -> str:
        low = text.lower()
        for ing, kws in self._ingredient_kw.items():
            if any(k in low for k in kws):
                return ing
        return ""

    def is_merch(self, title: str) -> bool:
        return any(k in title.lower() for k in self.SKIP_KW)

    # ── Fetch ──────────────────────────────────────────────────────────────

    def _make_session(self) -> "cffi_requests.Session":
        s = cffi_requests.Session(impersonate="chrome124")
        s.headers.update(self._base_headers)
        s.cookies.set("i18n-prefs", "USD", domain=".amazon.com")
        return s

    def fetch_html(self, url: str, retries: int = 2) -> Optional[str]:
        # Fresh session per request — Amazon poisons the session after the first
        # product page by setting session-token, which causes subsequent pages to
        # return a 330KB login-wall instead of the full product page.
        for attempt in range(1, retries + 1):
            try:
                session = self._make_session()
                resp = session.get(url, timeout=30)
                if resp.status_code == 200 and len(resp.text) > 10000:
                    return resp.text
                self.log.error(f"Unexpected response {resp.status_code} (len={len(resp.text)}) for {url}")
            except Exception as e:
                self.log.error(f"Fetch attempt {attempt} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(5)
        return None

    # ── ASIN discovery ─────────────────────────────────────────────────────

    def get_asins_from_storefront(self, html: str) -> list[str]:
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)
        return list(dict.fromkeys(asins))

    def _discover_store_subpages(self, html: str) -> list[str]:
        """Return internal Amazon store category page URLs found in storefront HTML."""
        found = []
        for path in re.findall(
            r'href=["\']([^"\']*?/stores(?:/[^"\']+)?/page/[A-F0-9-]{36}[^"\']*)["\']',
            html, re.IGNORECASE,
        ):
            url = path if path.startswith("http") else "https://www.amazon.com" + path
            base_url = url.split("?")[0]  # strip query params that filter by lp_asin
            if base_url not in found:
                found.append(base_url)
        return found

    def get_asins_from_twister(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        asins = []
        for li in soup.select("[id*='twister'] li[data-asin]"):
            asin = li.get("data-asin", "").strip()
            if re.fullmatch(r"[A-Z0-9]{10}", asin):
                asins.append(asin)
        return list(dict.fromkeys(asins))

    # ── Parsing ────────────────────────────────────────────────────────────

    def parse_product_page(self, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        # Basis (strikethrough) price → single_discount
        basis_price  = None
        basis_el = soup.select_one(".basisPrice .a-offscreen")
        if basis_el:
            m = re.match(r"\$(\d+\.\d+)", basis_el.get_text(strip=True))
            if m:
                basis_price = float(m.group(1))

        single_price = None
        # Try scoped buybox first (avoids picking up prices from related-product widgets)
        _PRICE_SKIP_CLS = {"basisPrice", "apex-basisprice-value", "apex-basis-price-value"}
        _BUYBOX_SCOPES = ["#apex_offerDisplay_desktop", "#corePriceDisplay_desktop_feature_div", "#buybox"]
        for scope_sel in _BUYBOX_SCOPES:
            scope_el = soup.select_one(scope_sel)
            if not scope_el:
                continue
            for el in scope_el.select(".a-offscreen"):
                m = re.match(r"\$(\d+\.\d+)", el.get_text(strip=True))
                if m:
                    single_price = float(m.group(1))
                    break
            if single_price:
                break
        # Fallback: global search (original behavior)
        if not single_price:
            for el in soup.select(".a-price .a-offscreen"):
                parent = el.find_parent(class_="a-price")
                if parent:
                    cls = set(parent.get("class", []))
                    if cls & _PRICE_SKIP_CLS:
                        continue
                m = re.match(r"\$(\d+\.\d+)", el.get_text(strip=True))
                if m:
                    single_price = float(m.group(1))
                    break

        single_discount = 0.0
        if basis_price and single_price and basis_price > single_price:
            single_discount = round((basis_price - single_price) / basis_price * 100)

        sub_price = None
        for sel in ['#snsAccordionRowMiddle .a-offscreen', '[id*="sns"] .a-offscreen', '.snsPriceLabelValue']:
            for el in soup.select(sel):
                m = re.match(r"\$(\d+\.\d+)", el.get_text(strip=True))
                if m:
                    sub_price = float(m.group(1))
                    break
            if sub_price:
                break

        discounts = []
        for el in soup.select(".savingsPercentage"):
            m = re.search(r"(\d+)", el.get_text(strip=True))
            if m:
                discounts.append(float(m.group(1)))
        sub_discount = discounts[0] if discounts else 0.0

        # Serving count: title → bullets/details → full HTML
        _SC_PATTERNS = [
            r"(\d+)\s*[Ss]erving",
            r"(\d+)\s*[Ll]att(?:e|es)?\b",  # "14 Lattes", "30 Lattes" (Clevr etc.)
            r"(\d+)\s*[Cc]ount",
            r"(\d+)\s*[Ss]achet",
            r"(\d+)\s*[Pp]acket",
            r"(\d+)\s*[Ss]tick\b",
            r"(\d+)\s*[Pp]od\b",
            r"(\d+)\s*ct\b",   # K-cup boxes say "10ct" not "10 Count"
        ]
        serving_count = None
        for pattern in _SC_PATTERNS:
            m = re.search(pattern, title)
            if m:
                serving_count = int(m.group(1))
                break

        if serving_count is None:
            search_els = (
                soup.select("#feature-bullets li")
                + soup.select("#detailBullets_feature_div li")
                + soup.select("#productDetails_techSpec_section_1 tr")
            )
            bullets = " ".join(el.get_text(" ", strip=True) for el in search_els)
            for pattern in _SC_PATTERNS:
                m = re.search(pattern, bullets)
                if m:
                    serving_count = int(m.group(1))
                    break

        if serving_count is None:
            for pattern in _SC_PATTERNS:
                m = re.search(pattern, html)
                if m:
                    serving_count = int(m.group(1))
                    break

        # Volume (oz → g)
        volume_g = None
        meas_el = soup.select_one("#measurements")
        if meas_el:
            m = re.search(r"([\d.]+)\s*[Oo]unce", meas_el.get_text())
            if m:
                volume_g = round(float(m.group(1)) * 28.3495, 1)
        if volume_g is None:
            m = re.search(
                r"(?:Unit Count|Item Weight|Net Weight)[^\d]*([\d.]+)\s*[Oo]unce", html
            )
            if m:
                volume_g = round(float(m.group(1)) * 28.3495, 1)

        return {
            "title":               title,
            "single_price":        single_price,
            "single_discount":     single_discount,
            "sub_price":           sub_price,
            "sub_discount":        sub_discount,
            "serving_count":       serving_count,
            "volume_g":            volume_g,
            "key_ingredient":      self.infer_ingredient(title),
            "subscribe_available": sub_price is not None,
        }

    def build_row(self, detail: dict, url: str, purchase_type: str) -> dict:
        price = detail["sub_price"] if purchase_type == "subscription" else detail["single_price"]
        disc  = detail["sub_discount"] if purchase_type == "subscription" else detail["single_discount"]
        sc    = detail["serving_count"]
        sp    = round(price / sc, 4) if price and sc else None

        return {
            "brand":          self.BRAND,
            "product_name":   detail["title"],
            "format":         self.infer_format(detail["title"]),
            "serving_size_g": None,
            "serving_count":  sc,
            "volume_g":       detail["volume_g"],
            "price_usd":      price,
            "discount_pct":   disc,
            "serving_price":  sp,
            "key_ingredient": detail["key_ingredient"],
            "channel":        "amazon",
            "url":            url,
            "date_collected": self.today,
            "purchase_type":  purchase_type,
        }

    def print_row(self, row: dict) -> None:
        for field in CSV_FIELDS:
            self.safe_print(f"  {field:<16}: {row[field]}")
        print()

    # ── Main entry point ───────────────────────────────────────────────────

    def run(self, pilot: bool = False) -> None:
        rows = []

        if pilot:
            self.safe_print(f"=== PILOT MODE: seed ASIN {self.SEED_ASIN} only, no file written ===\n")
            queue = [self.SEED_ASIN]
        else:
            self.safe_print(f"Step 1: Fetching {self.BRAND} storefront...")
            queue: list[str] = []
            seen_sf: set[str] = set()

            all_sf_urls = [self.STOREFRONT_URL] + list(self.EXTRA_STOREFRONT_URLS)
            for sf_url in all_sf_urls:
                if sf_url in seen_sf:
                    continue
                seen_sf.add(sf_url)

                sf_html = self.fetch_html(sf_url)
                if not sf_html:
                    self.safe_print(f"  Fetch failed: {sf_url[:80]}")
                    continue

                new_asins = [a for a in self.get_asins_from_storefront(sf_html) if a not in queue]
                queue.extend(new_asins)
                self.safe_print(f"  {sf_url[:80]} → +{len(new_asins)} ASINs")

                # Follow internal store category links (skip if subclass handles sub-pages itself)
                if not self.AUTO_DISCOVER_SUBPAGES:
                    continue
                for sp_url in self._discover_store_subpages(sf_html):
                    sp_base = sp_url.split("?")[0]
                    if sp_base in seen_sf:
                        continue
                    seen_sf.add(sp_base)
                    time.sleep(random.uniform(2, 4))
                    sp_html = self.fetch_html(sp_url)
                    if sp_html:
                        sp_asins = [a for a in self.get_asins_from_storefront(sp_html) if a not in queue]
                        queue.extend(sp_asins)
                        self.safe_print(f"    sub-page ...{sp_url[-50:]} → +{len(sp_asins)} ASINs")

                if sf_url != all_sf_urls[-1]:
                    time.sleep(random.uniform(2, 4))

            if not queue:
                self.safe_print("  All storefront fetches failed — using seed ASIN only.")
                queue = [self.SEED_ASIN]
            if self.SEED_ASIN not in queue:
                queue.insert(0, self.SEED_ASIN)
            self.safe_print(f"  Total queue: {len(queue)} ASINs")

        seen = set()
        self.safe_print(f"\n{'Pilot' if pilot else 'Step 2'}: Scraping product pages...")
        i = 0
        while i < len(queue):
            asin = queue[i]
            i += 1
            if asin in seen:
                continue
            seen.add(asin)

            url = f"https://www.amazon.com/dp/{asin}"
            self.safe_print(f"  [{i}/{len(queue)}] {url}")

            html = self.fetch_html(url)
            if not html:
                self.safe_print("    Failed to fetch — skipping.")
                self.log.error(f"Failed to fetch {url}")
                continue

            if not pilot:
                for v_asin in self.get_asins_from_twister(html):
                    if v_asin not in seen and v_asin not in queue:
                        queue.append(v_asin)
                        self.safe_print(f"    + queued variant {v_asin}")

            detail = self.parse_product_page(html)
            if not detail or detail["single_price"] is None:
                self.safe_print("    No price found — skipping.")
                continue

            if self.is_merch(detail["title"]):
                self.safe_print(f"    Merch/skip: {detail['title'][:70]}")
                continue

            single_row = self.build_row(detail, url, "single")
            rows.append(single_row)
            if pilot:
                self.safe_print("  --- single ---")
                self.print_row(single_row)

            if detail["subscribe_available"]:
                sub_row = self.build_row(detail, url, "subscription")
                rows.append(sub_row)
                if pilot:
                    self.safe_print("  --- subscription ---")
                    self.print_row(sub_row)

            if not pilot and i < len(queue):
                time.sleep(random.uniform(4, 7))

        if pilot:
            self.safe_print(f"Pilot complete. {len(rows)} row(s). Verify above, then run without --pilot.")
            return

        self.safe_print(f"\nStep 3: Writing {len(rows)} rows to {self.out_file}")
        with open(self.out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.safe_print(f"Done. Output: {self.out_file}")
