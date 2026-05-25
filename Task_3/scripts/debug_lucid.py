#!/usr/bin/env python3
"""Debug: bullets and SNS discount for LUCID B0DDY9GDNQ."""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from amazon_scraper_template import AmazonScraperBase
from bs4 import BeautifulSoup


class LucidDebug(AmazonScraperBase):
    BRAND = "Lucid"; SEED_ASIN = "B0DDY9GDNQ"; STOREFRONT_URL = ""
    OUT_FILENAME = "lucid_amazon.csv"; DEFAULT_FORMAT = "instant"

scraper = LucidDebug()
html = scraper.fetch_html("https://www.amazon.com/dp/B0DDY9GDNQ")
soup = BeautifulSoup(html, "lxml")

print("=== Feature bullets ===")
for li in soup.select("#feature-bullets li")[:10]:
    t = li.get_text(" ", strip=True)
    if t:
        print(f"  {t[:120]}")

print("\n=== Detail bullets ===")
for li in soup.select("#detailBullets_feature_div li")[:10]:
    t = li.get_text(" ", strip=True).encode("cp1251", errors="replace").decode("cp1251")
    if t:
        print(f"  {t[:120]}")

print("\n=== techSpec table ===")
for tr in soup.select("#productDetails_techSpec_section_1 tr")[:10]:
    print(f"  {tr.get_text(' ', strip=True)[:120]}")

print("\n=== SNS discount % ===")
# look for % off text near the sns block
sns = soup.select_one("#snsAccordionRowMiddle")
if sns:
    text = sns.get_text(" ", strip=True)
    print(f"  Full SNS text: {text[:200]}")
    m = re.search(r'(\d+)\s*%', text)
    print(f"  Discount % in SNS text: {m.group(1) if m else 'NOT FOUND'}")

# Also check nearby savingsPercentage
for el in soup.select(".savingsPercentage")[:5]:
    print(f"  savingsPercentage: '{el.get_text(strip=True)}'")

print("\n=== Regex serving patterns in bullets+techspec ===")
search_els = (
    soup.select("#feature-bullets li") +
    soup.select("#detailBullets_feature_div li") +
    soup.select("#productDetails_techSpec_section_1 tr")
)
bullets = " ".join(el.get_text(" ", strip=True) for el in search_els)
print(f"  Combined text (first 400): {bullets[:400]}")
PATTERNS = [
    r"(\d+)\s*[Ss]erving",
    r"(\d+)\s*[Cc]ount",
    r"(\d+)\s*[Ss]achet",
    r"(\d+)\s*[Pp]acket",
]
for p in PATTERNS:
    m = re.search(p, bullets)
    print(f"  {p}: {m.group(1) if m else 'not found'}")
