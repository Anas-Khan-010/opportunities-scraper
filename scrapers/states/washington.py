"""
Washington Procurement scraper — DES Contracts & Purchasing

Source: https://des.wa.gov/services/contracting-purchasing
"""

import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class WashingtonProcurementScraper(BaseScraper):
    """
    Washington Procurement scraper — WEBS (Official) & DES Services.
    
    Target 1: https://pr-webs-vendor.des.wa.gov/ (Official WEBS Portal)
    Target 2: https://des.wa.gov/services/contracting-purchasing (DES Listings)
    """
    
    SEARCH_URLS = [
        "https://pr-webs-vendor.des.wa.gov/",
        "https://des.wa.gov/services/contracting-purchasing",
    ]

    def __init__(self):
        super().__init__("Washington Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Washington WEBS is behind an aggressive firewall. MUST use residential proxy.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Washington")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "pr-webs-vendor" in url:
                    self._scrape_webs(driver)
                else:
                    self._scrape_des(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Washington at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_webs(self, driver):
        """Parse Washington WEBS public solicitation list."""
        try:
            # WEBS usually has a 'Public Solicitations' link
            links = driver.find_elements_by_tag_name('a')
            for link in links:
                if 'public' in link.text.lower() and 'solicitation' in link.text.lower():
                    link.click()
                    time.sleep(8)
                    break
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # WEBS uses a standard data grid
            rows = soup.select('tr[class*="row"], tr[id*="row"]')
            if not rows:
                rows = soup.find_all('tr')[1:]

            for row in rows:
                if self.reached_limit(): break
                cells = row.find_all('td')
                if len(cells) < 4: continue

                try:
                    # WEBS Columns: RFX #, Title, Agency, Date
                    opp_num = clean_text(cells[0].get_text(strip=True))
                    title = clean_text(cells[1].get_text(strip=True))
                    org = clean_text(cells[2].get_text(strip=True))
                    deadline_str = clean_text(cells[3].get_text(strip=True))

                    if not title or len(title) < 5: continue

                    self.add_opportunity({
                        'title': title,
                        'organization': org or 'State of Washington',
                        'description': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'Washington',
                        'source': self.source_name,
                        'source_url': self.SEARCH_URLS[0],
                        'opportunity_number': opp_num,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except: continue
        except Exception as e:
            logger.warning(f"WEBS parse failure: {e}")

    def _scrape_des(self, driver):
        """Legacy DES link-based parser."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            if self.reached_limit(): break
            text = clean_text(link.get_text(strip=True))
            href = link['href']
            if not href.startswith('http'): href = f"https://des.wa.gov{href}"
            
            if len(text) > 10 and (href.endswith('.pdf') or 'bid' in text.lower() or 'rfp' in text.lower()):
                self.add_opportunity({
                    'title': text,
                    'organization': 'State of Washington',
                    'description': None,
                    'deadline': None,
                    'category': categorize_opportunity(text, ""),
                    'location': 'Washington',
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [href] if href.endswith('.pdf') else [],
                    'opportunity_type': 'bid',
                })

def get_washington_scrapers():
    return [WashingtonProcurementScraper()]

def get_washington_scrapers():
    return [WashingtonProcurementScraper()]
