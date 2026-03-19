from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class DOEScraper(BaseScraper):
    """Department of Energy grants scraper"""
    def __init__(self):
        super().__init__('DOE Grants')
        self.base_url = 'https://eere-exchange.energy.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(self.base_url)
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.opportunity-item, .funding-opp')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find(['h3', 'a'])
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            link = element.find('a')
            url = f"{self.base_url}{link['href']}" if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'U.S. Department of Energy',
                'description': None,
                'eligibility': 'Businesses, universities, research institutions',
                'funding_amount': None,
                'deadline': None,
                'category': 'Energy',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None


class USDAGrantsScraper(BaseScraper):
    """USDA grants scraper"""
    def __init__(self):
        super().__init__('USDA Grants')
        self.base_url = 'https://www.grants.usda.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/web/grants/search-grants.html')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-listing, .program-item')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find(['h3', 'a'])
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            link = element.find('a')
            url = f"{self.base_url}{link['href']}" if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'U.S. Department of Agriculture',
                'description': None,
                'eligibility': 'Farmers, rural communities, research institutions',
                'funding_amount': None,
                'deadline': None,
                'category': 'Agriculture',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None


class EPAGrantsScraper(BaseScraper):
    """EPA grants scraper"""
    def __init__(self):
        super().__init__('EPA Grants')
        self.base_url = 'https://www.epa.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-item, .view-content .views-row')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find(['h3', 'h4', 'a'])
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            link = element.find('a')
            url = f"{self.base_url}{link['href']}" if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'U.S. Environmental Protection Agency',
                'description': None,
                'eligibility': 'State/local governments, nonprofits, universities',
                'funding_amount': None,
                'deadline': None,
                'category': 'Environment',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None


class HUDGrantsScraper(BaseScraper):
    """HUD grants scraper"""
    def __init__(self):
        super().__init__('HUD Grants')
        self.base_url = 'https://www.hud.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/program_offices/administration/grants/fundsavail')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-notice, .content-item a')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            if element.name == 'a':
                title = clean_text(element.text)
                url = f"{self.base_url}{element['href']}" if element.get('href') else self.base_url
            else:
                title_elem = element.find('a')
                if not title_elem:
                    return None
                title = clean_text(title_elem.text)
                url = f"{self.base_url}{title_elem['href']}" if title_elem.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'U.S. Department of Housing and Urban Development',
                'description': None,
                'eligibility': 'State/local governments, housing authorities',
                'funding_amount': None,
                'deadline': None,
                'category': 'Housing',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None


class SBAGrantsScraper(BaseScraper):
    """SBA grants scraper"""
    def __init__(self):
        super().__init__('SBA Grants')
        self.base_url = 'https://www.sba.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/funding-programs/grants')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.program-card, .grant-program')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find(['h3', 'a'])
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            link = element.find('a')
            url = f"{self.base_url}{link['href']}" if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'U.S. Small Business Administration',
                'description': None,
                'eligibility': 'Small businesses, entrepreneurs',
                'funding_amount': None,
                'deadline': None,
                'category': 'Business',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None
