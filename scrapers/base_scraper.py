import os
import subprocess
import re
import requests
import time
import random
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from config.settings import config
from utils.logger import logger

SELENIUM_DELAY_RANGE = (config.SELENIUM_DELAY_MIN, config.SELENIUM_DELAY_MAX)


def _detect_chrome_binary():
    """Locate a usable Chrome/Chromium binary on the system.

    Returns ``(path, major_version)`` or ``(None, None)``.
    """
    candidates = (
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/opt/google/chrome/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
    )
    import shutil
    for path in candidates:
        if not os.path.exists(path) and shutil.which(path) is None:
            continue
        try:
            out = subprocess.check_output(
                [path, '--version'], stderr=subprocess.STDOUT, text=True, timeout=10
            )
            m = re.search(r'(\d+)\.', out)
            if m:
                return path, int(m.group(1))
        except Exception:
            continue
    return None, None


def _detect_chrome_major_version():
    """Best-effort major Chrome/Chromium version for undetected_chromedriver."""
    _, version = _detect_chrome_binary()
    return version


class SeleniumDriverManager:
    """Manages a single shared headless Chrome instance across all scrapers."""

    _driver = None
    _current_proxy = None

    @classmethod
    def get_driver(cls, use_proxy=False, force_new=False):
        # Determine if we need to restart the driver for proxy change
        needs_restart = False
        if force_new or (use_proxy and not cls._current_proxy) or (not use_proxy and cls._current_proxy):
            needs_restart = True
            
        if cls._driver is not None:
            if needs_restart:
                cls.quit()
            else:
                try:
                    cls._driver.title
                    return cls._driver
                except Exception:
                    logger.warning("Shared Selenium driver is dead, restarting...")
                    cls._driver = None

        try:
            import undetected_chromedriver as uc

            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--log-level=3')
            options.add_argument('--dns-prefetch-disable')
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # --- Network Evasion (Free Proxy) ---
            proxy_url = None
            if use_proxy:
                try:
                    from fp.fp import FreeProxy
                    logger.info("Fetching a free US proxy for evasion...")
                    proxy_url = FreeProxy(country_id=['US'], https=True).get()
                    if proxy_url:
                        logger.info(f"Using Free Proxy: {proxy_url}")
                        options.add_argument(f'--proxy-server={proxy_url}')
                        cls._current_proxy = proxy_url
                except Exception as proxy_e:
                    logger.error(f"Failed to fetch proxy: {proxy_e}")
                    cls._current_proxy = None

            browser_path, version_main = _detect_chrome_binary()
            if version_main is None:
                logger.error("Chrome/Chromium not found on this system.")
                return None

            if browser_path:
                options.binary_location = browser_path

            cls._driver = uc.Chrome(
                options=options,
                headless=True,
                use_subprocess=True,
                version_main=version_main,
                browser_executable_path=browser_path,
            )
            
            # Stealth: patch navigator.webdriver
            cls._driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            # Increase timeout since free proxies are slow
            timeout_val = 60 if use_proxy else 45
            cls._driver.set_page_load_timeout(timeout_val)

            realistic_ua = (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{version_main}.0.0.0 Safari/537.36'
            )
            try:
                cls._driver.execute_cdp_cmd(
                    'Network.setUserAgentOverride',
                    {"userAgent": realistic_ua},
                )
            except Exception:
                pass

            proxy_str = f" (Proxy: {cls._current_proxy})" if cls._current_proxy else ""
            logger.info(f"Shared Selenium driver initialized{proxy_str}")
            return cls._driver
        except Exception as e:
            logger.error(f"Failed to init shared Selenium driver: {e}")
            return None

    @staticmethod
    def resolve_host(host):
        """DNS Fallback for known blocked gov portals."""
        fallbacks = {
            'omb.illinois.gov': '216.124.52.91',
            'procure.ohio.gov': '156.63.155.65',
            'finance.ky.gov': '13.107.246.40', # FrontDoor IP
            'oa.mo.gov': '198.209.11.16',
            'arkansas.gov': '170.94.34.195',
            'doas.ga.gov': '167.196.1.18',
        }
        return fallbacks.get(host, host)

    @classmethod
    def quit(cls):
        if cls._driver is not None:
            try:
                cls._driver.quit()
                logger.info("Shared Selenium driver closed")
            except Exception as e:
                logger.warning(f"Error closing shared Selenium driver: {e}")
            finally:
                cls._driver = None
                cls._current_proxy = None


def cleanup_selenium():
    """Close the shared Selenium driver (call at end of scraping session)."""
    SeleniumDriverManager.quit()


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
        
        # Validation: Reject obviously invalid/dead links or generic noise
        NOISE_DOMAINS = [
            'denotificationservices.bbcportal.com',
            'bbcportal.com/registration',
            'public.govdelivery.com',
            'subscriberhelp.govdelivery.com',
        ]
        
        if source_url:
            url_lower = source_url.lower()
            if url_lower.startswith('javascript:'):
                logger.warning(f"{self.source_name}: Skipping invalid source_url: {source_url}")
                return False
            if any(domain in url_lower for domain in NOISE_DOMAINS):
                logger.info(f"{self.source_name}: Filtering out generic noise URL: {source_url}")
                return False

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
    
    def enrich_from_documents(self, opp):
        """Download PDFs listed in opp['document_urls'] and backfill empty fields."""
        from parsers.parser_utils import OpportunityEnricher
        try:
            OpportunityEnricher.enrich_with_documents(opp)
        except Exception as exc:
            logger.debug(f"{self.source_name}: PDF enrichment failed: {exc}")
        return opp

    def get_opportunities(self):
        """Return collected opportunities"""
        return self.opportunities
    
    def log_summary(self):
        """Log scraping summary"""
        total = len(self.opportunities)
        logger.info(
            f"{self.source_name}: {total} scraped | {self._new_count} new | {self._dup_count} duplicates"
        )

class BaseIvaluaScraper(BaseScraper):
    """Base class for Ivalua-based portals (Alabama, Arizona, Maryland, etc.)"""
    
    def __init__(self, source_name, base_url, location):
        super().__init__(source_name)
        self.base_url = base_url
        self.location = location

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver: return self.opportunities
        
        try:
            driver.get(self.base_url)
            time.sleep(random.uniform(10, 15))
            
            # Check for Cloudflare
            if "Just a moment" in driver.page_source:
                logger.info(f"  {self.source_name}: Waiting for Cloudflare bypass...")
                time.sleep(15)
                
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Ivalua grids usually have 'body_x_grid_grd'
            table = soup.find('table', id='body_x_grid_grd')
            if not table:
                table = soup.find('table', class_='iv-grid-view')
                
            if not table:
                logger.warning(f"  {self.source_name}: No grid found")
                return self.opportunities
                
            tbody = table.find('tbody')
            if not tbody:
                # Some versions put rows directly in the table
                rows = table.find_all('tr', class_=lambda x: x and 'iv-grid-row' in x)
            else:
                rows = tbody.find_all('tr')
                
            for row in rows:
                if self.reached_limit(): break
                opp = self.parse_ivalua_row(row)
                if opp: self.add_opportunity(opp)
        except Exception as e:
            logger.error(f"  {self.source_name} error: {e}")
            
        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        return self.parse_ivalua_row(row)

    def parse_ivalua_row(self, row):
        cells = row.find_all('td')
        if len(cells) < 4: return None
        try:
            row_id = row.get('data-id', '')
            opp_number = clean_text(cells[1].get_text(strip=True))
            title = clean_text(cells[2].get_text(strip=True))
            
            if not title or len(title) < 5: return None
            
            # Ivalua columns vary, but Agency is usually after title
            org = clean_text(cells[5].get_text(strip=True)) if len(cells) > 5 else ''
            deadline_str = clean_text(cells[-1].get_text(strip=True))
            
            # Detail URL
            domain = self.base_url.split('/page.aspx')[0]
            if row_id:
                source_url = f"{domain}/page.aspx/en/bpm/process_manage_extranet/{row_id}"
            else:
                source_url = self.base_url

            return {
                'title': title,
                'organization': org or f"State of {self.location}",
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': parse_date(deadline_str),
                'category': categorize_opportunity(title, ''),
                'location': self.location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'rfp',
            }
        except: return None
