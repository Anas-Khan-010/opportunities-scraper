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
        self._new_count = 0
        self._dup_count = 0
        self._max_new = config.MAX_NEW_PER_SCRAPER

    def reached_limit(self):
        """True when we've collected enough NEW opportunities for this run."""
        if self._max_new <= 0:
            return False
        return self._new_count >= self._max_new

    def add_opportunity(self, opp):
        """Store an opportunity to the DB immediately and track new vs dup.

        Every opportunity is written to the database the moment it is
        scraped, so nothing is lost if the process is interrupted.
        Only genuinely NEW records count toward the per-scraper limit.

        Returns True if the opportunity is NEW, False if duplicate/update.
        """
        from database.db import db

        source_url = opp.get('source_url', '')
        is_new = not (source_url and db.opportunity_exists(source_url))

        opp.setdefault('opportunity_type', None)
        try:
            db.insert_opportunity(opp)
        except Exception as exc:
            logger.debug(f"{self.source_name}: DB write failed: {exc}")

        self.opportunities.append(opp)

        if is_new:
            self._new_count += 1
            if self._max_new > 0 and self._new_count >= self._max_new:
                logger.info(
                    f"{self.source_name}: reached {self._max_new} new opportunities limit — stopping early"
                )
        else:
            self._dup_count += 1

        return is_new

    def track_new(self):
        """Legacy counter — prefer add_opportunity() instead."""
        self._new_count += 1
        return self._new_count
    
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
        total = len(self.opportunities)
        logger.info(
            f"{self.source_name}: {total} scraped | {self._new_count} new | {self._dup_count} duplicates"
        )
