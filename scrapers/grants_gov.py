import json
from datetime import datetime
from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class GrantsGovScraper(BaseScraper):
    """Scraper for Grants.gov - Federal grant opportunities"""
    
    def __init__(self):
        super().__init__('Grants.gov')
        self.base_url = 'https://www.grants.gov'
        self.search_url = f'{self.base_url}/search-results-detail'
        self.api_url = 'https://www.grants.gov/grantsws/rest/opportunities/search'
    
    def scrape(self, max_pages=5):
        """Scrape grant opportunities from Grants.gov"""
        logger.info(f"Starting {self.source_name} scraper...")
        
        for page in range(max_pages):
            try:
                # Grants.gov has a REST API we can use
                params = {
                    'startRecordNum': page * 25,
                    'oppStatuses': 'forecasted|posted',
                    'sortBy': 'openDate|desc'
                }
                
                response = self.fetch_page(self.api_url, params=params)
                if not response:
                    continue
                
                data = response.json()
                
                if 'oppHits' not in data or not data['oppHits']:
                    logger.info(f"No more opportunities found on page {page + 1}")
                    break
                
                for opp in data['oppHits']:
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
        """Parse individual grant opportunity from API response"""
        try:
            title = clean_text(opp_data.get('title', ''))
            opportunity_number = opp_data.get('number', '')
            source_url = f"{self.base_url}/search-results-detail/{opp_data.get('id', '')}"
            
            # Parse dates
            posted_date = parse_date(opp_data.get('openDate'))
            deadline = parse_date(opp_data.get('closeDate'))
            
            # Get agency info
            agency = clean_text(opp_data.get('agency', ''))
            
            # Get description
            description = clean_text(opp_data.get('description', ''))
            
            # Extract funding amount if available
            funding_amount = None
            if 'awardCeiling' in opp_data and opp_data['awardCeiling']:
                funding_amount = f"${opp_data['awardCeiling']:,.0f}"
            
            # Categorize
            category = categorize_opportunity(title, description or '')
            
            opportunity = {
                'title': title,
                'organization': agency,
                'description': description,
                'eligibility': clean_text(opp_data.get('eligibility', '')),
                'funding_amount': funding_amount,
                'deadline': deadline,
                'category': category,
                'location': 'United States',
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
    
    def fetch_full_details(self, opportunity_id):
        """Fetch full opportunity details including documents"""
        try:
            detail_url = f"{self.api_url}/{opportunity_id}"
            response = self.fetch_page(detail_url)
            
            if response:
                data = response.json()
                # Extract document URLs if available
                documents = []
                if 'synopsisAttachments' in data:
                    for doc in data['synopsisAttachments']:
                        if 'url' in doc:
                            documents.append(doc['url'])
                
                return documents
        except Exception as e:
            logger.error(f"Error fetching full details: {e}")
        
        return []
