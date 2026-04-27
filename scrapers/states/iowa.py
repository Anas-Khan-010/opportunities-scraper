"""
Iowa Procurement scraper — Bid Opportunities Iowa

Scrapes open bid opportunities from the Iowa Department of
Administrative Services bid board.

Source: https://bidopportunities.iowa.gov/
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class IowaBidOpportunitiesScraper(BaseScraper):
    """Scrapes bid opportunities from Iowa DAS."""

    SEARCH_URL = "https://bidopportunities.iowa.gov/"

    def __init__(self):
        super().__init__("Iowa Bid Opportunities")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping Iowa")
            return self.opportunities

        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(6, 10))

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            table = soup.find('table')
            if not table:
                logger.warning("No table found on Iowa bid page")
                self.log_summary()
                return self.opportunities

            rows = table.find_all('tr')
            data_rows = [r for r in rows if r.find('td')]

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    self.add_opportunity(opp)

            logger.info(f"  Parsed {len(data_rows)} rows from Iowa bids")

        except Exception as e:
            logger.error(f"Error scraping Iowa bids: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        """
        Parse a table row from the Iowa bid board.
        Columns: (checkbox), Bid Number, Agency, Contact, Title,
                 Effective Date, Expiration Date, (links), (links)
        """
        cells = row.find_all('td')
        if len(cells) < 5:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]

            # Skip empty rows (some rows have no text in any cell)
            if not any(t for t in cell_texts if t):
                return None

            # Column mapping (0=checkbox, 1=Bid Number, 2=Agency, 3=Contact,
            # 4=Title, 5=Effective Date, 6=Expiration Date)
            opp_number = cell_texts[1] if len(cell_texts) > 1 else ''
            agency = cell_texts[2] if len(cell_texts) > 2 else ''
            contact = cell_texts[3] if len(cell_texts) > 3 else ''
            title = cell_texts[4] if len(cell_texts) > 4 else ''
            posted_str = cell_texts[5] if len(cell_texts) > 5 else ''
            deadline_str = cell_texts[6] if len(cell_texts) > 6 else ''

            if not title and not opp_number:
                return None

            if not title:
                title = opp_number

            deadline = parse_date(deadline_str) if deadline_str else None
            posted_date = parse_date(posted_str) if posted_str else None

            # Extract any links (detail or document)
            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"https://bidopportunities.iowa.gov{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif '/Home/BidDetail' in href or '/BidDetail' in href:
                    detail_url = href
                elif not detail_url and href != '#':
                    detail_url = href

            source_url = detail_url or self.SEARCH_URL
            category = categorize_opportunity(title, '')

            description = f"Contact: {contact}" if contact else None

            return {
                'title': title,
                'organization': f"Iowa - {agency}" if agency else 'State of Iowa',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Iowa',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': posted_date,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing Iowa row: {e}")
            return None


def get_iowa_scrapers():
    return [IowaBidOpportunitiesScraper()]


if __name__ == '__main__':
    scraper = IowaBidOpportunitiesScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
