import os
from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class SAMGovScraper(BaseScraper):
    """Scraper for SAM.gov - Federal contract opportunities and RFPs"""
    
    def __init__(self):
        super().__init__('SAM.gov')
        self.base_url = 'https://sam.gov'
        self.api_url = 'https://api.sam.gov/opportunities/v2/search'
        self.api_key = os.getenv('SAM_GOV_API_KEY')
    
    def scrape(self, max_pages=5):
        """Scrape contract opportunities from SAM.gov"""
        logger.info(f"Starting {self.source_name} scraper...")
        
        if not self.api_key:
            logger.warning("SAM.gov API key not configured. Get free key at https://sam.gov/data-services/")
            logger.warning("Add SAM_GOV_API_KEY to .env file to enable this scraper")
            return self.opportunities
        
        for page in range(max_pages):
            try:
                params = {
                    'api_key': self.api_key,
                    'limit': 100,
                    'offset': page * 100,
                    'postedFrom': '01/01/2024',
                    'postedTo': '12/31/2026'
                }
                
                response = self.fetch_page(self.api_url, params=params)
                if not response:
                    continue
                
                data = response.json()
                
                if 'opportunitiesData' not in data or not data['opportunitiesData']:
                    logger.info(f"No more opportunities found on page {page + 1}")
                    break
                
                for opp in data['opportunitiesData']:
                    opportunity = self.parse_opportunity(opp)
                    if opportunity:
                        self.opportunities.append(opportunity)
                
                logger.info(f"Processed page {page + 1}, total opportunities: {len(self.opportunities)}")
                
            except Exception as e:
                logger.error(f"Error scraping page {page + 1}: {e}")
                continue
        
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, opp_data):
        """Parse individual contract opportunity"""
        try:
            title = clean_text(opp_data.get('title', ''))
            opportunity_number = opp_data.get('noticeId', '')
            source_url = f"{self.base_url}/opp/{opportunity_number}/view"
            
            # Parse dates
            posted_date = parse_date(opp_data.get('postedDate'))
            deadline = parse_date(opp_data.get('responseDeadLine'))
            
            # Get organization
            organization = clean_text(opp_data.get('department', ''))
            if 'subtier' in opp_data:
                organization += f" - {clean_text(opp_data['subtier'])}"
            
            # Get description
            description = clean_text(opp_data.get('description', ''))
            
            # Category
            category = opp_data.get('type', 'Contract')
            
            # Location
            location = clean_text(opp_data.get('placeOfPerformance', {}).get('city', {}).get('name', 'United States'))
            
            opportunity = {
                'title': title,
                'organization': organization,
                'description': description,
                'eligibility': clean_text(opp_data.get('typeOfSetAside', '')),
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opportunity_number,
                'posted_date': posted_date,
                'document_urls': [],
                'full_document': None
            }
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error parsing opportunity: {e}")
            return None
