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

try:
    from langchain_ollama import ChatOllama as _ChatOllama
    import langchain_community.chat_models as _lcm
    if not hasattr(_lcm, "ChatOllama"):
        _lcm.ChatOllama = _ChatOllama
except ImportError:
    pass

from bs4 import BeautifulSoup
from scrapegraphai.docloaders import ChromiumLoader

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

_BASE_FORMAT_KW = {
    "packet":  ["packet", "sachet", "single-serve", "stick pack", "variety pack", "sampler"],
    "capsule": ["capsule", "pill", "softgel", "tablet"],
    "creamer": ["creamer", "creme"],
    "ground":  ["ground coffee", "whole bean", "brew", "french press"],
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

    EXTRA_FORMAT_KW     : dict = {}   # merged on top of _BASE_FORMAT_KW
    EXTRA_INGREDIENT_KW : dict = {}   # merged on top of _BASE_INGREDIENT_KW
    SKIP_KW             : list = _BASE_SKIP_KW
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

    def fetch_html(self, url: str, retries: int = 2) -> Optional[str]:
        for attempt in range(1, retries + 1):
            try:
                loader = ChromiumLoader([url], headless=True, load_state="load", timeout=60)
                docs = loader.load()
                if docs and docs[0].page_content.strip():
                    return docs[0].page_content
            except Exception as e:
                self.log.error(f"Fetch attempt {attempt} failed for {url}: {e}")
                if attempt < retries:
                    time.sleep(5)
        return None

    # ── ASIN discovery ─────────────────────────────────────────────────────

    def get_asins_from_storefront(self, html: str) -> list[str]:
        asins = re.findall(r"/dp/([A-Z0-9]{10})", html)
        return list(dict.fromkeys(asins))

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
        for el in soup.select(".a-price .a-offscreen"):
            parent = el.find_parent(class_="a-price")
            if parent and "basisPrice" in parent.get("class", []):
                continue
            m = re.match(r"\$(\d+\.\d+)", el.get_text(strip=True))
            if m:
                single_price = float(m.group(1))
                break

        single_discount = 0.0
        if basis_price and single_price and basis_price > single_price:
            single_discount = round((basis_price - single_price) / basis_price * 100)

        sub_price = None
        for el in soup.select('[id*="sns"] .a-offscreen, .snsPriceLabelValue'):
            m = re.match(r"\$(\d+\.\d+)", el.get_text(strip=True))
            if m:
                sub_price = float(m.group(1))
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
            r"(\d+)\s*[Cc]ount",
            r"(\d+)\s*[Ss]achet",
            r"(\d+)\s*[Pp]acket",
            r"(\d+)\s*[Ss]tick\b",
            r"(\d+)\s*[Pp]od\b",
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
            storefront_html = self.fetch_html(self.STOREFRONT_URL)
            if storefront_html:
                queue = self.get_asins_from_storefront(storefront_html)
                self.safe_print(f"  Found {len(queue)} ASINs: {queue}")
            else:
                self.safe_print("  Storefront fetch failed — using seed ASIN only.")
                queue = [self.SEED_ASIN]
            if self.SEED_ASIN not in queue:
                queue.insert(0, self.SEED_ASIN)

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
