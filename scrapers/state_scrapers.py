from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class CaliforniaScraper(BaseScraper):
    def __init__(self):
        super().__init__('California Grants')
        self.base_url = 'https://grants.ca.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants/')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for row in soup.select('table.grants-table tr')[1:20]:
                opp = self.parse_opportunity(row)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            cells = element.find_all('td')
            if len(cells) < 2:
                return None
            title = clean_text(cells[0].text)
            link = cells[0].find('a')
            url = f"{self.base_url}{link['href']}" if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'State of California',
                'description': clean_text(cells[1].text) if len(cells) > 1 else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': parse_date(cells[2].text) if len(cells) > 2 else None,
                'category': categorize_opportunity(title, ''),
                'location': 'California',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class TexasScraper(BaseScraper):
    def __init__(self):
        super().__init__('Texas Grants')
        self.base_url = 'https://comptroller.texas.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/programs/')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.program-item, .grant-listing')[:15]:
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
                'organization': 'State of Texas',
                'description': clean_text(element.find('p').text) if element.find('p') else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Texas',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class FloridaScraper(BaseScraper):
    def __init__(self):
        super().__init__('Florida Grants')
        self.base_url = 'https://www.myfloridacfo.com'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/division/aa/grants/')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-item, .content-item')[:15]:
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
                'organization': 'State of Florida',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Florida',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class NewYorkScraper(BaseScraper):
    def __init__(self):
        super().__init__('New York Grants')
        self.base_url = 'https://grantsgateway.ny.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/IntelliGrants_NYSGG/module/nysgg/goportal.aspx')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-row, tr.data-row')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find(['a', 'td'])
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            link = element.find('a')
            url = link['href'] if link and link.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'State of New York',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'New York',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class PennsylvaniaScraper(BaseScraper):
    def __init__(self):
        super().__init__('Pennsylvania Grants')
        self.base_url = 'https://www.grants.pa.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/Search.aspx')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-listing, .search-result')[:15]:
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
                'organization': 'Commonwealth of Pennsylvania',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Pennsylvania',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class IllinoisScraper(BaseScraper):
    def __init__(self):
        super().__init__('Illinois Grants')
        self.base_url = 'https://www2.illinois.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/sites/GATA/Grants/SitePages/AvailableGrants.aspx')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-item, .ms-listlink')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find('a')
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            url = title_elem['href'] if title_elem.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'State of Illinois',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Illinois',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class OhioScraper(BaseScraper):
    def __init__(self):
        super().__init__('Ohio Grants')
        self.base_url = 'https://development.ohio.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/bs/bs_grantslist.htm')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-listing, li a')[:15]:
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
                'organization': 'State of Ohio',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Ohio',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class GeorgiaScraper(BaseScraper):
    def __init__(self):
        super().__init__('Georgia Grants')
        self.base_url = 'https://www.dca.ga.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/safe-affordable-housing/funding')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.funding-item, .content-block a')[:15]:
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
                'organization': 'State of Georgia',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Georgia',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class NorthCarolinaScraper(BaseScraper):
    def __init__(self):
        super().__init__('North Carolina Grants')
        self.base_url = 'https://www.nccommerce.com'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/grants-incentives')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-program, .program-link')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find('a')
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            url = f"{self.base_url}{title_elem['href']}" if title_elem.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'State of North Carolina',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'North Carolina',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None

class MichiganScraper(BaseScraper):
    def __init__(self):
        super().__init__('Michigan Grants')
        self.base_url = 'https://www.michigan.gov'
    
    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        try:
            response = self.fetch_page(f'{self.base_url}/budget/resources/grants')
            if not response:
                return self.opportunities
            soup = self.parse_html(response.content)
            for item in soup.select('.grant-listing, .content-link')[:15]:
                opp = self.parse_opportunity(item)
                if opp:
                    self.opportunities.append(opp)
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        self.log_summary()
        return self.opportunities
    
    def parse_opportunity(self, element):
        try:
            title_elem = element.find('a')
            if not title_elem:
                return None
            title = clean_text(title_elem.text)
            url = f"{self.base_url}{title_elem['href']}" if title_elem.get('href') else self.base_url
            return {
                'title': title,
                'organization': 'State of Michigan',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(title, ''),
                'location': 'Michigan',
                'source': self.source_name,
                'source_url': url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [],
                'full_document': None
            }
        except:
            return None
