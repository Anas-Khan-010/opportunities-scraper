import json
import re
import time
import random
import urllib.parse
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

from scrapers.states.florida_vip import get_florida_procurement_scrapers

class FloridaDOSGrantsScraper(BaseScraper):
    """Scrapes Grants from Florida Department of State Grants System (dosgrants.com)"""

    def __init__(self):
        super().__init__("Florida DOS Grants")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Target the Kendo UI grid data endpoint directly or parse the inline JSON
        url = "https://dosgrants.com/Program"
        
        response = self.fetch_page(url)
        if not response:
            logger.error("Failed to load Florida DOS Grants page")
            return self.opportunities
            
        soup = self.parse_html(response.text)
        
        # Extract the JSON data from the inline script for the Kendo Grid
        script_tags = soup.find_all('script')
        grid_data = None
        
        for script in script_tags:
            content = script.string
            if content and 'kendoGrid(' in content and 'dataSource' in content:
                # Try to extract the JSON payload containing the programs
                match = re.search(r'"data":\{"Data":\[(.*?)\],"Total"', content)
                if match:
                    try:
                        # Extract the inner items array
                        full_json_str = '{"Data":[' + match.group(1) + ']}'
                        data_obj = json.loads(full_json_str)
                        grid_data = data_obj.get('Data', [])
                        break
                    except Exception as e:
                        logger.error(f"Error parsing JSON from Florida DOS script: {e}")
        
        if grid_data:
            for group in grid_data:
                for item in group.get('Items', []):
                    if self.reached_limit():
                        return self.opportunities
                        
                    opp = self.parse_opportunity(item)
                    if opp:
                        self.add_opportunity(opp)
        else:
            logger.warning("Could not find grant data inside page scripts.")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, item):
        # Kendo Grid JSON ships an integer "Id", not "Guid". Falling back to a
        # generic URL collapses every record onto the same source_url and the
        # ON CONFLICT upsert ends up persisting only one row per run.
        program_id = item.get('Id') or item.get('Guid')
        title = item.get('Name')
        if not title:
            return None

        program_code = item.get('ProgramCode')
        if program_id is not None:
            detail_url = f"https://dosgrants.com/Program/Details/{program_id}"
        elif program_code:
            detail_url = f"https://dosgrants.com/Program/Details/{program_code}"
        else:
            detail_url = "https://dosgrants.com/Program"
        
        description_raw = item.get('PD', '')
        description = clean_text(re.sub(r'<[^>]+>', ' ', description_raw))
        
        division = item.get('Division', 'Florida Department of State')
        org = f"{division}".strip() if division else "Florida Department of State"
        
        deadline_str = item.get('ApplicationPeriod', '')
        deadline = None
        if deadline_str and '-' in deadline_str:
            end_date_str = deadline_str.split('-')[1].strip()
            deadline = parse_date(end_date_str)
            
        # --- Deep Enrichment from Detail Page ---
        eligibility = None
        doc_urls = []
        try:
            driver = SeleniumDriverManager.get_driver()
            if driver:
                driver.get(detail_url)
                time.sleep(random.uniform(2, 4))
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Look for attachments/docs
                for a in soup.find_all('a', href=True):
                    if a['href'].lower().endswith('.pdf'):
                        doc_urls.append(urllib.parse.urljoin(detail_url, a['href']))
                
                # Look for eligibility section
                elig_header = soup.find(lambda t: t.name in ['h2', 'h3', 'h4', 'strong'] and 'Eligibility' in t.text)
                if elig_header:
                    para = elig_header.find_next('p')
                    if para:
                        eligibility = clean_text(para.get_text())
        except Exception as e:
            logger.debug(f"Florida: could not enrich {title}: {e}")

        category = categorize_opportunity(title, description)
        
        return {
            'title': title,
            'organization': org,
            'description': description,
            'eligibility': eligibility,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': 'Florida',
            'source': self.source_name,
            'source_url': detail_url,
            'opportunity_number': item.get('ProgramCode'),
            'posted_date': None,
            'document_urls': list(set(doc_urls)),
            'opportunity_type': 'grant',
        }

def get_florida_scrapers():
    """Return all Florida scrapers (Grants + Procurement)."""
    scrapers = [FloridaDOSGrantsScraper()]
    scrapers.extend(get_florida_procurement_scrapers())
    return scrapers

if __name__ == '__main__':
    scraper = FloridaDOSGrantsScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    pprint.pprint(opps[:2])
