"""
Nike PH Product Scraper — v2 (JSON + PDP)
==========================================
1. Extracts all product data from __NEXT_DATA__ JSON on the listing page
2. Paginates using the internal API endpoint (no scrolling needed)
3. Filters by Product_Tagging (badgeLabel) and Discount_Price
4. Visits each valid product's detail page for full fields
5. Saves to CSV

Requirements:
    pip install playwright pandas
    playwright install chromium

Usage:
    python nike_scraper.py
"""

import asyncio
import csv
import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────
BASE_URL = "https://www.nike.com/ph/w"
NIKE_BASE = "https://www.nike.com"
OUTPUT_CSV = "nike_products.csv"
TOP20_CSV = "top_20_rating_review.csv"
CHECKPOINT_CSV = "nike_checkpoint.csv"
PDP_TIMEOUT = 30_000
PDP_DELAY_MIN = 1.5
PDP_DELAY_MAX = 3.5
CHECKPOINT_EVERY = 25
API_PAGE_SIZE = 24            # Nike returns 24 products per page
API_DELAY_MIN = 0.8           # delay between API page fetches
API_DELAY_MAX = 1.5

CSV_COLUMNS = [
    "Product_URL",
    "Product_Image_URL",
    "Product_Tagging",
    "Product_Name",
    "Product_Description",
    "Original_Price",
    "Discount_Price",
    "Sizes_Available",
    "Vouchers",
    "Available_Colors",
    "Color_Shown",
    "Style_Code",
    "Rating_Score",
    "Review_Count",
]


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
async def safe_text(locator, default=""):
    try:
        if await locator.count() > 0:
            return (await locator.first.inner_text()).strip()
    except Exception:
        pass
    return default


async def safe_attr(locator, attr, default=""):
    try:
        if await locator.count() > 0:
            val = await locator.first.get_attribute(attr)
            return val.strip() if val else default
    except Exception:
        pass
    return default


def fmt_price(value, currency="PHP"):
    """Format a numeric price into a string like '₱9,677'."""
    if value is None or value == 0:
        return ""
    return f"₱{value:,.0f}"


def parse_product_from_json(grouping):
    """
    Convert a productGrouping JSON object into a flat dict.
    Uses the first (default displayed) colorway as representative.
    """
    products_in_group = grouping.get("products", [])
    if not products_in_group:
        return None

    p = products_in_group[0]
    num_colors = len(products_in_group)

    copy = p.get("copy", {})
    prices = p.get("prices", {})
    colors = p.get("displayColors", {})
    pdp = p.get("pdpUrl", {})
    images = p.get("colorwayImages", {})
    promos = p.get("promotions") or {}
    visibilities = promos.get("visibilities") or []

    # Tagging = badgeLabel  (what appears as product-card__messaging)
    badge_label = (p.get("badgeLabel") or "").strip()

    # Voucher = promotion title (e.g. "Limited Time Offer")
    voucher = ""
    if visibilities:
        voucher = (visibilities[0].get("title") or "").strip()

    # Prices
    initial_price = prices.get("initialPrice", 0)
    current_price = prices.get("currentPrice", 0)
    has_discount = current_price < initial_price and current_price > 0

    return {
        "Product_URL": pdp.get("url", ""),
        "Product_Image_URL": images.get("portraitURL", "") or images.get("squarishURL", ""),
        "Product_Tagging": badge_label,
        "Product_Name": copy.get("title", ""),
        "Product_Description": "",  # PDP
        "Original_Price": fmt_price(initial_price),
        "Discount_Price": fmt_price(current_price) if has_discount else "",
        "Sizes_Available": "",      # PDP
        "Vouchers": voucher,
        "Available_Colors": f"{num_colors} {'Colour' if num_colors == 1 else 'Colours'}",
        "Color_Shown": colors.get("colorDescription", ""),
        "Style_Code": p.get("productCode", ""),
        "Rating_Score": "",         # PDP
        "Review_Count": "",         # PDP
    }


# ────────────────────────────────────────────────────────────
# Phase 1 — Collect all listing data via JSON + direct API
# ────────────────────────────────────────────────────────────
async def collect_all_products(page, context):
    """
    1. Extract first batch from __NEXT_DATA__
    2. Scroll briefly to warm up session
    3. Use context.request.get() for all remaining pages (shares browser cookies)
    """
    print("  Extracting __NEXT_DATA__ from page ...")
    raw_json = await page.evaluate("""
        () => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? el.textContent : null;
        }
    """)
    if not raw_json:
        raise RuntimeError("Could not find __NEXT_DATA__ on the page.")

    data = json.loads(raw_json)
    wall = data["props"]["pageProps"]["initialState"]["Wall"]
    page_data = wall["pageData"]
    total_resources = page_data.get("totalResources", 0)
    total_pages = page_data.get("totalPages", 0)

    print(f"  Total products reported: {total_resources}  |  Pages: {total_pages}")

    all_products = []
    seen_codes = set()

    def add_groupings(groupings):
        count = 0
        for g in groupings:
            prod = parse_product_from_json(g)
            if prod and prod["Style_Code"] not in seen_codes:
                seen_codes.add(prod["Style_Code"])
                all_products.append(prod)
                count += 1
        return count

    # First batch from __NEXT_DATA__
    first_groupings = wall.get("productGroupings", [])
    added = add_groupings(first_groupings)
    print(f"  Page 1: {added} products  (total: {len(all_products)})")

    # Scroll once to warm up session cookies for API
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(4000)

    # Direct API calls for all remaining pages
    api_base = (
        "https://api.nike.com/discover/product_wall/v1/"
        "marketplace/PH/language/en-GB/"
        "consumerChannelId/d9a5bc42-4b9c-4976-858a-f159cf99c647"
    )
    req_headers = {
        "origin": "https://www.nike.com",
        "referer": "https://www.nike.com/",
        "accept": "application/json",
        "nike-api-caller-id": "com.nike.commerce.nikedotcom.web",
    }

    anchor = API_PAGE_SIZE  # start after first page
    consecutive_errors = 0
    MAX_ERRORS = 15

    while anchor < total_resources and consecutive_errors < MAX_ERRORS:
        url = f"{api_base}?path=%2Fph%2Fw&queryType=PRODUCTS&anchor={anchor}&count={API_PAGE_SIZE}"
        try:
            resp = await context.request.get(url, headers=req_headers)
            if resp.ok:
                body = await resp.json()
                groups = body.get("productGroupings", [])
                if not groups:
                    print(f"  No more products at anchor={anchor}")
                    break
                added = add_groupings(groups)
                anchor += API_PAGE_SIZE
                consecutive_errors = 0

                # Print progress every ~4 pages
                if len(all_products) % (API_PAGE_SIZE * 4) < API_PAGE_SIZE:
                    pct = (len(all_products) / total_resources) * 100
                    print(f"  ... {len(all_products)}/{total_resources} products ({pct:.0f}%)")

                await asyncio.sleep(random.uniform(API_DELAY_MIN, API_DELAY_MAX))
            else:
                consecutive_errors += 1
                status = resp.status
                print(f"  API error {status} at anchor={anchor} (attempt {consecutive_errors})")

                if status == 429:
                    print("  Rate limited — waiting 30s ...")
                    await asyncio.sleep(30)
                elif consecutive_errors % 3 == 0:
                    # Refresh page to renew cookies
                    print("  Refreshing page for new session ...")
                    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(5000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(4000)
                else:
                    await asyncio.sleep(5)
        except Exception as exc:
            consecutive_errors += 1
            print(f"  Exception at anchor={anchor}: {exc}")
            await asyncio.sleep(5)

    print(f"\n  === Total unique products collected: {len(all_products)} ===")
    return all_products


# ────────────────────────────────────────────────────────────
# Phase 2 — Scrape detail pages (PDP)
# ────────────────────────────────────────────────────────────
async def scrape_pdp(page, product: dict) -> dict:
    """Visit a product detail page and fill Description, Sizes, Rating, Reviews."""
    url = product["Product_URL"]
    if not url:
        return product

    try:
        await page.goto(url, timeout=PDP_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # ── Extract from __NEXT_DATA__ (description + sizes) ──
        pdp_json = await page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)

        if pdp_json:
            try:
                pdp_data = json.loads(pdp_json)
                pp = pdp_data.get("props", {}).get("pageProps", {})
                sp = pp.get("selectedProduct", {})

                if sp:
                    # Description from productInfo
                    pi = sp.get("productInfo", {})
                    desc = (
                        pi.get("productDescription", "")
                        or pi.get("reasonToBuy", "")
                        or pi.get("subtitle", "")
                    )
                    if desc:
                        # Strip HTML tags
                        desc = re.sub(r"<[^>]+>", " ", desc).strip()
                        desc = re.sub(r"\s+", " ", desc)
                        product["Product_Description"] = desc

                    # Sizes from sizes[]
                    sizes_list = sp.get("sizes", [])
                    if sizes_list:
                        prefix = sp.get("localizedLabelPrefix", "")
                        available = []
                        for s in sizes_list:
                            if s.get("status") == "ACTIVE" or s.get("status") == "LOW":
                                label = s.get("localizedLabel", "") or s.get("label", "")
                                lp = s.get("localizedLabelPrefix", prefix)
                                if label:
                                    available.append(f"{lp} {label}" if lp else label)
                        if available:
                            product["Sizes_Available"] = ", ".join(available)

                # Also check initialState (older PDP format)
                pdp_state = pp.get("initialState", {})
                if pdp_state:
                    for key in ["product", "Product"]:
                        pdp_product = pdp_state.get(key)
                        if pdp_product and isinstance(pdp_product, dict):
                            if not product["Product_Description"]:
                                d = pdp_product.get("descriptionPreview", "") or pdp_product.get("description", "")
                                if d:
                                    product["Product_Description"] = d.strip()
                            if not product["Sizes_Available"]:
                                skus = pdp_product.get("skus", [])
                                if skus:
                                    sz = [str(sk.get("localizedSize","") or sk.get("nikeSize","")) for sk in skus if sk.get("available", True)]
                                    if sz:
                                        product["Sizes_Available"] = ", ".join(sz)
                            break

            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # ── DOM fallback: Description ──
        if not product["Product_Description"]:
            desc = await safe_text(page.locator('[data-testid="product-description"]'))
            if not desc:
                desc = await safe_text(page.locator('.description-preview__content, .description-preview p'))
            product["Product_Description"] = desc

        # ── DOM fallback: Sizes ──
        if not product["Sizes_Available"]:
            try:
                grid = page.locator('[data-testid="size-grid"], fieldset')
                if await grid.count() > 0:
                    labels = grid.first.locator("label")
                    if await labels.count() > 0:
                        all_sizes = await labels.all_inner_texts()
                        all_sizes = [s.strip() for s in all_sizes if s.strip()]
                        product["Sizes_Available"] = ", ".join(all_sizes)
            except Exception:
                pass

        # ── DOM fallback: Voucher ──
        if not product["Vouchers"]:
            v = await safe_text(page.locator('.promo-message, [data-testid="promo-message"]'))
            product["Vouchers"] = v

        # ── Reviews & Rating (from TurnTo widget meta tags + DOM) ──
        # Scroll down to trigger lazy loading of the reviews section
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.8)")
        await page.wait_for_timeout(2000)

        # Best source: <meta itemprop="ratingValue" content="4.7">
        #              <meta itemprop="reviewCount"  content="610">
        try:
            rating_meta = page.locator('meta[itemprop="ratingValue"]')
            if await rating_meta.count() > 0:
                val = await rating_meta.first.get_attribute("content")
                if val:
                    product["Rating_Score"] = val.strip()
        except Exception:
            pass

        try:
            count_meta = page.locator('meta[itemprop="reviewCount"]')
            if await count_meta.count() > 0:
                val = await count_meta.first.get_attribute("content")
                if val:
                    product["Review_Count"] = val.strip()
        except Exception:
            pass

        # Fallback: innerHTML of reviews-summary testid (returns "4.7 stars")
        if not product["Rating_Score"]:
            try:
                el = page.locator('[data-testid="reviews-summary"]')
                if await el.count() > 0:
                    html = await el.first.inner_html()
                    m = re.search(r"([\d.]+)\s*stars?", html)
                    if m:
                        product["Rating_Score"] = m.group(1)
            except Exception:
                pass

        # Fallback: "Reviews (N)" text for count
        if not product["Review_Count"]:
            try:
                rev_el = page.locator("text=/Reviews \\(\\d+\\)/")
                if await rev_el.count() > 0:
                    raw = (await rev_el.first.inner_text()).strip()
                    m = re.search(r"Reviews\s*\((\d+)\)", raw)
                    if m:
                        product["Review_Count"] = m.group(1)
            except Exception:
                pass

    except PlaywrightTimeout:
        print("  [timeout]", end="")
    except Exception as exc:
        print(f"  [error: {exc}]", end="")

    return product


# ────────────────────────────────────────────────────────────
# CSV helpers
# ────────────────────────────────────────────────────────────
def save_csv(products, filepath):
    df = pd.DataFrame(products)
    for c in CSV_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[CSV_COLUMNS]
    df.to_csv(filepath, index=False, encoding="utf-8-sig")


def price_to_numeric(price_str):
    """Convert '₱7,395' -> 7395.0.  Returns 0.0 for empty/invalid."""
    if not price_str or not isinstance(price_str, str):
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ────────────────────────────────────────────────────────────
# Analytics
# ────────────────────────────────────────────────────────────
def print_top10_expensive(products):
    """Print Top 10 most expensive products sorted by Discount_Price (desc)."""
    with_price = [
        p for p in products if price_to_numeric(p.get("Discount_Price", "")) > 0
    ]
    with_price.sort(key=lambda p: price_to_numeric(p["Discount_Price"]), reverse=True)
    top10 = with_price[:10]

    print("\n" + "=" * 65)
    print("  Top 10 Most Expensive Products (by Discount Price)")
    print("=" * 65)
    for i, p in enumerate(top10, 1):
        print(f"  {i:>2}. {p['Product_Name']}")
        print(f"      Price: {p['Discount_Price']}")
        print(f"      URL  : {p['Product_URL']}")
    print("=" * 65)


def create_top20_rating_csv(products):
    """
    Rank products by Rating_Score (desc), then Review_Count (desc).
    Only include products with Review_Count > 150.
    If rating AND review count are identical → same rank.
    Save top 20 to CSV.
    """
    eligible = []
    for p in products:
        try:
            rc = float(p.get("Review_Count", 0) or 0)
        except (ValueError, TypeError):
            rc = 0
        if rc > 150:
            try:
                rs = float(p.get("Rating_Score", 0) or 0)
            except (ValueError, TypeError):
                rs = 0
            eligible.append({**p, "_rs": rs, "_rc": rc})

    # Sort by rating desc, then review count desc
    eligible.sort(key=lambda x: (x["_rs"], x["_rc"]), reverse=True)

    # Assign dense rank (same rank for ties on BOTH rating AND review)
    ranked = []
    current_rank = 0
    prev_rs, prev_rc = None, None
    for item in eligible:
        if item["_rs"] != prev_rs or item["_rc"] != prev_rc:
            current_rank += 1
        prev_rs, prev_rc = item["_rs"], item["_rc"]
        ranked.append({**item, "Rank": current_rank})

    top20 = ranked[:20]

    print(f"\n  Rating/Review analysis:")
    print(f"    Products with Review_Count > 150: {len(eligible)}")
    print(f"    Top 20 saved to {TOP20_CSV}")

    if top20:
        df = pd.DataFrame(top20)
        cols = ["Rank"] + CSV_COLUMNS
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        df = df[cols]
        df.to_csv(TOP20_CSV, index=False, encoding="utf-8-sig")
    else:
        # Write empty CSV with headers
        df = pd.DataFrame(columns=["Rank"] + CSV_COLUMNS)
        df.to_csv(TOP20_CSV, index=False, encoding="utf-8-sig")
        print("    (no products met the Review_Count > 150 criteria)")


# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────
async def main():
    start_time = time.time()
    print("=" * 65)
    print("  Nike PH Product Scraper v2 (JSON + PDP)")
    print(f"  Target : {BASE_URL}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-PH",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )
        page = await context.new_page()

        # ═══ STEP 1: Open Website ═══════════════════════════
        print(f"\n[Step 1] Opening {BASE_URL} ...")
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_selector("#__NEXT_DATA__", timeout=15_000)
        except PlaywrightTimeout:
            print("  Page load slow, continuing ...")

        # Close cookie banner
        try:
            btn = page.locator(
                'button:has-text("Accept"), '
                'button[data-testid="dialog-accept-button"]'
            )
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        await page.wait_for_timeout(3000)

        # ═══ STEP 2: Load & Scrape All Results ══════════════
        print(f"\n[Step 2] Collecting all product listings via JSON + API ...")
        all_products = await collect_all_products(page, context)
        total_scraped = len(all_products)

        # ═══ STEP 3: Tagging Rule ═══════════════════════════
        print(f"\n[Step 3] Applying tagging & discount filter ...")

        empty_tagging = [p for p in all_products if not p["Product_Tagging"]]
        tagged = [p for p in all_products if p["Product_Tagging"]]
        valid = [p for p in tagged if p["Discount_Price"]]

        print(f"\n  Total products scraped:            {total_scraped}")
        print(f"  Total products with empty tagging: {len(empty_tagging)}")
        print(f"  Products with valid tagging:       {len(tagged)}")
        print(f"  Products with tagging + discount:  {len(valid)}  <-- final CSV candidates")

        if not valid:
            print("\n  WARNING: No products passed both filters!")
            print("  Saving all tagged products instead ...")
            valid = tagged

        # ═══ Visit PDP for each valid product ════════════════
        print(f"\n  Visiting {len(valid)} product detail pages ...\n")
        completed = []

        for i, prod in enumerate(valid):
            label = f"[{i+1}/{len(valid)}]"
            name_short = prod["Product_Name"][:45]
            print(f"  {label} {name_short:45s} {prod['Style_Code']:15s}", end="")

            updated = await scrape_pdp(page, prod)
            completed.append(updated)

            d = "D" if updated["Product_Description"] else "-"
            s = "S" if updated["Sizes_Available"] else "-"
            r = "R" if updated["Rating_Score"] else "-"
            print(f"  [{d}{s}{r}]")

            if (i + 1) % CHECKPOINT_EVERY == 0:
                save_csv(completed, CHECKPOINT_CSV)
                print(f"        checkpoint saved ({i+1} products)")

            await asyncio.sleep(random.uniform(PDP_DELAY_MIN, PDP_DELAY_MAX))

        await browser.close()

    # ═══ STEP 4: Save Final CSV ══════════════════════════════
    print(f"\n[Step 4] Saving final CSV ...")
    save_csv(completed, OUTPUT_CSV)
    print(f"  Saved {len(completed)} products -> {OUTPUT_CSV}")

    if os.path.exists(CHECKPOINT_CSV):
        os.remove(CHECKPOINT_CSV)

    # ═══ STEP 5: Analytics ═══════════════════════════════════
    print(f"\n[Step 5] Analytics ...")
    print(f"\n  Total products with empty tagging: {len(empty_tagging)}")

    # A. Top 10 Most Expensive (by Discount Price)
    print_top10_expensive(completed)

    # B. Top 20 Rating & Review Ranking (Review Count > 150)
    create_top20_rating_csv(completed)

    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)

    print("\n" + "=" * 65)
    print(f"  DONE - {len(completed)} products saved to {OUTPUT_CSV}")
    print(f"  Time elapsed: {mins}m {secs}s")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
