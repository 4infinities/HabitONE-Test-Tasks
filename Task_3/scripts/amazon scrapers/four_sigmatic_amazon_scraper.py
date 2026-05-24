#!/usr/bin/env python3
"""
four_sigmatic_amazon_scraper.py
Scrapes all Four Sigmatic products from their Amazon storefront.
Output: data/raw/four_sigmatic_amazon.csv
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

ROOT     = Path(__file__).parent.parent
RAW_DIR  = ROOT / "data" / "raw"
OUT_FILE = RAW_DIR / "four_sigmatic_amazon.csv"
TODAY    = date.today().isoformat()
BRAND    = "Four Sigmatic"
SEED_ASIN = "B0756D1D39"

STOREFRONT_URL = (
    "https://www.amazon.com/stores/page/BFD5C04F-8BEE-465A-8B09-51EAD476D2DC"
)

logging.basicConfig(
    filename=RAW_DIR / "scrape_errors.log",
    level=logging.ERROR,
    format="%(asctime)s | four_sigmatic_amazon | %(message)s",
)

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

FORMAT_KW = {
    "packet":  ["packet", "sachet", "single-serve", "stick pack", "variety pack"],
    "capsule": ["capsule", "pill", "softgel", "tablet"],
    "creamer": ["creamer", "creme"],
    "ground":  ["ground coffee", "whole bean", "brew", "french press"],
    "instant": ["instant", "powder", "powdered"],
}

INGREDIENT_KW = {
    "lion's mane":    ["lion's mane", "lion mane"],
    "chaga":          ["chaga"],
    "reishi":         ["reishi"],
    "cordyceps":      ["cordyceps"],
    "mushroom blend": ["mushroom"],
    "adaptogen":      ["adaptogen"],
}

SKIP_KW = ["apparel", "t-shirt", "mug", "gift card", "kettle", "frother", "bundle pack"]


def fetch_html(url: str, retries: int = 2) -> Optional[str]:
    for attempt in range(1, retries + 1):
        try:
            loader = ChromiumLoader(
                [url],
                headless=True,
                load_state="load",
                timeout=60,
            )
            docs = loader.load()
            if docs and docs[0].page_content.strip():
                return docs[0].page_content
        except Exception as e:
            logging.error(f"Fetch attempt {attempt} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(5)
    return None


def infer_format(text: str) -> str:
    low = text.lower()
    for fmt, kws in FORMAT_KW.items():
        if any(k in low for k in kws):
            return fmt
    return "instant"


def infer_ingredient(text: str) -> str:
    low = text.lower()
    for ing, kws in INGREDIENT_KW.items():
        if any(k in low for k in kws):
            return ing
    return ""


def is_merch(title: str) -> bool:
    low = title.lower()
    return any(k in low for k in SKIP_KW)


def get_asins_from_storefront(html: str) -> list[str]:
    asins = re.findall(r"/dp/([A-Z0-9]{10})", html)
    return list(dict.fromkeys(asins))


def parse_product_page(html: str, url: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    all_price_els = [e.get_text(strip=True) for e in soup.select(".a-price .a-offscreen")]
    single_price = None
    for p in all_price_els:
        m = re.match(r"\$(\d+\.\d+)", p)
        if m:
            single_price = float(m.group(1))
            break

    sub_price = None
    for el in soup.select('[id*="sns"] .a-offscreen, .snsPriceLabelValue'):
        p = el.get_text(strip=True)
        m = re.match(r"\$(\d+\.\d+)", p)
        if m:
            sub_price = float(m.group(1))
            break

    discounts = []
    for el in soup.select(".savingsPercentage"):
        m = re.search(r"(\d+)", el.get_text(strip=True))
        if m:
            discounts.append(float(m.group(1)))
    single_discount = 0.0  # single purchase has no discount by default
    sub_discount    = discounts[0] if discounts else 0.0

    sc_m = re.search(r"(\d+)\s*[Ss]erving", title)
    serving_count = int(sc_m.group(1)) if sc_m else None

    volume_g = None
    meas_el = soup.select_one("#measurements")
    if meas_el:
        oz_m = re.search(r"([\d.]+)\s*[Oo]unce", meas_el.get_text())
        if oz_m:
            volume_g = round(float(oz_m.group(1)) * 28.3495, 1)

    if volume_g is None:
        oz_m = re.search(
            r"(?:Unit Count|Item Weight|Net Weight)[^\d]*([\d.]+)\s*[Oo]unce",
            html,
        )
        if oz_m:
            volume_g = round(float(oz_m.group(1)) * 28.3495, 1)

    return {
        "title":               title,
        "single_price":        single_price,
        "sub_price":           sub_price,
        "single_discount":     single_discount,
        "sub_discount":        sub_discount,
        "serving_count":       serving_count,
        "volume_g":            volume_g,
        "key_ingredient":      infer_ingredient(title),
        "subscribe_available": sub_price is not None,
    }


def build_row(detail: dict, url: str, purchase_type: str) -> dict:
    price = detail["sub_price"] if purchase_type == "subscription" else detail["single_price"]
    disc  = detail["sub_discount"] if purchase_type == "subscription" else detail["single_discount"]
    sc    = detail["serving_count"]
    sp    = round(price / sc, 4) if price and sc else None

    return {
        "brand":          BRAND,
        "product_name":   detail["title"],
        "format":         infer_format(detail["title"]),
        "serving_size_g": None,
        "serving_count":  sc,
        "volume_g":       detail["volume_g"],
        "price_usd":      price,
        "discount_pct":   disc,
        "serving_price":  sp,
        "key_ingredient": detail["key_ingredient"],
        "channel":        "amazon",
        "url":            url,
        "date_collected": TODAY,
        "purchase_type":  purchase_type,
    }


def main():
    rows = []

    print("Step 1: Fetching Four Sigmatic storefront...")
    storefront_html = fetch_html(STOREFRONT_URL)
    if storefront_html:
        asins = get_asins_from_storefront(storefront_html)
        print(f"  Found {len(asins)} ASINs: {asins}")
    else:
        print("  Storefront fetch failed — using seed ASIN only.")
        asins = [SEED_ASIN]

    if SEED_ASIN not in asins:
        asins.insert(0, SEED_ASIN)

    print(f"\nStep 2: Scraping {len(asins)} product pages...")
    for i, asin in enumerate(asins, 1):
        url = f"https://www.amazon.com/dp/{asin}"
        print(f"  [{i}/{len(asins)}] {url}")

        html = fetch_html(url)
        if not html:
            print("    Failed to fetch — skipping.")
            logging.error(f"Failed to fetch {url}")
            continue

        detail = parse_product_page(html, url)
        if not detail or detail["single_price"] is None:
            print("    No price found — skipping.")
            continue

        if is_merch(detail["title"]):
            print(f"    Merch/skip: {detail['title'][:60]}")
            continue

        print(f"    '{detail['title'][:70]}'")
        print(f"    single=${detail['single_price']} ({detail['single_discount']}% off)  "
              f"servings={detail['serving_count']}  vol={detail['volume_g']}g")

        rows.append(build_row(detail, url, "single"))

        if detail["subscribe_available"]:
            print(f"    sub=${detail['sub_price']} ({detail['sub_discount']}% off)")
            rows.append(build_row(detail, url, "subscription"))

        if i < len(asins):
            time.sleep(random.uniform(4, 7))

    print(f"\nStep 3: Writing {len(rows)} rows to {OUT_FILE}")
    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Output: {OUT_FILE}")


if __name__ == "__main__":
    main()
