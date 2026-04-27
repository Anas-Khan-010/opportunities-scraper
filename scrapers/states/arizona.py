import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class ArizonaProcurementPortalScraper(BaseScraper):
    """Scrapes RFPs and Bids from the Arizona Procurement Portal (APP) — Ivalua Platform."""

    SEARCH_URL = "https://app.az.gov/page.aspx/en/rfp/request_browse_public"

    def __init__(self):
        super().__init__("Arizona Procurement Portal")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Arizona uses Ivalua. We use residential proxy for reliability.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Arizona")
            return self.opportunities
        
        try:
            driver.get(self.SEARCH_URL)
            # Wait for the Ivalua grid to load
            time.sleep(random.uniform(8, 12))
            
            # Handle potential Cloudflare challenge
            if "Just a moment" in driver.page_source:
                time.sleep(10)
            
            self._scrape_ivalua(driver)
                    
        except Exception as e:
            logger.error(f"Error scraping Arizona: {e}")
            
        self.log_summary()
        return self.opportunities

    def _scrape_ivalua(self, driver):
        """Parse Arizona APP Ivalua grid blocks."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Ivalua Grid Selectors
        rows = soup.select('tr[id*="grd"], .iv-grid-row, tr[class*="grid-row"]')
        if not rows:
            table = soup.find('table', id=lambda x: x and 'grd' in x)
            rows = table.find_all('tr')[1:] if table else []

        for row in rows:
            if self.reached_limit(): break
            cells = row.find_all('td')
            if len(cells) < 6: continue
            
            try:
                # APP Ivalua Columns: Code, Title, Fam, Agency, status, end
                opp_num = clean_text(cells[1].get_text(strip=True))
                title = clean_text(cells[2].get_text(strip=True))
                rfx_type = clean_text(cells[4].get_text(strip=True))
                org = clean_text(cells[5].get_text(strip=True))
                deadline_str = clean_text(cells[11].get_text(strip=True)) if len(cells) > 11 else None

                if not title or len(title) < 5: continue

                self.add_opportunity({
                    'title': title,
                    'organization': org or "State of Arizona",
                    'description': f"RFx Type: {rfx_type}",
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, rfx_type),
                    'location': 'Arizona',
                    'source': self.source_name,
                    'source_url': f"{self.SEARCH_URL}?rfp={opp_num}",
                    'opportunity_number': opp_num,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'rfp' if 'rfp' in rfx_type.lower() else 'bid',
                })
            except: continue

def get_arizona_scrapers():
    return [ArizonaProcurementPortalScraper()]

def get_arizona_scrapers():
    return [ArizonaProcurementPortalScraper()]

if __name__ == '__main__':
    scraper = ArizonaProcurementPortalScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    pprint.pprint(opps[:2])
