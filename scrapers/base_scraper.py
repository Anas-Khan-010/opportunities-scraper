import requests
import time
import random
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from config.settings import config
from utils.logger import logger

class BaseScraper(ABC):
    """Base class for all scrapers"""
    
    def __init__(self, source_name):
        self.source_name = source_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config.USER_AGENTS)
        })
        self.opportunities = []
    
    def fetch_page(self, url, method='GET', **kwargs):
        """Fetch page with retry logic"""
        for attempt in range(config.MAX_RETRIES):
            try:
                if method == 'GET':
                    response = self.session.get(url, timeout=30, **kwargs)
                else:
                    response = self.session.post(url, timeout=30, **kwargs)
                
                response.raise_for_status()
                time.sleep(config.SCRAPER_DELAY)
                return response
            
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.SCRAPER_DELAY * 2)
                else:
                    logger.error(f"Failed to fetch {url} after {config.MAX_RETRIES} attempts")
                    return None
    
    def parse_html(self, html_content):
        """Parse HTML content with BeautifulSoup"""
        return BeautifulSoup(html_content, 'lxml')
    
    @abstractmethod
    def scrape(self):
        """Main scraping method - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    def parse_opportunity(self, element):
        """Parse individual opportunity - must be implemented by subclasses"""
        pass
    
    def get_opportunities(self):
        """Return collected opportunities"""
        return self.opportunities
    
    def log_summary(self):
        """Log scraping summary"""
        logger.info(f"{self.source_name}: Found {len(self.opportunities)} opportunities")
