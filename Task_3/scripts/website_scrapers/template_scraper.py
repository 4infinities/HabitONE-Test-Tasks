#!/usr/bin/env python3
"""
template_scraper.py — Copy, rename, fill in CONFIGURE block, pick strategies.

CONFIGURE CHECKLIST (top to bottom):
  1. BRAND, BRAND_KEY, BASE, COLLECTION, OUT_FILE_NAME
  2. SUB_DISCOUNT_PCT — if store has a fixed sub discount (e.g. "always 11%")
  3. SERVING_SIZE_G   — if serving size is known from reference data
  4. SKIP_HANDLE_RE   — add brand-specific patterns
  5. SKIP_MERCH, SKIP_NONCOFFEE — brand-specific keywords
  6. FORMAT_DEFAULT   — "instant" / "ground" / "packet"
  7. Collection strategy: uncomment JSON API or Playwright block in main()
  8. Product strategy:   uncomment JSON API or Playwright scraper in main()
  9. Subscription widget: uncomment ONE handler; delete the others

Output: data/raw/{OUT_FILE_NAME}
"""

import re
import csv
import time
import random
import logging
import requests
from datetime import date
from pathlib import Path

# Uncomment if using Playwright strategy:
# from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
# from bs4 import BeautifulSoup

# ═══ CONFIGURE ════════════════════════════════════════════════════════════════

BRAND        = "Brand Name"              # exact brand name in output CSV
BRAND_KEY    = "brand_key"              # for scrape_errors.log; lowercase, no spaces
BASE         = "https://example.com"
COLLECTION   = "collection-slug"        # from /collections/{slug}
OUT_FILE_NAME = "brand_key_individual.csv"

# Fixed subscription discount — set if confirmed from reference product:
# SUB_DISCOUNT_PCT = 11.0

# Fixed serving size — set if confirmed from reference data (e.g. 219g / 30 = 7.3):
# SERVING_SIZE_G = 7.3

SKIP_HANDLE_RE = re.compile(
    r"^[a-z0-9]{8,12}$"            # random alphanumeric redirect handles
    r"|-test$"                       # internal test SKUs
    # Add brand-specific patterns below:
    # r"|dose-rewards"              # loyalty program
    # r"|gift-card"
    # r"|no-ship"
)

SKIP_MERCH = [
    "frother", "shaker", "tote", "mug", "glass", "tumbler",
    "sticker", "planner", "poster", "magnet", "plushy", "spoon",
    "gift card", "hoodie", "sweats",
    # Add brand-specific merch keywords here
]

SKIP_NONCOFFEE = [
    # Add non-coffee products to skip (electrolytes, matcha, pure supplements, etc.)
    # "matcha", "cacao", "electrolyte", "hydration",
]

FORMAT_DEFAULT = "instant"   # brand-wide fallback: "instant" / "ground" / "packet"

FORMAT_KEYWORDS = {
    "packet":  ["packet", "sachet", "single-serve", "stick pack"],
    "capsule": ["capsule", "pill", "softgel"],
    "creamer": ["creamer", "creme"],
    "ground":  ["ground coffee", "whole bean"],
    "instant": ["instant", "powder"],
}

INGREDIENT_KEYWORDS = [
    "lion's mane", "lions mane", "chaga", "reishi", "cordyceps", "turkey tail",
    "ashwagandha", "rhodiola", "l-theanine", "theanine", "tongkat ali",
    "collagen", "mushroom", "adaptogen",
]

# ═════════════════════════════════════════════════════════════════════════════

ROOT    = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_FILE = RAW_DIR / OUT_FILE_NAME
TODAY   = date.today().isoformat()

logging.basicConfig(
    filename=RAW_DIR / "scrape_errors.log",
    level=logging.ERROR,
    format=f"%(asctime)s | {BRAND_KEY} | %(message)s",
)

CSV_FIELDS = [
    "brand", "product_name", "format", "serving_size_g", "serving_count",
    "volume_g", "price_usd", "discount_pct", "serving_price",
    "key_ingredient", "channel", "url", "date_collected", "purchase_type",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── FILTER HELPERS ───────────────────────────────────────────────────────────

def is_merch(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in SKIP_MERCH)


def is_noncoffee(title: str) -> bool:
    low = title.lower()
    return any(kw in low for kw in SKIP_NONCOFFEE)


# ─── INFERENCE HELPERS ────────────────────────────────────────────────────────

def infer_format(title: str, body: str) -> str:
    # Serving count in title → instant (prevents "+FREE Creamer" bundles changing format)
    if re.search(r"\d+\s*servings?\s*(?:of\s*)?(?:coffee|matcha|latte)", title, re.IGNORECASE):
        return "instant"
    text = (title + " " + body).lower()
    for fmt, kws in FORMAT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            return fmt
    return FORMAT_DEFAULT


def infer_ingredient(title: str, body: str) -> str | None:
    text = (title + " " + body).lower()
    for ing in INGREDIENT_KEYWORDS:
        if ing in text:
            return ing
    return None


def extract_serving_count(title: str, body: str) -> int | None:
    for text in [title, body]:
        for pat in [r"(\d+)\s*servings?", r"(\d+)\s*-\s*serving", r"(\d+)\s*count"]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 500:
                    return val
    return None


def parse_price(text: str) -> float | None:
    """Parse price string; handles $44.99, 44,99 $, non-breaking spaces. Rejects non-USD."""
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


def to_grams(value: float, unit: str) -> float:
    unit = unit.lower().strip()
    if unit in ("oz", "ounce", "ounces"):
        return round(value * 28.3495, 1)
    if unit in ("lb", "lbs", "pound", "pounds"):
        return round(value * 453.592, 1)
    return value


# ─── ROW BUILDER ──────────────────────────────────────────────────────────────

def _row(product_name, fmt, ingredient, url,
         serving_size_g, serving_count, volume_g,
         price, discount_pct, serving_price, purchase_type) -> dict:
    return {
        "brand":          BRAND,
        "product_name":   product_name,
        "format":         fmt,
        "serving_size_g": serving_size_g,
        "serving_count":  serving_count,
        "volume_g":       volume_g,
        "price_usd":      price,
        "discount_pct":   discount_pct,
        "serving_price":  serving_price,
        "key_ingredient": ingredient,
        "channel":        "own_site",
        "url":            url,
        "date_collected": TODAY,
        "purchase_type":  purchase_type,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY A — Shopify JSON API (requests only, no browser)
# Use when: /collections/{COLLECTION}/products.json accessible (Accept: application/json)
# Examples: Everyday Dose (Cloudflare blocks HTML but not JSON endpoints)
# ═══════════════════════════════════════════════════════════════════════════════

def get_handles_json(session: requests.Session) -> list[str]:
    handles = []
    page_num = 1
    while True:
        url = f"{BASE}/collections/{COLLECTION}/products.json?limit=250&page={page_num}"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                break
            products = r.json().get("products", [])
            if not products:
                break
            for p in products:
                h = p.get("handle", "")
                if h and not SKIP_HANDLE_RE.search(h):
                    handles.append(h)
            if len(products) < 250:
                break
            page_num += 1
        except Exception as e:
            logging.error("collection fetch error page=%d: %s", page_num, e)
            break
    return list(dict.fromkeys(handles))


def get_product_json(session: requests.Session, handle: str) -> dict | None:
    url = f"{BASE}/products/{handle}.json"
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            logging.error("product fetch %s → %d", handle, r.status_code)
            return None
        return r.json().get("product", {})
    except Exception as e:
        logging.error("product fetch %s: %s", handle, e)
        return None


def build_rows_json(handle: str, product: dict) -> list[dict]:
    title    = product.get("title", "")
    body_raw = product.get("body_html") or ""
    body     = re.sub(r"<[^>]+>", " ", body_raw)

    if is_merch(title) or is_noncoffee(title):
        print(f"    SKIP: {title}")
        return []

    fmt          = infer_format(title, body)
    ingredient   = infer_ingredient(title, body)
    serving_count = extract_serving_count(title, body)

    variants = product.get("variants", [])
    if not variants:
        return []
    single_price = float(variants[0].get("price", 0) or 0)
    if single_price <= 0:
        return []

    # serving_size_g / volume_g — PICK ONE:
    # Option A: known from reference data (set SERVING_SIZE_G above)
    # serving_size_g = SERVING_SIZE_G if serving_count else None
    # volume_g = round(serving_count * SERVING_SIZE_G, 1) if serving_count else None
    # Option B: leave null (cannot reach product pages to find nutrition label)
    serving_size_g = None
    volume_g = None

    product_url = f"{BASE}/products/{handle}"
    rows = []

    sp_single = round(single_price / serving_count, 2) if serving_count else None
    rows.append(_row(title, fmt, ingredient, product_url,
                     serving_size_g, serving_count, volume_g,
                     single_price, 0, sp_single, "single"))

    # Subscription — PICK ONE:
    # Option A: fixed discount from reference data
    # sub_price = round(single_price * (1 - SUB_DISCOUNT_PCT / 100), 2)
    # sp_sub = round(sub_price / serving_count, 2) if serving_count else None
    # rows.append(_row(title, fmt, ingredient, product_url,
    #                  serving_size_g, serving_count, volume_g,
    #                  sub_price, SUB_DISCOUNT_PCT, sp_sub, "subscription"))
    # Option B: no subscription for this brand → nothing to add

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY B — Playwright (JS-rendered pages)
# Use when: prices rendered by JS / subscription widget requires browser
# Examples: Rasa (Skio), Clevr (custom widget), BodyBrain (Seal Subscriptions)
# ═══════════════════════════════════════════════════════════════════════════════

# def get_handles_playwright(page) -> list[str]:
#     page.goto(f"{BASE}/collections/{COLLECTION}", wait_until="networkidle", timeout=30000)
#     page.wait_for_timeout(2000)
#     html = page.content()
#     handles = re.findall(r"/products/([a-z0-9][a-z0-9\-]+)", html)
#     handles = list(dict.fromkeys(handles))
#     return [h for h in handles if not SKIP_HANDLE_RE.search(h)]
#
#
# def scrape_product_playwright(page, handle: str, rows: list[dict]):
#     url = f"{BASE}/products/{handle}"
#     try:
#         page.goto(url, wait_until="networkidle", timeout=30000)
#         page.wait_for_timeout(1500)
#     except PlaywrightTimeout:
#         logging.error("timeout | %s", url)
#         return
#
#     name_el = page.query_selector("h1")
#     if not name_el:
#         return
#     title = name_el.inner_text().strip().replace("\n", " ")
#     if title == "404" or len(title) < 3:
#         return
#     if is_merch(title) or is_noncoffee(title):
#         print(f"    SKIP: {title}")
#         return
#
#     desc_el = page.query_selector("[class*='description']")
#     desc = desc_el.inner_text() if desc_el else ""
#     body_text = page.query_selector("body").inner_text()
#
#     fmt = infer_format(title, desc)
#     ingredient = infer_ingredient(title, desc)
#     serving_count = extract_serving_count(title, body_text)
#
#     # Call the subscription widget handler (pick one below):
#     prices = read_prices_skio(page)   # or read_prices_seal / read_prices_clevr
#     if not prices:
#         print(f"    SKIP (no price): {title}")
#         return
#
#     product_url = f"{BASE}/products/{handle}"
#
#     # serving_size_g / volume_g from body text (if label present):
#     serving_size_g = None
#     volume_g = None
#     # m = re.search(r"serving size[:\s]+(\d+\.?\d*)\s*g", body_text, re.IGNORECASE)
#     # if m: serving_size_g = float(m.group(1))
#     # if serving_size_g and serving_count: volume_g = round(serving_size_g * serving_count, 1)
#
#     if "single" in prices:
#         price, sp = prices["single"]
#         if not sp and serving_count: sp = round(price / serving_count, 2)
#         rows.append(_row(title, fmt, ingredient, product_url,
#                          serving_size_g, serving_count, volume_g,
#                          price, 0, sp, "single"))
#
#     if "subscription" in prices:
#         price, sp, discount = prices["subscription"]
#         if not sp and serving_count: sp = round(price / serving_count, 2)
#         rows.append(_row(title, fmt, ingredient, product_url,
#                          serving_size_g, serving_count, volume_g,
#                          price, discount, sp, "subscription"))


# ─── SUBSCRIPTION WIDGET HANDLERS ─────────────────────────────────────────────
# Uncomment ONE. Delete the others after choosing.
# Return value convention: dict with keys "single" and/or "subscription"
#   "single":       (price: float, serving_price: float | None)
#   "subscription": (price: float, serving_price: float | None, discount_pct: float)

# ── Widget 1: Skio (Rasa, IQBAR, many Shopify stores) ─────────────────────────
# def read_prices_skio(page) -> dict:
#     result = {}
#     for inp in page.query_selector_all("input.skio-group-input"):
#         id_ = inp.get_attribute("id") or ""
#         label_el = page.query_selector(f'label[for="{id_}"]')
#         if not label_el:
#             continue
#         text = label_el.inner_text().strip()
#         kind = "subscription" if "selling-plan" in id_ else "single"
#         prices = re.findall(r"\$(\d+\.?\d*)", text)
#         if not prices:
#             continue
#         price = float(prices[0])
#         sp = float(prices[1]) if len(prices) >= 2 else None
#         if kind == "subscription":
#             discount = re.search(r"SAVE\s+(\d+)%", text, re.IGNORECASE)
#             result["subscription"] = (price, sp, float(discount.group(1)) if discount else 0.0)
#         else:
#             result["single"] = (price, sp)
#     return result

# ── Widget 2: Seal Subscriptions (BodyBrain) ──────────────────────────────────
# Requires: from bs4 import BeautifulSoup; call after wait_for_selector(".sls-option-container.sls-active")
# def read_prices_seal(page) -> dict:
#     html = page.content()
#     soup = BeautifulSoup(html, "lxml")
#     single_price = sub_price = sub_discount = None
#     one_time_el = soup.select_one(".sls-option-container.sls-active")
#     sub_el = soup.select_one(".sls-option-container:not(.sls-active)")
#     if one_time_el:
#         for money in one_time_el.select("span.money"):
#             p = parse_price(money.get_text(strip=True))
#             if p and 0 < p < 2000:
#                 single_price = p; break
#     if sub_el:
#         price_el = sub_el.select_one(".sls-selling-plan-group-price, .sls-total-price")
#         if price_el:
#             p = parse_price(price_el.get_text(strip=True))
#             if p: sub_price = p
#         badge = sub_el.select_one(".sls-savings-badge")
#         if badge:
#             m = re.search(r"(\d+)\s*%", badge.get_text())
#             if m: sub_discount = int(m.group(1))
#     result = {}
#     if single_price:
#         result["single"] = (single_price, None)
#     if sub_price:
#         result["subscription"] = (sub_price, None, sub_discount or 0)
#     return result

# ── Widget 3: Clevr custom widget ────────────────────────────────────────────
# def read_prices_clevr(page) -> dict:
#     result = {}
#     sp = page.query_selector(".c-product-form__selling-plan") or \
#          page.query_selector("[class*='selling-plan']")
#     if sp:
#         text = sp.inner_text().strip()
#         prices = re.findall(r"\$(\d+\.?\d*)", text)
#         discount = re.search(r"SAVE\s+(\d+)%", text, re.IGNORECASE)
#         if len(prices) >= 2:
#             single_p, sub_p = float(prices[0]), float(prices[1])
#             pct = float(discount.group(1)) if discount else \
#                   round((single_p - sub_p) / single_p * 100, 1)
#             result["single"] = (single_p, None)
#             result["subscription"] = (sub_p, None, pct)
#         elif len(prices) == 1:
#             result["single"] = (float(prices[0]), None)
#     return result


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    all_rows: list[dict] = []

    # ── STRATEGY A: JSON API ──────────────────────────────────────────────────
    session = requests.Session()
    session.headers.update(HEADERS)

    print("Fetching handles via JSON API...")
    handles = get_handles_json(session)
    print(f"Found {len(handles)} handles")

    for i, handle in enumerate(handles, 1):
        print(f"[{i}/{len(handles)}] {handle}")
        product = get_product_json(session, handle)
        if not product:
            continue
        rows = build_rows_json(handle, product)
        all_rows.extend(rows)
        if rows:
            print(f"    {rows[0]['product_name']} | single={rows[0]['price_usd']}")
        time.sleep(random.uniform(1, 2))

    # ── STRATEGY B: Playwright ────────────────────────────────────────────────
    # with sync_playwright() as pw:
    #     browser = pw.chromium.launch(headless=True)
    #     ctx = browser.new_context(user_agent=HEADERS["User-Agent"], locale="en-US")
    #     page = ctx.new_page()
    #     page.goto(f"{BASE}/?currency=USD", wait_until="domcontentloaded")  # force USD cookie
    #     time.sleep(1)
    #
    #     handles = get_handles_playwright(page)
    #     print(f"Found {len(handles)} handles")
    #
    #     for i, handle in enumerate(handles, 1):
    #         print(f"[{i}/{len(handles)}] {handle}")
    #         scrape_product_playwright(page, handle, all_rows)
    #         time.sleep(random.uniform(2, 4))
    #
    #     browser.close()

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nDone. {len(all_rows)} rows -> {OUT_FILE}")


if __name__ == "__main__":
    main()
