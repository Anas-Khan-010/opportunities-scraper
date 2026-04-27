"""
Louisiana Procurement scraper — LaPAC (Louisiana Procurement and Contract Network)

Source: https://wwwprd.doa.louisiana.gov/osp/lapac/pubmain.asp
"""
import time, random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class LouisianaLaPACScraper(BaseScraper):
    SEARCH_URL = "https://wwwprd.doa.louisiana.gov/osp/lapac/pubmain.asp"
    
    def __init__(self):
        super().__init__("Louisiana LaPAC")
        
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        driver = SeleniumDriverManager.get_driver()
        if not driver: return self.opportunities
        
        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(5, 8))
            
            # Click "Search for Bids / RFPs" - this usually just goes to pubMain.asp which has the options
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # The site uses forms. We can just visit the department categories or search all.
            # Usually searching all open bids is easiest:
            all_bids_url = "https://wwwprd.doa.louisiana.gov/osp/lapac/pubMain.asp?S_Type=ALL"
            driver.get(all_bids_url)
            time.sleep(8)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            table = soup.find('table', class_='list')
            if not table:
                table = soup.find('table', attrs={'border': '1'})
                
            if table:
                rows = table.find_all('tr')[1:] # skip header
                for row in rows:
                    if self.reached_limit(): break
                    opp = self.parse_opportunity(row)
                    if opp: self.add_opportunity(opp)
        except Exception as e:
            logger.error(f"Error scraping Louisiana LaPAC: {e}")
            
        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 4: return None
        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]
            # LaPAC columns: Solicitation#, Description, Agency, Opening Date
            opp_number = cell_texts[0]
            title = cell_texts[1]
            org = cell_texts[2]
            deadline_str = cell_texts[3]
            
            if not title or len(title) < 5: return None
            
            links = row.find_all('a', href=True)
            url = links[0]['href'] if links else self.SEARCH_URL
            if not url.startswith('http'): url = f"https://wwwprd.doa.louisiana.gov/osp/lapac/{url}"
            
            deadline = parse_date(deadline_str) if deadline_str else None
            
            return {
                'title': title, 
                'organization': org or 'State of Louisiana',
                'description': None, 
                'eligibility': None, 
                'funding_amount': None,
                'deadline': deadline, 
                'category': categorize_opportunity(title, ''),
                'location': 'Louisiana', 
                'source': self.source_name,
                'source_url': url, 
                'opportunity_number': opp_number, 
                'posted_date': None,
                'document_urls': [], 
                'opportunity_type': 'bid',
            }
        except: return None

def get_louisiana_scrapers():
    return [LouisianaLaPACScraper()]
