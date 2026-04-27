"""
Nebraska Procurement scraper — DAS Purchasing Bids

Scrapes open bid/solicitation opportunities from Nebraska's DAS
Material Division purchasing page.

Source: https://das.nebraska.gov/materiel/purchasing/bidw.html
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class NebraskaPurchasingScraper(BaseScraper):
    """Scrapes bid opportunities from Nebraska DAS Purchasing."""

    BIDS_URL = "https://das.nebraska.gov/materiel/purchasing/bidw.html"

    def __init__(self):
        super().__init__("Nebraska DAS Purchasing")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for Nebraska scraper")
                return self.opportunities

            driver.get(self.BIDS_URL)
            time.sleep(6)

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Nebraska page uses a simple HTML table for bids
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                # Check if this looks like a bid table
                header = rows[0]
                header_text = header.get_text(strip=True).lower()
                if not any(kw in header_text for kw in ['bid', 'rfp', 'solicitation', 'title', 'description', 'number', 'open']):
                    continue

                data_rows = rows[1:]
                for row in data_rows:
                    if self.reached_limit():
                        break
                    opp = self.parse_opportunity(row)
                    if opp:
                        self.add_opportunity(opp)

                logger.info(f"  Parsed {len(data_rows)} rows from NE DAS")
                break  # Only process the first matching table

        except Exception as e:
            logger.error(f"Error scraping Nebraska DAS: {e}")

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
                    href = f"https://das.nebraska.gov{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            # NE format: Bid Number, Title/Description, Agency, Opening Date
            opp_number = cell_texts[0] if len(cell_texts) > 0 else None
            title = cell_texts[1] if len(cell_texts) > 1 else cell_texts[0]
            org = cell_texts[2] if len(cell_texts) > 2 else 'State of Nebraska'
            deadline_str = cell_texts[3] if len(cell_texts) > 3 else None

            if not title or len(title) < 3:
                return None

            deadline = parse_date(deadline_str) if deadline_str else None
            source_url = detail_url or self.BIDS_URL
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': org if org else 'State of Nebraska',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Nebraska',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing NE row: {e}")
            return None


def get_nebraska_scrapers():
    return [NebraskaPurchasingScraper()]


if __name__ == '__main__':
    scraper = NebraskaPurchasingScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
