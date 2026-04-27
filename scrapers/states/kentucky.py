"""
Kentucky Procurement scraper — Finance Cabinet Procurement

Source: https://finance.ky.gov/offices/procurement/Pages/default.aspx
Listing: https://emars311.ky.gov/webapp/vssps2/AltSelfService
"""
import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class KentuckyProcurementScraper(BaseScraper):
    # This URL often redirects to the VSS portal. 
    SEARCH_URLS = [
        "https://finance.ky.gov/offices/procurement/Pages/default.aspx",
        "https://emars311.ky.gov/webapp/vssps2/AltSelfService"
    ]
    
    def __init__(self):
        super().__init__("Kentucky Procurement")
        
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver: return self.opportunities
        
        for url in self.SEARCH_URLS:
            try:
                driver.get(url)
                time.sleep(random.uniform(8, 12))
                
                # Check if we are on the VSS Guest Access page
                if "Guest Access" in driver.page_source:
                    try:
                        guest_btn = driver.find_element("link text", "Guest Access")
                        guest_btn.click()
                        time.sleep(10)
                    except: pass
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                table = soup.find('table', class_=lambda x: x and ('grid' in str(x).lower() or 'list' in str(x).lower()))
                if not table: table = soup.find('table')
                
                if table:
                    rows = table.find_all('tr')
                    for row in rows:
                        if self.reached_limit(): break
                        opp = self.parse_opportunity(row)
                        if opp: self.add_opportunity(opp)
                    if self.opportunities: break
            except Exception as e:
                logger.warning(f"Error scraping Kentucky at {url}: {e}")
                
        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 4: return None
        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]
            
            # Standard VSS columns: Solicitation#, Type, Title, Issued, Closing
            opp_number = cell_texts[0]
            title = cell_texts[2]
            issued_str = cell_texts[3]
            deadline_str = cell_texts[4] if len(cell_texts) > 4 else None
            
            if not title or len(title) < 5: return None
            
            links = row.find_all('a', href=True)
            url = links[0]['href'] if links else self.SEARCH_URLS[0]
            if not url.startswith('http'): url = f"https://emars311.ky.gov{url}"
            
            posted_date = parse_date(issued_str) if issued_str else None
            deadline = parse_date(deadline_str) if deadline_str else None
            
            return {
                'title': title, 
                'organization': 'Commonwealth of Kentucky',
                'description': None, 
                'eligibility': None, 
                'funding_amount': None,
                'deadline': deadline, 
                'category': categorize_opportunity(title, ''),
                'location': 'Kentucky', 
                'source': self.source_name,
                'source_url': url, 
                'opportunity_number': opp_number, 
                'posted_date': posted_date,
                'document_urls': [], 
                'opportunity_type': 'bid',
            }
        except: return None

def get_kentucky_scrapers():
    return [KentuckyProcurementScraper()]
