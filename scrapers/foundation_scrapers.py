from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class FoundationCenterScraper(BaseScraper):
    """Scraper for Foundation Directory Online (Candid)"""
    
    def __init__(self):
        super().__init__('Foundation Center')
        self.base_url = 'https://fconline.foundationcenter.org'
    
    def scrape(self):
        """Scrape foundation grants"""
        logger.info(f"Starting {self.source_name} scraper...")
        logger.warning("Foundation Center requires subscription - implementing placeholder")
        
        # Note: This site requires authentication and subscription
        # Implementation would need client credentials
        
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        """Parse foundation opportunity"""
        pass


class GrantWatchScraper(BaseScraper):
    """Scraper for GrantWatch.com"""
    
    def __init__(self):
        super().__init__('GrantWatch')
        self.base_url = 'https://www.grantwatch.com'
    
    def scrape(self):
        """Scrape GrantWatch opportunities"""
        logger.info(f"Starting {self.source_name} scraper...")
        
        try:
            # GrantWatch has free listings
            search_url = f'{self.base_url}/grants.php'
            response = self.fetch_page(search_url)
            
            if not response:
                return self.opportunities
            
            soup = self.parse_html(response.content)
            
            # Parse grant listings
            grant_elements = soup.find_all('div', class_='grant-item')
            
            for element in grant_elements:
                opportunity = self.parse_opportunity(element)
                if opportunity:
                    self.opportunities.append(opportunity)
            
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        """Parse GrantWatch opportunity"""
        try:
            title_elem = element.find('a', class_='grant-title')
            if not title_elem:
                return None
            
            title = clean_text(title_elem.text)
            url = title_elem.get('href', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}/{url}"
            
            # Extract description
            desc_elem = element.find('div', class_='grant-description')
            description = clean_text(desc_elem.text) if desc_elem else None
            
            # Extract deadline
            deadline_elem = element.find('span', class_='deadline')
            deadline = parse_date(deadline_elem.text) if deadline_elem else None
            
            opportunity = {
                'title': title,
                'organization': 'Various Foundations',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': categorize_opportunity(title, description or ''),
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error parsing opportunity: {e}")
            return None


class NIHGrantsScraper(BaseScraper):
    """Scraper for NIH (National Institutes of Health) grants"""
    
    def __init__(self):
        super().__init__('NIH Grants')
        self.base_url = 'https://grants.nih.gov'
        self.search_url = f'{self.base_url}/funding/searchguide/nih-guide-to-grants-and-contracts.cfm'
    
    def scrape(self):
        """Scrape NIH grant opportunities"""
        logger.info(f"Starting {self.source_name} scraper...")
        
        try:
            response = self.fetch_page(self.search_url)
            
            if not response:
                return self.opportunities
            
            soup = self.parse_html(response.content)
            
            # Parse NIH notices
            notice_elements = soup.find_all('div', class_='notice')
            
            for element in notice_elements:
                opportunity = self.parse_opportunity(element)
                if opportunity:
                    self.opportunities.append(opportunity)
            
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        """Parse NIH grant opportunity"""
        try:
            title_elem = element.find('a')
            if not title_elem:
                return None
            
            title = clean_text(title_elem.text)
            url = title_elem.get('href', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}{url}"
            
            opportunity = {
                'title': title,
                'organization': 'National Institutes of Health',
                'description': None,
                'eligibility': 'Research institutions, universities',
                'funding_amount': None,
                'deadline': None,
                'category': 'Healthcare',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error parsing opportunity: {e}")
            return None


class NSFGrantsScraper(BaseScraper):
    """Scraper for NSF (National Science Foundation) grants"""
    
    def __init__(self):
        super().__init__('NSF Grants')
        self.base_url = 'https://www.nsf.gov'
        self.search_url = f'{self.base_url}/funding/opportunities'
    
    def scrape(self):
        """Scrape NSF grant opportunities"""
        logger.info(f"Starting {self.source_name} scraper...")
        
        try:
            response = self.fetch_page(self.search_url)
            
            if not response:
                return self.opportunities
            
            soup = self.parse_html(response.content)
            
            # Parse funding opportunities
            opp_elements = soup.find_all('div', class_='funding-opportunity')
            
            for element in opp_elements:
                opportunity = self.parse_opportunity(element)
                if opportunity:
                    self.opportunities.append(opportunity)
            
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        """Parse NSF grant opportunity"""
        try:
            title_elem = element.find('a')
            if not title_elem:
                return None
            
            title = clean_text(title_elem.text)
            url = title_elem.get('href', '')
            if url and not url.startswith('http'):
                url = f"{self.base_url}{url}"
            
            opportunity = {
                'title': title,
                'organization': 'National Science Foundation',
                'description': None,
                'eligibility': 'Research institutions, universities',
                'funding_amount': None,
                'deadline': None,
                'category': 'Research',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error parsing opportunity: {e}")
            return None


class GatesFoundationScraper(BaseScraper):
    def __init__(self):
        super().__init__('Gates Foundation')
        self.base_url = 'https://www.gatesfoundation.org'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/about/how-we-work/general-information/grant-opportunities')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-opportunity, .content-item')[:10]:
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
                'organization': 'Bill & Melinda Gates Foundation',
                'description': clean_text(element.find('p').text) if element.find('p') else None,
                'eligibility': 'Nonprofits, research institutions',
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Global',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
        except:
            return None


class FordFoundationScraper(BaseScraper):
    def __init__(self):
        super().__init__('Ford Foundation')
        self.base_url = 'https://www.fordfoundation.org'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/work/our-grants/')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-item, .program-area')[:10]:
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
                'organization': 'Ford Foundation',
                'description': None,
                'eligibility': 'Nonprofits, social justice organizations',
                'funding_amount': None,
                'deadline': None,
                'category': 'Social Justice',
                'location': 'Global',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
        except:
            return None


class RWJFScraper(BaseScraper):
    def __init__(self):
        super().__init__('Robert Wood Johnson Foundation')
        self.base_url = 'https://www.rwjf.org'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants/apply-for-a-grant')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-opportunity, .funding-opp')[:10]:
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
                'organization': 'Robert Wood Johnson Foundation',
                'description': None,
                'eligibility': 'Health organizations, nonprofits',
                'funding_amount': None,
                'deadline': None,
                'category': 'Healthcare',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
        except:
            return None


class KelloggFoundationScraper(BaseScraper):
    def __init__(self):
        super().__init__('W.K. Kellogg Foundation')
        self.base_url = 'https://www.wkkf.org'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-listing, .opportunity')[:10]:
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
                'organization': 'W.K. Kellogg Foundation',
                'description': None,
                'eligibility': 'Community organizations, nonprofits',
                'funding_amount': None,
                'deadline': None,
                'category': 'Community',
                'location': 'United States',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
        except:
            return None


class MacArthurFoundationScraper(BaseScraper):
    def __init__(self):
        super().__init__('MacArthur Foundation')
        self.base_url = 'https://www.macfound.org'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants/')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-program, .funding-area')[:10]:
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
                'organization': 'MacArthur Foundation',
                'description': None,
                'eligibility': 'Nonprofits, research institutions',
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Global',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'grant'
            }
        except:
            return None
