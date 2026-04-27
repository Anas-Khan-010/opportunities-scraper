"""
Colorado Procurement scraper — BidNet Direct

Scrapes open bid/RFP opportunities from Colorado's public
procurement listings on BidNet Direct.

Source: https://www.bidnetdirect.com/colorado
"""

import re
import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class ColoradoProcurementScraper(BaseScraper):
    """
    Colorado Procurement scraper — Colorado VSS (Official) & BidNet Direct.
    
    Target 1: https://vss.state.co.us/ (Official CGI Advantage VSS)
    Target 2: https://www.bidnetdirect.com/colorado (Official Regional Partner)
    """
    
    SEARCH_URLS = [
        "https://vss.state.co.us/",
        "https://www.bidnetdirect.com/colorado",
    ]

    def __init__(self):
        super().__init__("Colorado Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Colorado")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "vss.state.co.us" in url:
                    self._scrape_vss(driver)
                else:
                    self._scrape_bidnet(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Colorado at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_vss(self, driver):
        """Parse Colorado VSS CGI Advantage grid."""
        try:
            # CGI VSS usually requires clicking 'Public Access' or 'Solicitations'
            # Look for a link containing 'Solicitation' or 'Public Access'
            links = driver.find_elements_by_tag_name('a')
            for link in links:
                if 'solicitation' in link.text.lower() or 'published' in link.text.lower():
                    link.click()
                    time.sleep(5)
                    break
            
            # Wait for grid to load
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('tr[id*="row"], tr[class*="grid-row"]')
            if not rows:
                rows = soup.find_all('tr')[5:] # Skip top navigation rows

            for row in rows:
                if self.reached_limit(): break
                cells = row.find_all('td')
                if len(cells) < 4: continue

                try:
                    # VSS Columns: ID, Title, Dept, Type, Date
                    id_txt = clean_text(cells[0].get_text(strip=True))
                    title = clean_text(cells[1].get_text(strip=True))
                    dept = clean_text(cells[2].get_text(strip=True))
                    deadline_str = clean_text(cells[-1].get_text(strip=True))

                    if not title or len(title) < 5: continue

                    self.add_opportunity({
                        'title': title,
                        'organization': dept or 'State of Colorado',
                        'description': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'Colorado',
                        'source': self.source_name,
                        'source_url': self.SEARCH_URLS[0],
                        'opportunity_number': id_txt,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except: continue
        except Exception as e:
            logger.warning(f"VSS parse failure: {e}")

    def _scrape_bidnet(self, driver):
        """Legacy BidNet parser integration."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        cards = soup.select('div[class*="solicitation"], .bid-card')
        for card in cards:
            if self.reached_limit(): break
            try:
                title_el = card.find(['a', 'h3'])
                title = clean_text(title_el.get_text(strip=True)) if title_el else None
                if not title: continue
                
                href = title_el.get('href', self.SEARCH_URLS[1])
                if not href.startswith('http'): href = f"https://www.bidnetdirect.com{href}"

                self.add_opportunity({
                    'title': title,
                    'organization': 'State of Colorado',
                    'description': None,
                    'deadline': None,
                    'category': categorize_opportunity(title, ""),
                    'location': 'Colorado',
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except: continue

def get_colorado_scrapers():
    return [ColoradoProcurementScraper()]


def get_colorado_scrapers():
    return [ColoradoBidNetScraper()]
