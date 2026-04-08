"""
Shared infrastructure for state-level scrapers.

Classes:
  _SeleniumDriverManager - singleton headless Chrome manager
  StateAPIScraper        - JSON API scraper (e.g., CKAN)
  StateHTMLScraper       - static HTML scraper (requests + BeautifulSoup)
  StateSeleniumScraper   - JS-rendered portal scraper (Selenium)

Functions:
  create_state_scrapers(configs) - factory to build scraper instances from config list
  cleanup_state_scrapers()       - close shared Selenium driver
"""

import subprocess
import time
import random
import re
import urllib.parse
from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

SELENIUM_DELAY_RANGE = (config.SELENIUM_DELAY_MIN, config.SELENIUM_DELAY_MAX)

_TITLE_BLOCKLIST = {
    'here', 'click here', 'click', 'more', 'read more', 'learn more',
    'view', 'view details', 'details', 'download', 'link', 'submit',
    'apply', 'apply now', 'register', 'sign in', 'login', 'log in',
    'home', 'back', 'next', 'previous', 'close', 'open', 'see more',
}


def _title_is_garbage(title: str) -> bool:
    """Reject generic/navigational link text that isn't a real title."""
    if not title or len(title) < 6:
        return True
    if title.lower().strip() in _TITLE_BLOCKLIST:
        return True
    return False


# When fallback_procurement_only is set on a config, only keep links whose text
# looks like a solicitation (stops MS/MI-style portals from harvesting nav noise).
_PROCUREMENT_TITLE_RE = re.compile(
    r'(?:^|\s)(?:BID\s*:|RFQ|RFP|IFB|ITB|RFI|RFX|ITN|SOLICITATION|'
    r'INVITATION\s+TO\s+BID|REQUEST\s+FOR\s+(?:PROPOSAL|QUOTATION|QUALIFICATIONS))',
    re.I,
)
_MS_STYLE_BIDNUM = re.compile(
    r'\b\d{3,4}-\d{2}-[A-Z]+-[A-Z]+-\d+\b',
)


def _detect_chrome_major_version():
    """Best-effort major Chrome/Chromium version for undetected_chromedriver."""
    for cmd in (
        ['google-chrome', '--version'],
        ['google-chrome-stable', '--version'],
        ['chromium', '--version'],
        ['chromium-browser', '--version'],
    ):
        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, text=True, timeout=10
            )
            m = re.search(r'(\d+)\.', out)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def _title_looks_like_procurement(title: str) -> bool:
    if not title or len(title) < 8:
        return False
    if _PROCUREMENT_TITLE_RE.search(title):
        return True
    if _MS_STYLE_BIDNUM.search(title):
        return True
    return False


class _SeleniumDriverManager:
    """Manages a single shared headless Chrome instance across all state scrapers."""

    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is not None:
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
            options.add_argument(
                'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
            # Note: excludeSwitches breaks uc.ChromeOptions parsing in some Chrome builds

            version_main = _detect_chrome_major_version()
            if version_main:
                logger.debug(f"undetected-chromedriver version_main={version_main}")

            # headless=True via kwarg (do not pass --headless; UC patches it)
            cls._driver = uc.Chrome(
                options=options,
                headless=True,
                use_subprocess=True,
                version_main=version_main,
            )
            cls._driver.set_page_load_timeout(45)
            logger.info("Shared Selenium driver initialized (undetected-chromedriver)")
            return cls._driver
        except Exception as e:
            logger.error(f"Failed to init shared Selenium driver: {e}")
            return None

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


# ---------------------------------------------------------------------------
# StateAPIScraper — JSON API (California CKAN, etc.)
# ---------------------------------------------------------------------------

class StateAPIScraper(BaseScraper):
    """Scraper for states that expose data via a public JSON API."""

    def __init__(self, config):
        super().__init__(config['source_name'])
        self.config = config
        self.state_name = config['name']
        self.organization = config['organization']
        self.location = config['location']
        self.opportunity_type = config.get('opportunity_type', 'grant')

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (API)...")

        api_type = self.config.get('api_type', 'ckan')
        if api_type == 'ckan':
            self._scrape_ckan()
        else:
            logger.error(f"Unknown API type: {api_type}")

        self.log_summary()
        return self.opportunities

    def _scrape_ckan(self):
        api_url = self.config['api_url']
        resource_id = self.config['resource_id']
        page_size = self.config.get('page_size', 100)
        offset = 0

        count_sql = (
            f'SELECT COUNT(*) FROM "{resource_id}" WHERE "Status" = \'active\''
        )
        total = None
        try:
            resp = self.fetch_page(api_url, params={'sql': count_sql})
            if resp:
                total = resp.json()['result']['records'][0]['count']
                logger.info(f"{self.state_name}: {total} active records in API")
        except Exception:
            pass

        while True:
            sql = (
                f'SELECT * FROM "{resource_id}" '
                f"WHERE \"Status\" = 'active' "
                f'ORDER BY "_id" ASC '
                f'LIMIT {page_size} OFFSET {offset}'
            )
            try:
                response = self.fetch_page(api_url, params={'sql': sql})
                if not response:
                    break

                data = response.json()
                if not data.get('success'):
                    logger.error(f"CKAN API error: {data}")
                    break

                records = data['result'].get('records', [])
                if not records:
                    break

                for record in records:
                    opp = self.parse_opportunity(record)
                    if opp:
                        self.add_opportunity(opp)
                    if self.reached_limit():
                        break

                logger.info(
                    f"  Fetched offset {offset}-{offset + len(records)}, "
                    f"running total: {len(self.opportunities)}"
                )
                offset += page_size

                if self.reached_limit() or (total and offset >= total):
                    break

            except Exception as e:
                logger.error(f"Error at offset {offset}: {e}")
                break

    def parse_opportunity(self, record):
        try:
            title = clean_text(record.get('Title', ''))
            if not title:
                return None

            grant_url = (record.get('GrantURL') or '').strip()
            portal_id = record.get('PortalID', '')

            if grant_url:
                source_url = grant_url
            elif portal_id:
                source_url = f"https://grants.ca.gov/?portal_id={portal_id}"
            else:
                return None

            deadline_raw = record.get('ApplicationDeadline', '')
            deadline = None
            if deadline_raw:
                lowered = deadline_raw.strip().lower()
                if lowered not in ('ongoing', 'continuous', 'n/a', 'tbd', ''):
                    deadline = parse_date(deadline_raw)

            description = clean_text(record.get('Description', ''))
            if not description:
                description = clean_text(record.get('Purpose', ''))

            eligibility_parts = filter(None, [
                record.get('ApplicantType'),
                record.get('ApplicantTypeNotes'),
            ])
            eligibility = clean_text('; '.join(eligibility_parts)) or None

            category = clean_text(record.get('Categories', ''))
            if not category:
                category = categorize_opportunity(title, description or '')

            geography = clean_text(record.get('Geography', ''))
            location = (
                f"{self.location} - {geography}" if geography else self.location
            )

            return {
                'title': title,
                'organization': clean_text(record.get('AgencyDept', ''))
                    or self.organization,
                'description': description,
                'eligibility': eligibility,
                'funding_amount': clean_text(record.get('EstAvailFunds', '')),
                'deadline': deadline,
                'category': category,
                'location': location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': portal_id or None,
                'posted_date': parse_date(record.get('OpenDate', '')),
                'document_urls': [],
                'opportunity_type': self.opportunity_type,
            }
        except Exception as e:
            logger.error(f"Error parsing {self.state_name} API record: {e}")
            return None


# ---------------------------------------------------------------------------
# StateHTMLScraper — Static HTML pages (requests + BeautifulSoup)
# ---------------------------------------------------------------------------

class StateHTMLScraper(BaseScraper):
    """
    Scraper for states with static, server-rendered HTML pages.

    Supports parser modes: 'table', 'links', 'links_external'.
    """

    def __init__(self, config):
        super().__init__(config['source_name'])
        self.config = config
        self.state_name = config['name']
        self.organization = config['organization']
        self.location = config['location']
        self.url = config['url']
        self.opportunity_type = config.get('opportunity_type', 'grant')

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (HTML)...")
        try:
            response = self.fetch_page(self.url)
            if not response:
                logger.warning(f"Failed to fetch {self.url}")
                self.log_summary()
                return self.opportunities

            soup = self.parse_html(response.content)
            parser = self.config.get('parser', 'links')

            if parser == 'table':
                self._parse_table(soup)
            elif parser in ('links', 'links_external'):
                self._parse_links(soup, external_only=(parser == 'links_external'))
            else:
                logger.error(f"Unknown parser type: {parser}")

        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")

        self.log_summary()
        return self.opportunities

    def _parse_table(self, soup):
        selector = self.config.get('table_selector', 'table')
        tables = soup.select(selector)
        if not tables:
            logger.warning(f"{self.state_name}: no table found with '{selector}'")
            return

        table = tables[0]
        rows = table.find_all('tr')
        start = 1 if self.config.get('skip_header', True) else 0

        col_cat = self.config.get('col_category')
        col_title = self.config.get('col_title_link')
        col_desc = self.config.get('col_description')

        seen_urls = set()

        for row in rows[start:]:
            cells = row.find_all('td')
            if not cells:
                continue

            try:
                link_cell = cells[col_title] if col_title is not None and col_title < len(cells) else None
                link_tag = link_cell.find('a') if link_cell else None
                if not link_tag:
                    continue

                title = clean_text(link_tag.text)
                href = link_tag.get('href', '').strip()
                if not title or not href:
                    continue

                if not href.startswith('http'):
                    href = urllib.parse.urljoin(self.url, href)

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                category = None
                if col_cat is not None and col_cat < len(cells):
                    category = clean_text(cells[col_cat].text)

                description = None
                if col_desc is not None and col_desc < len(cells):
                    description = clean_text(cells[col_desc].text)

                if not category:
                    category = categorize_opportunity(title, description or '')

                opp = {
                    'title': title,
                    'organization': self.organization,
                    'description': description,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': None,
                    'category': category,
                    'location': self.location,
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': self.opportunity_type,
                }
                self._enrich_from_detail_page(opp)
                self.add_opportunity(opp)
                if self.reached_limit():
                    break
            except Exception as e:
                logger.debug(f"Skipping row in {self.state_name}: {e}")
                continue

    def _parse_links(self, soup, external_only=False):
        container_sel = self.config.get(
            'container_selector', '.content-area, main, article'
        )
        containers = soup.select(container_sel)
        if not containers:
            containers = [soup.body] if soup.body else []

        link_pattern = self.config.get('link_pattern', '')
        base_domain = urllib.parse.urlparse(self.url).netloc.lower()
        seen_urls = set()

        for container in containers:
            for link in container.find_all('a', href=True):
                href = link['href'].strip()
                title = clean_text(link.text)

                if not title or len(title) < 8:
                    continue
                if not href or href.startswith(('#', 'javascript', 'mailto:', 'tel:')):
                    continue

                if not href.startswith('http'):
                    href = urllib.parse.urljoin(self.url, href)

                skip_extensions = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')
                if any(href.lower().endswith(ext) for ext in skip_extensions):
                    continue

                if external_only:
                    link_domain = urllib.parse.urlparse(href).netloc.lower()
                    if link_domain == base_domain:
                        continue

                if link_pattern and not any(
                    p in href.lower() for p in link_pattern.split('|')
                ):
                    continue

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                category = categorize_opportunity(title, '')

                opp = {
                    'title': title,
                    'organization': self.organization,
                    'description': None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': None,
                    'category': category,
                    'location': self.location,
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': self.opportunity_type,
                }
                self._enrich_from_detail_page(opp)
                self.add_opportunity(opp)
                if self.reached_limit():
                    break

    def _enrich_from_detail_page(self, opp):
        """Visit source_url to extract description, doc links from the page."""
        url = opp.get('source_url', '')
        if not url:
            return
        try:
            time.sleep(random.uniform(1.0, 2.0))
            resp = self.fetch_page(url)
            if not resp:
                return
            soup = self.parse_html(resp.content)

            meta = soup.find('meta', attrs={'name': 'description'})
            if meta and meta.get('content'):
                desc = clean_text(meta['content'])
                if desc and len(desc) > 20:
                    opp['description'] = desc[:1000]

            if not opp.get('description'):
                for p in soup.find_all('p'):
                    text = clean_text(p.get_text())
                    if text and len(text) > 50:
                        opp['description'] = text[:1000]
                        break

            doc_urls = []
            for a in soup.find_all('a', href=True):
                h = a['href']
                if any(h.lower().endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    full = urllib.parse.urljoin(url, h)
                    if full not in doc_urls:
                        doc_urls.append(full)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]

            if opp.get('description'):
                opp['category'] = categorize_opportunity(opp['title'], opp['description'])

        except Exception as exc:
            logger.debug(f"Detail enrichment failed for {url}: {exc}")

    def parse_opportunity(self, element):
        """Required by BaseScraper ABC."""
        return None


# ---------------------------------------------------------------------------
# StateSeleniumScraper — JS-heavy portals (procurement, grants gateways)
# ---------------------------------------------------------------------------

class StateSeleniumScraper(BaseScraper):
    """Scraper for portals that require JavaScript rendering via headless Chrome."""

    def __init__(self, config):
        super().__init__(config['source_name'])
        self.config = config
        self.state_name = config['name']
        self.organization = config['organization']
        self.location = config['location']
        self.portal_url = config['url']
        self.wait_selector = config.get(
            'wait_selector', 'table, .search-results, main'
        )
        self.item_selector = config.get(
            'item_selector', 'table tbody tr, .result-item'
        )
        self.title_selector = config.get('title_selector', 'td a, a')
        self.opportunity_type = config.get('opportunity_type', 'grant')
        self.fallback_procurement_only = config.get(
            'fallback_procurement_only', False
        )
        self.max_parse_items = int(config.get('max_parse_items', 400))

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (Selenium)...")

        driver = _SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error(
                f"Selenium driver unavailable - skipping {self.state_name}"
            )
            self.log_summary()
            return self.opportunities

        try:
            self._scrape_with_driver(driver)
        except Exception as e:
            logger.error(f"Error scraping {self.state_name}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_with_driver(self, driver):
        """Navigate and extract. Returns False if driver.get failed, True otherwise."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, WebDriverException

        delay = random.uniform(*SELENIUM_DELAY_RANGE)
        logger.info(f"{self.state_name}: waiting {delay:.0f}s before request...")
        time.sleep(delay)

        try:
            driver.set_page_load_timeout(60)
            driver.get(self.portal_url)
        except WebDriverException as e:
            logger.error(f"{self.state_name}: page load failed - {e}")
            return False

        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.debug(f"{self.state_name}: readyState timeout, continuing anyway")

        try:
            wait_selectors = [s.strip() for s in self.wait_selector.split(',')]
            css = ', '.join(wait_selectors)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            )
        except TimeoutException:
            logger.warning(
                f"{self.state_name}: timed out waiting for content at {self.portal_url}"
            )

        time.sleep(random.uniform(4, 7))

        soup = self.parse_html(driver.page_source)
        self._extract_opportunities(soup)
        return True

    def _extract_opportunities(self, soup):
        item_selectors = [s.strip() for s in self.item_selector.split(',')]
        items = []
        for sel in item_selectors:
            items = soup.select(sel)
            if items:
                break

        if items:
            self._parse_items(items, soup)

        if not self.opportunities:
            logger.info(
                f"{self.state_name}: structured selectors found nothing, "
                f"trying link-extraction fallback..."
            )
            self._extract_links_fallback(soup)

        if not self.opportunities:
            logger.warning(
                f"{self.state_name}: no opportunities found at {self.portal_url}"
            )

    def _parse_items(self, items, soup):
        """Extract opportunities from structured items (table rows, cards, etc.)."""
        seen_urls = set()
        title_selectors = [s.strip() for s in self.title_selector.split(',')]
        if len(items) > self.max_parse_items:
            logger.info(
                f"{self.state_name}: limiting parse to {self.max_parse_items} "
                f"of {len(items)} matched items"
            )
            items = items[: self.max_parse_items]

        for item in items:
            try:
                link = None
                for sel in title_selectors:
                    found = item.select_one(sel)
                    if found and found.name == 'a' and found.get('href'):
                        link = found
                        break

                if not link:
                    all_links = item.find_all('a', href=True)
                    for a in all_links:
                        text = clean_text(a.text)
                        h = (a.get('href') or '').strip()
                        if text and len(text) >= 3 and h and h != '#':
                            link = a
                            break

                if not link:
                    continue

                title = clean_text(link.text)
                href = (link.get('href') or '').strip()

                if not title or len(title) < 3 or _title_is_garbage(title):
                    continue
                if not href or href == '#' or href.startswith('javascript'):
                    continue

                if not href.startswith('http'):
                    href = urllib.parse.urljoin(self.portal_url, href)

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                opp = self._build_opportunity(item, title, href)
                if opp:
                    self.add_opportunity(opp)
                if self.reached_limit():
                    break

            except Exception as e:
                logger.debug(f"Skipping item in {self.state_name}: {e}")
                continue

    _FALLBACK_MAX_LINKS = 200

    @staticmethod
    def _collect_doc_urls(container, base_url):
        """Find PDF/doc/spreadsheet links near an opportunity item."""
        doc_ext = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.ppt', '.pptx')
        doc_urls = []
        for a in container.find_all('a', href=True):
            h = a['href'].strip()
            if any(h.lower().endswith(ext) for ext in doc_ext):
                if not h.startswith('http'):
                    h = urllib.parse.urljoin(base_url, h)
                if h not in doc_urls:
                    doc_urls.append(h)
        return doc_urls

    def _extract_links_fallback(self, soup):
        """Fallback: extract all meaningful links from the page's main content."""
        containers = soup.select(
            'main, article, section, [role="main"], .content-area, .content, '
            '#content, .main-content, .page-content, .field-items, '
            '.entry-content, .site-content, .post-content, .page-wrapper, '
            '#main-content, #mainContent, .site-main'
        )
        if not containers:
            containers = [soup.body] if soup.body else []

        seen_urls = set()
        skip_ext = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js')
        doc_ext = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')
        nav_words = (
            'home', 'contact us', 'about us', 'login', 'sign in', 'register',
            'back to top', 'privacy policy', 'terms of', 'sitemap', 'menu',
            'skip to', 'accessibility', 'cookie', 'subscribe', 'follow us',
            'facebook', 'twitter', 'linkedin', 'instagram', 'youtube',
            'log in', 'sign up', 'forgot password',
        )

        page_doc_urls = self._collect_doc_urls(soup, self.portal_url)

        for container in containers:
            if len(seen_urls) >= self._FALLBACK_MAX_LINKS:
                break
            for link in container.find_all('a', href=True):
                if len(seen_urls) >= self._FALLBACK_MAX_LINKS:
                    break
                href = link['href'].strip()
                title = clean_text(link.text)

                if not title or len(title) < 6:
                    continue
                if not href or href.startswith(('#', 'javascript', 'mailto:', 'tel:')):
                    continue
                if not href.startswith('http'):
                    href = urllib.parse.urljoin(self.portal_url, href)
                if any(href.lower().endswith(ext) for ext in skip_ext):
                    continue
                if any(href.lower().endswith(ext) for ext in doc_ext):
                    continue

                lower_title = title.lower()
                if any(w in lower_title for w in nav_words):
                    continue

                if self.fallback_procurement_only and not _title_looks_like_procurement(
                    title
                ):
                    continue

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                parent = link.parent
                local_docs = self._collect_doc_urls(parent, self.portal_url) if parent else []

                category = categorize_opportunity(title, '')
                self.add_opportunity({
                    'title': title,
                    'organization': self.organization,
                    'description': None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': None,
                    'category': category,
                    'location': self.location,
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': local_docs or page_doc_urls[:5],
                    'opportunity_type': self.opportunity_type,
                })
                if self.reached_limit():
                    break

    def _build_opportunity(self, item, title, source_url):
        description = None
        deadline = None
        cells = item.find_all('td')

        if len(cells) >= 3:
            for cell in cells[1:]:
                text = clean_text(cell.text)
                if not text:
                    continue
                if not description and len(text) > 20:
                    description = text
                if not deadline:
                    parsed = parse_date(text)
                    if parsed:
                        deadline = parsed

        doc_urls = self._collect_doc_urls(item, self.portal_url)
        category = categorize_opportunity(title, description or '')

        return {
            'title': title,
            'organization': self.organization,
            'description': description,
            'eligibility': None,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': self.location,
            'source': self.source_name,
            'source_url': source_url,
            'opportunity_number': None,
            'posted_date': None,
            'document_urls': doc_urls,
            'opportunity_type': self.opportunity_type,
        }

    def parse_opportunity(self, element):
        """Required by BaseScraper ABC."""
        return None


# ---------------------------------------------------------------------------
# Factory + Cleanup
# ---------------------------------------------------------------------------

def create_state_scrapers(configs):
    """
    Create scraper instances from a list of config dicts.

    Each config must have at minimum: name, source_name, organization,
    location, method ('api'|'html'|'selenium'), and method-specific fields.
    """
    scrapers = []
    for cfg in configs:
        method = cfg.get('method', 'selenium')
        try:
            if method == 'api':
                scrapers.append(StateAPIScraper(cfg))
            elif method == 'html':
                scrapers.append(StateHTMLScraper(cfg))
            elif method == 'selenium':
                scrapers.append(StateSeleniumScraper(cfg))
            else:
                logger.warning(f"Unknown method '{method}' for {cfg.get('name')}")
        except Exception as e:
            logger.error(f"Failed to create scraper for {cfg.get('name')}: {e}")
    return scrapers


def cleanup_state_scrapers():
    """Close the shared Selenium driver (call after all state scrapers finish)."""
    _SeleniumDriverManager.quit()
