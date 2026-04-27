"""
Utah Procurement scraper — Utah Bonfire Hub

Scrapes open bid opportunities from the Utah Bonfire Hub platform.
Uses Selenium to wait for Bonfire's SPA layout to render the table.

Source: https://utah.bonfirehub.com/portal/?tab=openOpportunities
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class UtahBonfireScraper(BaseScraper):
    """Scrapes bid opportunities from Utah Bonfire Hub."""

    SEARCH_URL = "https://utah.bonfirehub.com/portal/?tab=openOpportunities"
    BASE_URL = "https://utah.bonfirehub.com"

    def __init__(self):
        super().__init__("Utah Bonfire Hub")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error(f"Selenium driver unavailable — skipping {self.source_name}")
            return self.opportunities

        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(8, 12))  # Bonfire can be slow to initialize SPA

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            table = soup.find('table')

            if not table:
                logger.warning(f"No results table found on {self.source_name}")
                self.log_summary()
                return self.opportunities

            rows = table.find_all('tr')
            if len(rows) > 1:
                data_rows = [r for r in rows if r.find('td')]
                
                for row in data_rows:
                    if self.reached_limit():
                        break
                    opp = self.parse_opportunity(row)
                    if opp:
                        self.add_opportunity(opp)

                logger.info(f"  Parsed {len(data_rows)} rows from {self.source_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        """
        Parses a single row from the Bonfire Hub table.
        Columns typically:
        Status, Ref. #, Project, Department, Close Date, Days Left, Action
        """
        cells = row.find_all('td')
        if len(cells) < 4:
            return None

        try:
            cell_texts = [clean_text(c.get_text(separator=' ', strip=True)) for c in cells]
            
            # Status, Ref. #, Project, Department, Close Date
            status = cell_texts[0] if len(cell_texts) > 0 else ''
            opp_number = cell_texts[1] if len(cell_texts) > 1 else ''
            title = cell_texts[2] if len(cell_texts) > 2 else ''
            org = cell_texts[3] if len(cell_texts) > 3 else ''
            deadline_str = cell_texts[4] if len(cell_texts) > 4 else ''

            if not title:
                return None

            deadline = parse_date(deadline_str) if deadline_str else None

            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = self.BASE_URL + href
                
                if '/opportunities/' in href:
                    detail_url = href

            source_url = detail_url or self.SEARCH_URL
            category = categorize_opportunity(title, '')

            description = f"Status: {status}" if status else None

            return {
                'title': title,
                'organization': org or 'State of Utah',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Utah',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing Utah row: {e}")
            return None


def get_utah_scrapers():
    return [UtahBonfireScraper()]


if __name__ == '__main__':
    scraper = UtahBonfireScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
