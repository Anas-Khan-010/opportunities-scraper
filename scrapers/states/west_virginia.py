"""
West Virginia Procurement scraper— WV Purchasing Division Bids

Scrapes open bid opportunities from West Virginia's Purchasing
Division bid page.  The page is organized as a calendar/date-based
layout with links to individual bid documents (PDFs).

Source: https://www.state.wv.us/admin/purchase/Bids/
"""

import time
import re
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class WestVirginiaProcurementScraper(BaseScraper):
    """
    West Virginia Procurement scraper — wvOASIS (Official) & Purchasing Division.
    
    Target 1: https://vss.wvoasis.gov/ (Official CGI Advantage VSS)
    Target 2: https://www.state.wv.us/admin/purchase/Bids/ (Legacy Listing)
    """
    
    SEARCH_URLS = [
        "https://vss.wvoasis.gov/",
        "https://www.state.wv.us/admin/purchase/Bids/",
    ]

    def __init__(self):
        super().__init__("West Virginia Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping West Virginia")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "wvoasis.gov" in url:
                    self._scrape_vss(driver)
                else:
                    self._scrape_legacy(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping West Virginia at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_vss(self, driver):
        """Parse wvOASIS CGI Advantage VSS grid."""
        try:
            # CGI VSS usually requires clicking 'View Published Solicitations'
            links = driver.find_elements_by_tag_name('a')
            for link in links:
                if 'published' in link.text.lower() or 'solicitation' in link.text.lower():
                    link.click()
                    time.sleep(5)
                    break
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('tr[id*="row"], tr[class*="grid-row"]')
            if not rows:
                rows = soup.find_all('tr')[5:] # Generic fallback

            for row in rows:
                if self.reached_limit(): break
                cells = row.find_all('td')
                if len(cells) < 4: continue

                try:
                    # VSS Columns: ID, Title, Dept, Date
                    id_txt = clean_text(cells[0].get_text(strip=True))
                    title = clean_text(cells[1].get_text(strip=True))
                    dept = clean_text(cells[2].get_text(strip=True))
                    deadline_str = clean_text(cells[-1].get_text(strip=True))

                    if not title or len(title) < 5: continue

                    self.add_opportunity({
                        'title': title,
                        'organization': dept or 'State of West Virginia',
                        'description': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'West Virginia',
                        'source': self.source_name,
                        'source_url': self.SEARCH_URLS[0],
                        'opportunity_number': id_txt,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except: continue
        except Exception as e:
            logger.warning(f"WV VSS parse failure: {e}")

    def _scrape_legacy(self, driver):
        """Standard link-based parser for legacy WV page."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            if self.reached_limit(): break
            text = clean_text(link.get_text(strip=True))
            href = link['href']
            if not href.startswith('http'): href = f"https://www.state.wv.us/admin/purchase/Bids/{href}"
            
            if len(text) > 10 and (href.endswith('.pdf') or href.endswith('.htm')):
                self.add_opportunity({
                    'title': text,
                    'organization': 'State of West Virginia',
                    'description': None,
                    'deadline': None,
                    'category': categorize_opportunity(text, ""),
                    'location': 'West Virginia',
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [href] if href.endswith('.pdf') else [],
                    'opportunity_type': 'bid',
                })

def get_west_virginia_scrapers():
    return [WestVirginiaProcurementScraper()]


def get_west_virginia_scrapers():
    return [WestVirginiaPurchasingScraper()]


if __name__ == '__main__':
    scraper = WestVirginiaPurchasingScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
