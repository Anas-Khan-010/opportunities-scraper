"""
Arkansas Procurement scraper — ARBuy / OSP Current Bids

Source: https://www.arkansas.gov/arbuy/
"""
import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, categorize_opportunity

class ArkansasProcurementScraper(BaseScraper):
    """
    Arkansas Procurement scraper — ARBuy (Official Ivalua Portal).
    
    Target: https://arbuy.arkansas.gov/ (Official State Registry)
    """
    
    SEARCH_URLS = [
        "https://arbuy.arkansas.gov/",
        "https://arbuy.arkansas.gov/page.aspx/en/rfp/request_browse_public", # Direct Search link
    ]

    def __init__(self):
        super().__init__("Arkansas ARBuy Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Arkansas uses Ivalua with Cloudflare protection. MUST use residential proxy.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Arkansas")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "Just a moment" in driver.page_source:
                    logger.info("  Bypassing Cloudflare/Imperva challenge...")
                    time.sleep(10)

                self._scrape_ivalua(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Arkansas at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_ivalua(self, driver):
        """Parse ARBuy Ivalua grid blocks."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Ivalua Grid Selectors
        rows = soup.select('tr[class*="grid-row"], .iv-grid-row')
        if not rows:
            rows = soup.find_all('tr')[1:] # Skip header if classes missing

        for row in rows:
            if self.reached_limit(): break
            cells = row.find_all('td')
            if len(cells) < 3: continue

            try:
                # Ivalua Columns: ID, Title, Org, Closing Date
                opp_id = clean_text(cells[0].get_text(strip=True))
                title = clean_text(cells[1].get_text(strip=True))
                org = clean_text(cells[2].get_text(strip=True))
                deadline_str = clean_text(cells[3].get_text(strip=True)) if len(cells) > 3 else None

                if not title or len(title) < 5: continue

                link = row.find('a', href=True)
                source_url = self.SEARCH_URLS[0]
                if link:
                    href = link['href']
                    source_url = f"https://arbuy.arkansas.gov{href}" if not href.startswith('http') else href

                self.add_opportunity({
                    'title': title,
                    'organization': org or 'State of Arkansas',
                    'description': None,
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, ''),
                    'location': 'Arkansas',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_id,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except: continue

def get_arkansas_scrapers():
    return [ArkansasProcurementScraper()]

def get_arkansas_scrapers():
    return [ArkansasProcurementScraper()]
