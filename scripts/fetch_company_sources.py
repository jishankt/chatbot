"""
scripts/fetch_company_sources.py
Fetches verbatim raw extracts from authorized Kepler Tech URLs and saves to data/raw/company/
"""

import os
import shutil
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
import html2text

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_COMPANY_DIR = BASE_DIR / "data" / "raw" / "company"
RAW_DIR = BASE_DIR / "data" / "raw"

SOURCES = [
    {
        "url": "https://www.keplertech.ae/",
        "filename": "keplertech_ae_home.txt",
        "site": "store",
        "description": "keplertech.ae home page"
    },
    {
        "url": "https://www.keplertech.ae/about-us/",
        "filename": "keplertech_ae_about_us.txt",
        "site": "store",
        "description": "keplertech.ae about us page"
    },
    {
        "url": "https://www.keplertech.ae/services/",
        "filename": "keplertech_ae_services.txt",
        "site": "store",
        "description": "keplertech.ae services overview"
    },
    {
        "url": "https://www.keplertech.ae/services/best-printer-repair-service-in-dubai/",
        "filename": "keplertech_ae_service_repair.txt",
        "site": "store",
        "description": "keplertech.ae printer repair service"
    },
    {
        "url": "https://www.keplertech.ae/services/best-printer-rental-and-lease-service-in-dubai/",
        "filename": "keplertech_ae_service_rental.txt",
        "site": "store",
        "description": "keplertech.ae printer rental and lease service"
    },
    {
        "url": "https://www.keplertech.ae/services/best-managed-print-services-in-dubai-uae/",
        "filename": "keplertech_ae_service_managed_print.txt",
        "site": "store",
        "description": "keplertech.ae managed print services"
    },
    {
        "url": "https://www.keplertech.ae/contact-us/",
        "filename": "keplertech_ae_contact_us.txt",
        "site": "store",
        "description": "keplertech.ae contact us page"
    },
    {
        "url": "https://www.keplertechllc.com/countries-we-serve/",
        "filename": "keplertechllc_countries_we_serve.txt",
        "site": "corporate",
        "description": "keplertechllc.com countries we serve page"
    },
    {
        "url": "https://www.keplertechllc.com/countries-we-serve/africa/",
        "filename": "keplertechllc_africa.txt",
        "site": "corporate",
        "description": "keplertechllc.com africa shipping page"
    },
    {
        "url": "https://www.keplertechllc.com/contact-us/",
        "filename": "keplertechllc_contact_us.txt",
        "site": "corporate",
        "description": "keplertechllc.com contact us page"
    },
    {
        "url": "https://www.keplertechllc.com/about-us/",
        "filename": "keplertechllc_about_us.txt",
        "site": "corporate",
        "description": "keplertechllc.com about us page"
    }
]


def extract_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script, style, noscript, svg
    for el in soup(["script", "style", "noscript", "svg"]):
        el.decompose()

    # Find main content container if possible
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_="entry-content")
        or soup.find("div", id="primary")
        or soup.find("body")
    )
    target_html = str(main) if main else html

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    h.body_width = 0
    text = h.handle(target_html)
    return text.strip()


def main():
    RAW_COMPANY_DIR.mkdir(parents=True, exist_ok=True)
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for item in SOURCES:
        url = item["url"]
        fname = item["filename"]
        out_path = RAW_COMPANY_DIR / fname
        print(f"Fetching {url} -> {out_path.name}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                content = extract_content(html)
                # Prepend source metadata header
                meta_header = f"URL: {url}\nSITE: {item['site']}\nDATE: 2026-10-26\nDESCRIPTION: {item['description']}\n\n---\n\n"
                out_path.write_text(meta_header + content, encoding="utf-8")
                print(f"Saved {out_path.name} ({len(content)} chars)")
        except Exception as e:
            print(f"Error fetching {url}: {e}")

    # Copy existing CX-02 raw files to data/raw/company/
    cx02_files = [
        "citizen_cx02_page.txt",
        "cx02_datasheet.txt",
        "cx02_product_page.txt",
        "media_4x6_page.txt",
        "media_5x7_page.txt",
        "media_6x8_page.txt",
        "bag_product_page.txt",
        "pen_product_page.txt",
        "terms_and_conditions.txt",
        "faq.txt"
    ]
    for cxf in cx02_files:
        src = RAW_DIR / cxf
        dst = RAW_COMPANY_DIR / cxf
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"Copied {cxf} into {RAW_COMPANY_DIR.name}/")

    print("Raw extracts complete.")


if __name__ == "__main__":
    main()
