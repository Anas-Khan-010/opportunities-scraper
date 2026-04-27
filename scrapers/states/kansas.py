"""
Kansas Procurement scraper — Bid Solicitations (eSupplier PeopleSoft)

Source: https://admin.ks.gov/offices/procurement-and-contracts/bid-solicitations
"""
import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, categorize_opportunity

class KansasProcurementScraper(BaseScraper):
    SEARCH_URL = "https://admin.ks.gov/offices/procurement-and-contracts/bid-solicitations"
    def __init__(self):
        super().__init__("Kansas Procurement")
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        driver = SeleniumDriverManager.get_driver()
        if not driver: return self.opportunities
        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(6, 10))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            table = soup.find('table')
            if table:
                for row in table.find_all('tr'):
                    if self.reached_limit(): break
                    opp = self.parse_opportunity(row)
                    if opp: self.add_opportunity(opp)
        except Exception as e:
            logger.warning(f"Error scraping Kansas: {e}")
        self.log_summary()
        return self.opportunities
    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 2: return None
        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]
            title = max(cell_texts, key=len)
            if not title or len(title) < 5: return None
            links = row.find_all('a', href=True)
            url = links[0]['href'] if links else self.SEARCH_URL
            if not url.startswith('http'): url = f"https://admin.ks.gov{url}"
            return {
                'title': title, 'organization': 'State of Kansas',
                'description': None, 'eligibility': None, 'funding_amount': None,
                'deadline': None, 'category': categorize_opportunity(title, ''),
                'location': 'Kansas', 'source': self.source_name,
                'source_url': url, 'opportunity_number': None, 'posted_date': None,
                'document_urls': [], 'opportunity_type': 'bid',
            }
        except: return None

def get_kansas_scrapers():
    return [KansasProcurementScraper()]
