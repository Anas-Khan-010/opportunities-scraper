"""
Maine Procurement scraper — Bureau of General Services Procurement

Scrapes open bid/RFP opportunities from Maine's Bureau of
General Services procurement portal.

Source: https://www.maine.gov/dafs/bbm/procurementservices/vendors/current-bid-opportunities
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class MaineProcurementScraper(BaseScraper):
    """Scrapes bid opportunities from Maine Bureau of General Services."""

    BIDS_URL = "https://www.maine.gov/dafs/bbm/procurementservices/vendors/current-bid-opportunities"

    def __init__(self):
        super().__init__("Maine BGS Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for Maine scraper")
                return self.opportunities

            driver.get(self.BIDS_URL)
            time.sleep(6)

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Maine uses a Drupal CMS — bids are often in tables or structured content
            tables = soup.find_all('table')
            found_data = False

            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                data_rows = rows[1:]
                for row in data_rows:
                    if self.reached_limit():
                        break
                    opp = self.parse_opportunity(row)
                    if opp:
                        self.add_opportunity(opp)
                        found_data = True

                if found_data:
                    logger.info(f"  Parsed {len(data_rows)} rows from ME BGS")
                    break

            if not found_data:
                # Try content area links
                content = soup.find('div', class_='field-items') or soup.find('main') or soup.find('article')
                if content:
                    links = content.find_all('a', href=True)
                    bid_links = [a for a in links if
                                 a['href'].endswith('.pdf') or
                                 'rfp' in a.get_text(strip=True).lower() or
                                 'bid' in a.get_text(strip=True).lower() or
                                 'solicitation' in a.get_text(strip=True).lower()]
                    for link in bid_links:
                        if self.reached_limit():
                            break
                        opp = self._parse_link(link)
                        if opp:
                            self.add_opportunity(opp)
                    if bid_links:
                        logger.info(f"  Found {len(bid_links)} bid links from ME BGS")

        except Exception as e:
            logger.error(f"Error scraping Maine BGS: {e}")

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
                    href = f"https://www.maine.gov{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            title = cell_texts[0] if cell_texts else None
            opp_number = cell_texts[1] if len(cell_texts) > 1 else None
            org = cell_texts[2] if len(cell_texts) > 2 else 'State of Maine'
            deadline_str = cell_texts[-1] if len(cell_texts) > 2 else None

            if not title or len(title) < 3:
                return None

            deadline = parse_date(deadline_str) if deadline_str else None
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': org if org else 'State of Maine',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Maine',
                'source': self.source_name,
                'source_url': detail_url or self.BIDS_URL,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing ME row: {e}")
            return None

    def _parse_link(self, link):
        try:
            title = clean_text(link.get_text(strip=True))
            if not title or len(title) < 5:
                return None
            href = link['href']
            if not href.startswith('http'):
                href = f"https://www.maine.gov{href}"

            doc_urls = [href] if href.endswith('.pdf') else []
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of Maine',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'Maine',
                'source': self.source_name,
                'source_url': href,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing ME link: {e}")
            return None


def get_maine_scrapers():
    return [MaineProcurementScraper()]


if __name__ == '__main__':
    scraper = MaineProcurementScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
