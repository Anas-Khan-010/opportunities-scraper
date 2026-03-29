import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from scrapers.base_scraper import BaseScraper
from config.settings import config
from database.db import db
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class SAMGovScraper(BaseScraper):
    """
    Robust scraper for SAM.gov - Federal contract opportunities and RFPs.
    
    Architecture:
        1. search v2 API -> paginated search using mandatory date filters
        2. detail description API (v1/noticedesc) -> fetch HTML description
        3. Parse HTML description into plain text
    """
    
    def __init__(self):
        super().__init__('SAM.gov')
        self.base_url = config.SAM_GOV_BASE_URL
        self.api_url = config.SAM_GOV_API_URL
        self.api_key = config.SAM_GOV_API_KEY
    
    def scrape(self, max_pages=5):
        """Scrape contract opportunities from SAM.gov"""
        logger.info(f"Starting {self.source_name} scraper...")
        logger.info(f"\n🚀 Starting {self.source_name} scraper (API Only Mode)")
        
        if not self.api_key:
            logger.warning("SAM.gov API key not configured. Get free key at https://sam.gov/data-services/")
            logger.warning("Add SAM_GOV_API_KEY to .env file to enable this scraper")
            return self.opportunities
        
        # SAM.gov v2 search requires postedFrom and postedTo (max 1 year apart)
        # We will default to looking back 180 days from today to get fresh opps
        today = datetime.now()
        posted_to = today.strftime('%m/%d/%Y')
        posted_from = (today - timedelta(days=180)).strftime('%m/%d/%Y')
        
        logger.info(f"📅 Searching from {posted_from} to {posted_to}")
        
        # Track DB duplicates
        sequential_duplicates = 0
        
        for page in range(max_pages):
            try:
                params = {
                    'api_key': self.api_key,
                    'limit': 50,
                    'offset': page * 50,
                    'postedFrom': posted_from,
                    'postedTo': posted_to
                }
                
                response = self.fetch_page(self.api_url, params=params)
                if not response:
                    logger.warning(f"❌ Failed to fetch page {page + 1}")
                    continue
                
                data = response.json()
                
                if 'opportunitiesData' not in data or not data['opportunitiesData']:
                    logger.info(f"ℹ️ No more opportunities found on page {page + 1}")
                    break
                
                opps_data = data['opportunitiesData']
                logger.info(f"📄 Page {page + 1} returned {len(opps_data)} opportunities")
                
                for opp in opps_data:
                    # Construct UI link for deduplication check
                    ui_link = opp.get('uiLink')
                    if not ui_link:
                        ui_link = f"{self.base_url}/workspace/contract/opp/{opp.get('noticeId')}/view"
                        
                    if db.opportunity_exists(ui_link):
                        sequential_duplicates += 1
                        logger.info(f"  ⏭️  Skipped DB duplicate: {opp.get('title', '')[:50]}...")
                        if sequential_duplicates >= 20:
                            logger.info(f"  🛑 Hit 20 duplicates in a row. Stopping scraper.")
                            return self.opportunities
                        continue
                        
                    sequential_duplicates = 0
                    
                    opportunity = self.parse_opportunity(opp)
                    if opportunity:
                        self.opportunities.append(opportunity)
                        logger.info(f"  ✅ Extracted: {opportunity['title'][:60]}...")
                        
                    # HARD RATE LIMITING: SAM.gov API has extremely strict burst quotas.
                    # Sleeping configuration set in .env between each opportunity to ensure we stay well below limits.
                    logger.info(f"    ⏳ Anti-ban: Sleeping {config.SAM_GOV_OPP_DELAY}s before next request...")
                    time.sleep(config.SAM_GOV_OPP_DELAY)
                
                # HARD RATE LIMITING: Sleep between major paginated search requests
                if page < max_pages - 1:
                    logger.info(f"🛑 MAJOR REST: Waiting {config.SAM_GOV_PAGE_DELAY} seconds to clear SAM API quota buckets completely...")
                    time.sleep(config.SAM_GOV_PAGE_DELAY)
                    
            except Exception as e:
                logger.error(f"Error scraping page {page + 1}: {e}")
                continue
        
        self.log_summary()
        return self.opportunities
    
    def _fetch_description(self, desc_url):
        """Fetch and clean the HTML description from the noticedesc endpoint"""
        if not desc_url:
            return None
            
        try:
            # Add API key to the description URL
            parsed_url = urlparse(desc_url)
            query = parse_qs(parsed_url.query)
            query['api_key'] = [self.api_key]
            
            # Reconstruct URL
            new_query = urlencode(query, doseq=True)
            auth_url = urlunparse(parsed_url._replace(query=new_query))
            
            response = self.fetch_page(auth_url)
            if not response:
                return None
                
            data = response.json()
            html_content = data.get('description', '')
            
            if html_content:
                # Use BaseScraper's parse_html to parse via BeautifulSoup
                soup = self.parse_html(html_content)
                if soup:
                    # Extract text, stripping HTML tags and replacing block elements with newlines
                    text = soup.get_text(separator='\n\n', strip=True)
                    return clean_text(text, preserve_newlines=True)
                    
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch description: {e}")
            return None
    
    def parse_opportunity(self, opp_data):
        """Parse individual contract opportunity"""
        try:
            title = clean_text(opp_data.get('title', ''))
            opportunity_number = clean_text(opp_data.get('solicitationNumber', ''))
            
            source_url = opp_data.get('uiLink')
            if not source_url:
                source_url = f"{self.base_url}/workspace/contract/opp/{opp_data.get('noticeId')}/view"
            
            # Parse dates
            posted_date = parse_date(opp_data.get('postedDate'))
            deadline = parse_date(opp_data.get('responseDeadLine'))
            
            # Get organization
            organization = clean_text(opp_data.get('fullParentPathName', ''))
            if not organization and 'officeAddress' in opp_data:
                organization = f"Office in {opp_data['officeAddress'].get('city', '')}"
            
            # Category
            category = opp_data.get('baseType', 'Contract')
            
            # Location
            location = "United States"
            pop = opp_data.get('placeOfPerformance')
            if pop:
                city = pop.get('city', {}).get('name', '')
                state = pop.get('state', {}).get('code', '')
                country = pop.get('country', {}).get('name', '')
                loc_parts = [p for p in [city, state, country] if p]
                if loc_parts:
                    location = ", ".join(loc_parts)
                    
            # Eligibility
            eligibility = clean_text(opp_data.get('typeOfSetAsideDescription') or opp_data.get('typeOfSetAside', ''))
            if eligibility == 'NONE' or eligibility == '':
                eligibility = 'Unrestricted / No Set-Aside'
                
            # Description (Secondary API fetch)
            desc_api_link = opp_data.get('description')
            description = None
            if desc_api_link and desc_api_link.startswith('http'):
                description = self._fetch_description(desc_api_link)
                
            # Auto-categorize if needed
            if category and category.lower() in ['solicitation', 'presolicitation', 'sources sought', 'award notice']:
                guessed_cat = categorize_opportunity(title, description or '')
                if guessed_cat != 'General':
                    category = f"{category} - {guessed_cat}"
            
            # Note: We omit document_urls since SAM.gov `resourceLinks` return 401 UNAUTHORIZED
            # for regular unauthenticated users anyway.
            
            opportunity = {
                'title': title,
                'organization': organization,
                'description': description,
                'eligibility': eligibility,
                'funding_amount': None, # API generally omits this
                'deadline': deadline,
                'category': category or 'General',
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

if __name__ == "__main__":
    scraper = SAMGovScraper()
    
    try:
        opps = scraper.scrape(max_pages=1) # Test with 1 page
    except KeyboardInterrupt:
        print("\n\n🛑 Script stopped manually!")
        opps = scraper.opportunities
    except Exception as e:
        print(f"\n\n💥 Script crashed: {e}")
        opps = scraper.opportunities
    finally:
        print(f"\nRescuing {len(opps)} opportunities scraped so far...\n")
        print("⏳ Connecting to Supabase... (Please DO NOT press Ctrl+C again!)\n")
        
        for i, opp in enumerate(opps[:3]):
            print(f"--- #{i+1} ---")
            for k, v in opp.items():
                val_str = str(v)
                if len(val_str) > 150:
                    val_str = val_str[:150] + "..."
                print(f"  {k}: {val_str}")
            print()

        # Insert to DB
        inserted = 0
        try:
            for opp in opps:
                result = db.insert_opportunity(opp)
                if result:
                    inserted += 1
        except KeyboardInterrupt:
            print("\n\n⚠️ Rescue interrupted by second Ctrl+C! Stopping DB inserts.")
        except Exception as e:
            print(f"\n\n💥 DB Error during rescue: {e}")

        print(f"\n✅ Saved: {inserted}/{len(opps)} new opportunities to Supabase")
        print(f"📊 DB Stats: {db.get_stats()}")
