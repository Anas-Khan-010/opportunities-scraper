"""
Mississippi Procurement scraper — DFA Contract/Bid Search

Scrapes open bid opportunities from Mississippi's official
procurement portal.  Uses Selenium to click the search button
(required to populate results) and then parses the DataTables
result table.

Source: https://www.ms.gov/dfa/contract_bid_search/Bid
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class MississippiBidScraper(BaseScraper):
    """Scrapes bid opportunities from Mississippi DFA portal."""

    SEARCH_URL = "https://www.ms.gov/dfa/contract_bid_search/Bid"

    def __init__(self):
        super().__init__("Mississippi DFA Bids")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for Mississippi scraper")
                return self.opportunities

            driver.get(self.SEARCH_URL)
            time.sleep(5)

            # Must click "SEARCH" button (id=btnSearch) to populate the DataTable
            try:
                search_btn = driver.find_element("id", "btnSearch")
                search_btn.click()
                time.sleep(10) # Wait for AJAX population
                
                # Verify if data loaded
                if "No data available in table" in driver.page_source:
                    logger.warning("Mississippi DFA: Table says no data after search.")
            except Exception as e:
                logger.warning(f"Could not click search button: {e}")
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # The results table uses DataTables; look for the data table
            table = soup.find('table', class_='dataTable') or soup.find('table', id=lambda x: x and 'DataTable' in str(x))
            if not table:
                # DataTables often doesn't set a unique ID; find table with bid-like headers
                for t in soup.find_all('table'):
                    header_text = t.get_text(strip=True).lower()
                    if any(kw in header_text for kw in ['rfx', 'smart number', 'agency', 'description', 'submission']):
                        table = t
                        break

            if not table:
                logger.warning("No bid data table found on Mississippi portal")
                self.log_summary()
                return self.opportunities

            rows = table.find_all('tr')
            data_rows = rows[1:]  # skip header

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    self.add_opportunity(opp)

            logger.info(f"  Parsed {len(data_rows)} rows from MS DFA")

        except Exception as e:
            logger.error(f"Error scraping Mississippi DFA: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 5:
            return None

        try:
            # Columns: Agency, Smart Number, RFx Number, Description (contains links), Status,
            #          Advertised Date, Submission Date, RFx Opening Date, View Contact
            agency = clean_text(cells[0].get_text(strip=True))
            smart_number = clean_text(cells[1].get_text(strip=True))
            rfx_number = clean_text(cells[2].get_text(strip=True))
            
            # The description cell often contains the title AND attachment links.
            # We want to extract the links and the clean text separately.
            desc_cell = cells[3]
            
            # Extract document links from this specific cell
            doc_urls = []
            for a in desc_cell.find_all('a', href=True):
                href = a['href']
                if not href.startswith('http'):
                    href = f"https://www.ms.gov{href}"
                doc_urls.append(href)
                # Remove the link from the cell before getting text to avoid smushing
                a.decompose()
                
            description = clean_text(desc_cell.get_text(separator=' ', strip=True))
            
            status = clean_text(cells[4].get_text(strip=True)) if len(cells) > 4 else ''
            advertised_date_str = clean_text(cells[5].get_text(strip=True)) if len(cells) > 5 else ''
            submission_date_str = clean_text(cells[6].get_text(strip=True)) if len(cells) > 6 else ''
            opening_date_str = clean_text(cells[7].get_text(strip=True)) if len(cells) > 7 else ''

            # Use description as title
            title = description if description else smart_number
            if not title or title.lower() == 'no data available in table':
                return None

            # Find detail link
            links = row.find_all('a', href=True)
            detail_url = None
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"https://www.ms.gov{href}"
                if '/Bid/Details/' in href or '/Detail' in href:
                    detail_url = href
                elif not detail_url and '/dfa/' in href:
                    detail_url = href

            source_url = detail_url or self.SEARCH_URL
            opp_number = smart_number or rfx_number
            category = categorize_opportunity(title, description)
            
            # Parse dates
            deadline = parse_date(submission_date_str) if submission_date_str else None
            posted_date = parse_date(advertised_date_str) if advertised_date_str else None

            return {
                'title': title,
                'organization': f"Mississippi - {agency}" if agency else 'State of Mississippi',
                'description': f"RFx #: {rfx_number}. Status: {status}." if rfx_number else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Mississippi',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': posted_date,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing MS row: {e}")
            return None


def get_mississippi_scrapers():
    return [MississippiBidScraper()]


if __name__ == '__main__':
    scraper = MississippiBidScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
