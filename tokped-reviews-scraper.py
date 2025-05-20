import asyncio
import csv
import logging
import re
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Union

from bs4 import BeautifulSoup
from pyppeteer import launch, browser, page

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def get_browser(executable_path: str, headless: bool = True) -> Tuple[browser.Browser, page.Page]:
    """
    Launch a headless browser and return the browser and a new page.
    """
    browser_obj = await launch(executablePath=executable_path, headless=headless)
    page_obj = await browser_obj.newPage()
    return browser_obj, page_obj

async def click_all_expand_buttons(page_obj: page.Page) -> None:
    """
    Click all "Selengkapnya" buttons to expand full review texts.
    """
    try:
        await page_obj.waitForSelector('button.css-89c2tx', timeout=500)
    except asyncio.TimeoutError:
        return

    buttons = await page_obj.xpath("//button[contains(text(), 'Selengkapnya')]")
    for btn in buttons:
        try:
            await btn.click()
            await asyncio.sleep(0.2)
        except Exception:
            continue

def convert_relative_date(relative_date: str) -> str:
    """
    Convert relative date strings from Indonesian (e.g., "2 hari lalu")
    into ISO format (YYYY-MM-DD).
    """
    now = datetime.now()
    rd = relative_date.lower()

    try:
        if "hari ini" in rd:
            actual = now
        elif "kemarin" in rd:
            actual = now - timedelta(days=1)
        elif "hari" in rd and "hari ini" not in rd:
            days = int(rd.split()[0])
            actual = now - timedelta(days=days)
        elif "minggu" in rd:
            weeks = int(rd.split()[0])
            actual = now - timedelta(weeks=weeks)
        elif "bulan" in rd:
            months = int(rd.split()[0])
            actual = now - timedelta(days=months * 30)
        elif "tahun" in rd:
            # Handle "lebih dari X tahun"
            if "lebih dari" in rd:
                match = re.search(r"lebih\s*dar[ai]\s*(\d+)", rd)
                years = int(match.group(1)) if match else 1
            else:
                years = int(rd.split()[0])
            actual = now - timedelta(days=years * 365)
        else:
            return relative_date
        return actual.strftime("%Y-%m-%d")
    except Exception:
        return relative_date

async def extract_reviews_from_page(page_obj: page.Page, page_num: int) -> List[Dict[str, Union[str, int]]]:
    """
    Parse the current page (page_num) and extract review data.
    """
    await click_all_expand_buttons(page_obj)
    content = await page_obj.content()
    soup = BeautifulSoup(content, "html.parser")

    articles = soup.find_all("article", class_="css-15m2bcr")
    reviews: List[Dict[str, Union[str, int]]] = []

    for art in articles:
        div_r = art.find("div", attrs={"data-testid": "icnStarRating"})
        aria = div_r.get('aria-label', '') if div_r else ''
        rating = int(aria.split()[-1]) if 'bintang' in aria else 0

        p_date = art.find("p", class_="css-vqrjg4-unf-heading")
        date_str = p_date.get_text(strip=True) if p_date else 'N/A'
        date = convert_relative_date(date_str)

        name_tag = art.find("span", class_="name")
        name = name_tag.get_text(strip=True) if name_tag else 'N/A'

        text_tag = art.find("span", attrs={"data-testid": "lblItemUlasan"})
        text = text_tag.get_text(strip=True) if text_tag else 'N/A'

        reviews.append({"name": name, "rating": rating, "date": date, "text": text})

    logger.info("Extracted %d reviews from page %d", len(reviews), page_num)
    return reviews

async def get_last_page_number(page_obj: page.Page) -> int:
    """
    Determine the last page number for pagination.
    """
    content = await page_obj.content()
    soup = BeautifulSoup(content, "html.parser")
    btns = soup.find_all("button", class_="css-5p3bh2-unf-pagination-item")
    nums = [int(b.get_text(strip=True)) for b in btns if b.get_text(strip=True).isdigit()]
    return max(nums) if nums else 1

async def scrape_reviews(
    url: str,
    output_csv: str,
    chrome_path: str,
    headless: bool
) -> None:
    """
    Orchestrate the scraping process and save results to CSV.
    """
    browser_obj, page_obj = await get_browser(chrome_path, headless)
    await page_obj.goto(url, {"waitUntil": "networkidle2"})
    await page_obj.reload({"waitUntil": "networkidle2"})
    await page_obj.waitForSelector("article.css-15m2bcr", {"timeout": 10000})

    last = await get_last_page_number(page_obj)
    all_reviews: List[Dict[str, Union[str, int]]] = []

    for pg in range(1, last + 1):
        if pg > 1:
            label = f"Laman {pg}"
            await page_obj.waitForSelector(f'button[aria-label="{label}"]', {"timeout": 10000})
            await page_obj.click(f'button[aria-label="{label}"]')
            await asyncio.sleep(0.7)

        page_reviews = await extract_reviews_from_page(page_obj, pg)
        all_reviews.extend(page_reviews)

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["name", "rating", "date", "text"])
        writer.writeheader()
        writer.writerows(all_reviews)

    logger.info("Saved %d reviews to %s", len(all_reviews), output_csv)
    await browser_obj.close()


def parse_args() -> ArgumentParser:
    parser = ArgumentParser(description="Tokopedia product review scraper")
    parser.add_argument(
        '--url', '-u', required=True,
        help='Tokopedia product review URL'
    )
    parser.add_argument(
        '--output', '-o', default='reviews.csv',
        help='Path to output CSV file'
    )
    parser.add_argument(
        '--chrome-path', '-c', default=None,
        help='Path to Chrome executable (defaults to system install)'
    )
    parser.add_argument(
        '--headless', action='store_true',
        help='Enable headless mode'
    )
    return parser

if __name__ == '__main__':
    args = parse_args().parse_args()

    chrome_path = args.chrome_path or None
    try:
        asyncio.run(
            scrape_reviews(
                url=args.url,
                output_csv=args.output,
                chrome_path=chrome_path,
                headless=args.headless
            )
        )
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
        sys.exit(1)
