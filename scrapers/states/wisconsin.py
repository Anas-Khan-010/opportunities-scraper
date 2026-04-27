"""
Wisconsin Procurement scraper — VendorNet

Scrapes open bid opportunities from Wisconsin's official
VendorNet portal.  Uses Selenium since the site is ASP.NET
with server-rendered GridView dat.

Source: https://vendornet.wi.gov/Bids.aspx
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class WisconsinVendorNetScraper(BaseScraper):
    """Scrapes bid opportunities from Wisconsin VendorNet."""

    BIDS_URL = "https://vendornet.wi.gov/Bids.aspx"

    def __init__(self):
        super().__init__("Wisconsin VendorNet")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for Wisconsin scraper")
                return self.opportunities

            driver.get(self.BIDS_URL)
            time.sleep(5)

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # VendorNet uses ASP.NET GridView — look for the main data table
            table = (
                soup.find('table', id=lambda x: x and 'GridView' in x) or
                soup.find('table', id=lambda x: x and 'grd' in str(x).lower()) or
                soup.find('table', class_='table') or
                soup.find('table')
            )

            if not table:
                logger.warning("No bid data table found on Wisconsin VendorNet")
                self.log_summary()
                return self.opportunities

            rows = table.find_all('tr')
            data_rows = rows[1:]  # Skip header row

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    self.add_opportunity(opp)

            logger.info(f"  Parsed {len(data_rows)} rows from WI VendorNet")

        except Exception as e:
            logger.error(f"Error scraping Wisconsin VendorNet: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 3:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]

            # Find links for detail pages and docs
            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"https://vendornet.wi.gov/{href.lstrip('/')}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            # WI VendorNet typically: Bid Number, Title, Agency, Close Date, Category
            opp_number = cell_texts[0] if len(cell_texts) > 0 else None
            title = cell_texts[1] if len(cell_texts) > 1 else cell_texts[0]
            org = cell_texts[2] if len(cell_texts) > 2 else 'State of Wisconsin'
            deadline_str = cell_texts[3] if len(cell_texts) > 3 else None
            category_raw = cell_texts[4] if len(cell_texts) > 4 else ''

            if not title:
                return None

            deadline = parse_date(deadline_str) if deadline_str else None
            source_url = detail_url or self.BIDS_URL
            category = categorize_opportunity(title, category_raw)

            return {
                'title': title,
                'organization': org if org else 'State of Wisconsin',
                'description': f"Category: {category_raw}" if category_raw else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Wisconsin',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing WI row: {e}")
            return None


def get_wisconsin_scrapers():
    return [WisconsinVendorNetScraper()]


if __name__ == '__main__':
    scraper = WisconsinVendorNetScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
