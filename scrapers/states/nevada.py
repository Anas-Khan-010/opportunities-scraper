"""
Nevada Procurement scraper — NevadaEPro (Periscope / BidSync)

Scrapes open bid opportunities from the NevadaEPro platform.
Uses Selenium to wait for Periscope's internal JS to load the table.

Source: https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class NevadaEProScraper(BaseScraper):
    """Scrapes bid opportunities from NevadaEPro (Periscope)."""

    SEARCH_URL = "https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true"
    BASE_URL = "https://nevadaepro.com"

    def __init__(self):
        super().__init__("NevadaEPro")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error(f"Selenium driver unavailable — skipping {self.source_name}")
            return self.opportunities

        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(5, 8))

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            results_div = soup.find('div', id=lambda x: x and 'results' in x.lower())
            if not results_div:
                results_div = soup

            table = results_div.find('table', id=lambda x: x and 'bidSearchResultsTable' in str(x))
            if not table:
                table = results_div.find('table', class_=lambda x: x and 'ui-datatable' in str(x))

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
        Parses a single row from the Periscope table.
        Columns typically:
        Bid Solicitation #, Organization Name, Blanket #, Buyer, Description,
        Bid Opening Date, Bid Holder List, Awarded Vendor(s), Status, Alternate Id
        """
        cells = row.find_all('td')
        if len(cells) < 5:
            return None

        try:
            cell_texts = [clean_text(c.get_text(separator=' ', strip=True)) for c in cells]
            
            def _extract_val(text, prefix):
                if text.lower().startswith(prefix.lower()):
                    return text[len(prefix):].strip()
                return text

            raw_opp_num = cell_texts[0] if len(cell_texts) > 0 else ''
            opp_number = _extract_val(raw_opp_num, 'Bid Solicitation #')
            
            raw_org = cell_texts[1] if len(cell_texts) > 1 else ''
            org = _extract_val(raw_org, 'Organization Name')
            
            raw_buyer = cell_texts[3] if len(cell_texts) > 3 else ''
            buyer = _extract_val(raw_buyer, 'Buyer')
            
            raw_desc = cell_texts[4] if len(cell_texts) > 4 else ''
            title = _extract_val(raw_desc, 'Description')
            
            raw_deadline = cell_texts[5] if len(cell_texts) > 5 else ''
            deadline_str = _extract_val(raw_deadline, 'Bid Opening Date')

            if not title or title == 'Description':
                title = opp_number
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
                
                if '/bso/external/bidDetail.sdo' in href:
                    detail_url = href
                elif href.endswith('.pdf'):
                    doc_urls.append(href)

            source_url = detail_url or self.SEARCH_URL
            category = categorize_opportunity(title, '')

            description = f"Buyer: {buyer}" if buyer else None

            return {
                'title': title,
                'organization': org or 'State of Nevada',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Nevada',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing Nevada row: {e}")
            return None


def get_nevada_scrapers():
    return [NevadaEProScraper()]


if __name__ == '__main__':
    scraper = NevadaEProScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
