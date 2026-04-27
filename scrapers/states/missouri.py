"""
Missouri Procurement scraper — MissouriBUYS / OA Purchasing

Source: https://oa.mo.gov/purchasing/vendor-information/current-bid-opportunities
"""
import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, categorize_opportunity

class MissouriProcurementScraper(BaseScraper):
    """
    Missouri Procurement scraper — MissouriBUYS (Ivalua) & Official Bid Locator.
    
    Target 1: https://missouribuys.mo.gov/bidboard (Official Ivalua Portal)
    Target 2: https://www.instantmarkets.com/q/missouri_state (Official Referral)
    """
    
    SEARCH_URLS = [
        "https://missouribuys.mo.gov/bidboard",
        "https://www.instantmarkets.com/q/missouri_state",
    ]

    def __init__(self):
        super().__init__("Missouri Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Missouri has a strict WAF (Imperva). We MUST route via proxy for the .gov site.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Missouri")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                # Handle Ivalua Grid (MissouriBUYS)
                if "missouribuys.mo.gov" in url:
                    self._scrape_ivalua(driver)
                else:
                    # Handle InstantMarkets (Official Referral)
                    self._scrape_simple_table(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Missouri at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_ivalua(self, driver):
        """Parse MissouriBUYS Ivalua grid blocks."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Ivalua usually renders results in a grid/table with specific classes
        rows = soup.select('tr[class*="grid-row"], .iv-grid-row')
        if not rows:
            # Fallback for dynamic tables
            rows = soup.find_all('tr')

        for row in rows:
            if self.reached_limit(): break
            cells = row.find_all('td')
            if len(cells) < 3: continue

            try:
                # Ivalua fields: ID, Title, Org, Date
                opp_id = clean_text(cells[0].get_text(strip=True))
                title = clean_text(cells[1].get_text(strip=True))
                org = clean_text(cells[2].get_text(strip=True))
                deadline_str = clean_text(cells[3].get_text(strip=True)) if len(cells) > 3 else None

                if not title or len(title) < 5: continue

                links = row.find_all('a', href=True)
                source_url = self.SEARCH_URLS[0]
                if links:
                    source_url = links[0]['href']
                    if not source_url.startswith('http'):
                        source_url = f"https://missouribuys.mo.gov{source_url}" if '/bidboard/' in source_url else f"https://missouribuys.mo.gov/bidboard"

                self.add_opportunity({
                    'title': title,
                    'organization': org or 'State of Missouri',
                    'description': None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, ''),
                    'location': 'Missouri',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_id,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except: continue

    def _scrape_simple_table(self, driver):
        """Parse standard table/list layout for referrals."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        items = soup.find_all(['tr', 'div'], class_=lambda x: x and ('bid' in x.lower() or 'item' in x.lower()))
        if not items:
            items = soup.find_all('tr')[1:] # Skip header

        for item in items:
            if self.reached_limit(): break
            try:
                text = clean_text(item.get_text(separator=' ', strip=True))
                if len(text) < 10: continue

                link = item.find('a', href=True)
                if not link: continue
                
                title = clean_text(link.get_text(strip=True))
                if not title: title = text.split('\n')[0][:100]

                href = link['href']
                if not href.startswith('http'): href = f"https://www.instantmarkets.com{href}"

                self.add_opportunity({
                    'title': title, 'organization': 'State of Missouri',
                    'description': text[:500], 'deadline': None,
                    'category': categorize_opportunity(title, text),
                    'location': 'Missouri', 'source': self.source_name,
                    'source_url': href, 'opportunity_number': None,
                    'posted_date': None, 'document_urls': [], 'opportunity_type': 'bid',
                })
            except: continue

def get_missouri_scrapers():
    return [MissouriProcurementScraper()]

def get_missouri_scrapers():
    return [MissouriProcurementScraper()]
