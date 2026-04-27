"""
Wyoming Procurement scraper — A&I General Services Purchasing Bids

Scrapes open bid opportunities from Wyoming's A&I General Services
Purchasing Division portal.

Source: https://ai.wyo.gov/divisions/general-services/purchasing/bid-opportunities
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class WyomingPurchasingScraper(BaseScraper):
    """Scrapes bid opportunities from Wyoming A&I Purchasing."""

    BID_URL = "https://ai.wyo.gov/divisions/general-services/purchasing/bid-opportunities"
    BASE_URL = "https://ai.wyo.gov"

    def __init__(self):
        super().__init__("Wyoming A&I Purchasing")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping Wyoming")
            return self.opportunities

        try:
            driver.get(self.BID_URL)
            time.sleep(random.uniform(6, 10))

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Wyoming uses a Drupal/WordPress CMS page. Get the content area.
            content = (
                soup.find('div', class_=lambda x: x and 'field-items' in str(x)) or
                soup.find('div', class_=lambda x: x and 'page-content' in str(x)) or
                soup.find('main') or
                soup.find('article') or
                soup
            )

            # Look for tables first
            table = content.find('table')
            if table:
                rows = table.find_all('tr')
                data_rows = [r for r in rows if r.find('td')]
                for row in data_rows:
                    if self.reached_limit():
                        break
                    opp = self.parse_opportunity(row)
                    if opp:
                        self.add_opportunity(opp)
                logger.info(f"  Parsed {len(data_rows)} rows from WY A&I")
            else:
                # No table — look for links to bid documents
                links = content.find_all('a', href=True)
                for link in links:
                    if self.reached_limit():
                        break

                    href = link['href']
                    text = clean_text(link.get_text(strip=True))

                    if not text or len(text) < 5:
                        continue
                    if href.startswith('#') or href.startswith('javascript'):
                        continue

                    # Look for PDF docs or bid-related links
                    is_bid_link = (
                        href.lower().endswith('.pdf') or
                        href.lower().endswith('.doc') or
                        href.lower().endswith('.docx') or
                        'bid' in text.lower() or
                        'rfp' in text.lower() or
                        'solicitation' in text.lower()
                    )

                    if is_bid_link:
                        full_href = href if href.startswith('http') else f"{self.BASE_URL}{href}"
                        opp = self._build_link_opportunity(text, full_href)
                        if opp:
                            self.add_opportunity(opp)

                logger.info(f"  Parsed bid links from WY A&I")

        except Exception as e:
            logger.error(f"Error scraping Wyoming A&I: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 2:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]

            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"{self.BASE_URL}{href}"
                if href.lower().endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            title = max(cell_texts, key=len) if cell_texts else None
            if not title or len(title) < 5:
                return None

            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of Wyoming',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'Wyoming',
                'source': self.source_name,
                'source_url': detail_url or self.BID_URL,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing WY row: {e}")
            return None

    def _build_link_opportunity(self, title, url):
        if not title or len(title) < 5:
            return None

        doc_urls = [url] if url.lower().endswith('.pdf') else []
        category = categorize_opportunity(title, '')

        return {
            'title': title,
            'organization': 'State of Wyoming',
            'description': None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': None,
            'category': category,
            'location': 'Wyoming',
            'source': self.source_name,
            'source_url': url,
            'opportunity_number': None,
            'posted_date': None,
            'document_urls': doc_urls,
            'opportunity_type': 'bid',
        }


def get_wyoming_scrapers():
    return [WyomingPurchasingScraper()]


if __name__ == '__main__':
    scraper = WyomingPurchasingScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
