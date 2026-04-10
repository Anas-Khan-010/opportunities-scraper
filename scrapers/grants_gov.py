import re
import time
import random
from datetime import datetime
from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity
from database.db import db

# Selenium imports (only used as fallback)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)


class GrantsGovScraper(BaseScraper):
    """
    Robust scraper for Grants.gov — Federal grant opportunities.
    
    Architecture (three-tier enrichment):
        1. search2 API (POST) → paginated keyword search → basic fields
        2. fetchOpportunity API (POST) → full detail via REST (no browser)
           → description, eligibility, funding, deadline, documents
        3. Selenium fallback → only if the detail API fails for an opportunity
        4. Merge all sources → validate → return opportunities
    
    The detail API (tier 2) requires no authentication and works on any
    server without Chrome/Selenium, making it reliable on headless VPS.
    """

    # Labels to extract from Selenium detail page text (case-insensitive)
    DETAIL_LABELS = {
        'description': ['Description:'],
        'eligibility': [
            'Eligible Applicants:',
            'Additional Information on Eligibility:',
        ],
        'funding_amount': [
            'Award Ceiling:',
            'Estimated Total Program Funding:',
            'Award Floor:',
        ],
        'deadline': [
            'Current Closing Date for Applications:',
            'Original Closing Date for Applications:',
        ],
        'category': [
            'Opportunity Category:',
            'Category of Funding Activity:'
        ]
    }

    def __init__(self):
        super().__init__('Grants.gov')
        self.base_url = config.GRANTS_GOV_BASE_URL
        self.api_url = config.GRANTS_GOV_API_URL
        self.detail_api_url = config.GRANTS_GOV_DETAIL_API_URL
        self._driver = None

    # ─── Selenium Lifecycle ───────────────────────────────────────────

    def _init_driver(self):
        """Initialize a headless Chrome driver with stealth hardening. Returns True on success."""
        if self._driver is not None:
            return True
        try:
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--no-first-run')
            options.add_argument('--no-default-browser-check')
            options.add_argument('--lang=en-US,en')
            options.add_argument(f'--user-agent={config.USER_AGENTS[0]}')
            options.add_argument('--log-level=3')
            options.add_experimental_option(
                'excludeSwitches', ['enable-automation', 'enable-logging']
            )
            options.add_experimental_option('useAutomationExtension', False)

            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(60)
            self._apply_stealth_patches()
            logger.info("Selenium Chrome driver initialized successfully (stealth mode)")
            return True
        except WebDriverException as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            logger.warning("Selenium fallback disabled")
            self._driver = None
            return False

    def _apply_stealth_patches(self):
        """Inject JS to hide automation markers from page scripts."""
        if not self._driver:
            return
        try:
            self._driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                        "Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});"
                        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                        "window.chrome=window.chrome||{runtime:{}};"
                    )
                },
            )
        except Exception as e:
            logger.debug(f"Stealth patch skipped: {e}")

    def _quit_driver(self):
        """Safely close the Selenium driver."""
        if self._driver is not None:
            try:
                self._driver.quit()
                logger.info("Selenium Chrome driver closed")
            except Exception as e:
                logger.warning(f"Error closing Chrome driver: {e}")
            finally:
                self._driver = None

    # ─── Main Scrape Orchestrator ─────────────────────────────────────

    def scrape(self, keywords=None, max_pages=5):
        """
        Scrape grant opportunities from Grants.gov.
        
        Args:
            keywords: List of search keywords, or a single string.
                      Defaults to a broad set of 19 keywords.
            max_pages: Maximum number of API pages to fetch per keyword.
                       Each page returns up to 25 results.
        
        Returns:
            List of opportunity dicts ready for DB insertion.
        """
        if keywords is None:
            keywords = [
                "health", "education", "technology", "environment", "community",
                "research", "agriculture", "energy", "justice", "transportation",
                "housing", "veterans", "arts", "humanities", "small business",
                "infrastructure", "cybersecurity", "manufacturing", "workforce"
            ]
        elif isinstance(keywords, str):
            keywords = [keywords]

        logger.info(f"Starting {self.source_name} scraper with "
                    f"{len(keywords)} keyword(s), max {max_pages} pages each")
        logger.info(f"\n🚀 Starting {self.source_name} scraper with {len(keywords)} keyword(s), max {max_pages} pages each")

        # Selenium is only initialized on demand (if detail API fails)
        selenium_available = False

        seen_ids = set()
        keyword_results = {}
        api_detail_hits = 0
        api_detail_misses = 0

        try:
            for keyword in keywords:
                if self.reached_limit():
                    break
                logger.info(f"Searching keyword: '{keyword}'")
                logger.info(f"\n🔍 Searching keyword: '{keyword}'")
                keyword_count = 0
                sequential_duplicates = 0
                skip_keyword = False

                for page in range(max_pages):
                    if skip_keyword:
                        break

                    api_results = self._search_api(keyword, page)

                    if api_results is None:
                        logger.warning(f"API request failed for keyword='{keyword}', "
                                      f"page={page + 1} — skipping rest of this keyword")
                        logger.info(f"❌ API request failed for keyword='{keyword}', page={page + 1}")
                        break

                    if not api_results:
                        logger.info(f"ℹ️ No more results for '{keyword}' after page {page + 1}")
                        break

                    for opp_data in api_results:
                        opp_id = opp_data.get('id')

                        if opp_id in seen_ids:
                            continue
                        seen_ids.add(opp_id)

                        opportunity = self._parse_api_result(opp_data)
                        if opportunity is None:
                            continue

                        if db.opportunity_exists(opportunity['source_url']):
                            sequential_duplicates += 1
                            logger.info(f"  ⏭️  Skipped DB duplicate: {opportunity['title'][:50]}...")
                            if sequential_duplicates >= 10:
                                logger.info(f"  🛑 Hit 10 duplicates in a row. Skipping rest of keyword '{keyword}'.")
                                skip_keyword = True
                                break
                            continue

                        sequential_duplicates = 0

                        # ── Enrichment: API first, Selenium fallback ──
                        enriched = False
                        if opp_id:
                            details = self._fetch_detail_api(opp_id)
                            if details:
                                opportunity = self._merge_details(opportunity, details)
                                enriched = True
                                api_detail_hits += 1

                        if not enriched:
                            api_detail_misses += 1
                            if not selenium_available:
                                selenium_available = self._init_driver()
                            if selenium_available:
                                details = self._fetch_detail_page(opportunity['source_url'])
                                if details:
                                    opportunity = self._merge_details(opportunity, details)
                                    enriched = True

                        if not enriched:
                            logger.warning(f"  ⚠️ No enrichment for: {opportunity['title'][:50]}...")

                        if not opportunity.get('category'):
                            opportunity['category'] = categorize_opportunity(
                                opportunity['title'] or '',
                                opportunity['description'] or ''
                            )

                        is_new = self.add_opportunity(opportunity)
                        if is_new:
                            keyword_count += 1
                        logger.info(f"  ✅ Extracted: {opportunity['title'][:60]}...")

                        if self.reached_limit():
                            skip_keyword = True
                            break

                    logger.info(f"📄 Page {page + 1} complete. Total for '{keyword}' so far: {keyword_count}")

                keyword_results[keyword] = keyword_count
                logger.info(f"🏁 Keyword '{keyword}' complete. Found {keyword_count} new opportunities.")

        finally:
            self._quit_driver()

        logger.info(
            f"📊 Detail enrichment stats: API hits={api_detail_hits}, "
            f"API misses={api_detail_misses}"
        )
        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, element):
        """Required by BaseScraper. Delegates to _parse_api_result."""
        return self._parse_api_result(element)

    # ─── Search API Layer ─────────────────────────────────────────────

    def _search_api(self, keyword, page):
        """
        Fetch one page of results from the Grants.gov search2 API.
        
        Returns:
            List of opportunity dicts from API, or None on failure.
            Empty list means no more results.
        """
        payload = {
            "keyword": keyword,
            "oppStatuses": "forecasted|posted",
            "sortBy": "openDate|desc",
            "startRecordNum": page * 25,
            "rows": 25,
            "resultType": "json",
            "searchOnly": False,
        }

        try:
            response = self.fetch_page(self.api_url, method='POST', json=payload)
            if not response:
                return None

            response_json = response.json()
            data = response_json.get('data', {})

            opp_hits = data.get('oppHits')
            if not opp_hits:
                return []

            return opp_hits

        except ValueError as e:
            logger.error(f"Invalid JSON response from API (keyword='{keyword}', "
                        f"page={page + 1}): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in API request (keyword='{keyword}', "
                        f"page={page + 1}): {e}")
            return None

    def _parse_api_result(self, opp_data):
        """
        Parse one opportunity from search API response into our standard dict.
        
        Returns dict or None if parsing fails.
        """
        try:
            opp_id = opp_data.get('id')
            title = clean_text(opp_data.get('title', ''))

            if not title or not opp_id:
                logger.warning(f"Skipping opportunity with missing title or ID: {opp_data}")
                return None

            opportunity_number = clean_text(opp_data.get('number', ''))
            source_url = f"{self.base_url}/search-results-detail/{opp_id}"
            agency = clean_text(opp_data.get('agency', ''))
            posted_date = parse_date(opp_data.get('openDate'))
            deadline = parse_date(opp_data.get('closeDate'))

            return {
                'title': title,
                'organization': agency,
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': 'General',
                'location': 'United States',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opportunity_number,
                'posted_date': posted_date,
                'document_urls': [],
                'opportunity_type': 'grant',
            }

        except Exception as e:
            logger.error(f"Error parsing API result: {e} | Data: {opp_data}")
            return None

    # ─── Detail API Layer (primary enrichment — no Selenium) ──────────

    _DETAIL_API_MAX_RETRIES = 4
    _DETAIL_API_BACKOFF_BASE = 3  # seconds

    def _fetch_detail_api(self, opportunity_id):
        """
        Fetch full opportunity details from the Grants.gov fetchOpportunity API.
        
        This is a simple POST request — no browser, no Selenium, no JS rendering.
        Works identically on any server (local, Chris's Webmin, CI, etc.).
        
        Includes 429/rate-limit handling with exponential backoff and
        Retry-After header respect.
        
        Returns:
            Dict with detail fields, or None on failure.
        """
        payload = {"opportunityId": int(opportunity_id)}

        for attempt in range(self._DETAIL_API_MAX_RETRIES):
            try:
                # Polite delay between detail API calls to avoid hammering
                time.sleep(random.uniform(1.0, 2.5))

                response = self.session.post(
                    self.detail_api_url, json=payload, timeout=30
                )

                # Handle rate limiting explicitly
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            wait_secs = int(retry_after)
                        except ValueError:
                            wait_secs = self._DETAIL_API_BACKOFF_BASE * (2 ** attempt)
                    else:
                        wait_secs = self._DETAIL_API_BACKOFF_BASE * (2 ** attempt)
                    wait_secs = min(wait_secs, 120)
                    logger.warning(
                        f"Rate limited (429) on fetchOpportunity ID {opportunity_id}, "
                        f"waiting {wait_secs}s (attempt {attempt + 1}/{self._DETAIL_API_MAX_RETRIES})"
                    )
                    time.sleep(wait_secs)
                    continue

                if response.status_code == 503:
                    wait_secs = self._DETAIL_API_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        f"Service unavailable (503) on fetchOpportunity ID {opportunity_id}, "
                        f"waiting {wait_secs}s (attempt {attempt + 1}/{self._DETAIL_API_MAX_RETRIES})"
                    )
                    time.sleep(wait_secs)
                    continue

                response.raise_for_status()

                resp_json = response.json()
                if resp_json.get('errorcode') and resp_json['errorcode'] != 0:
                    logger.warning(
                        f"fetchOpportunity error for ID {opportunity_id}: "
                        f"{resp_json.get('msg', 'unknown')}"
                    )
                    return None

                data = resp_json.get('data', {})
                if not data:
                    return None

                return self._parse_detail_api_response(data)

            except ValueError as e:
                logger.warning(f"fetchOpportunity JSON decode error for ID {opportunity_id}: {e}")
                return None
            except Exception as e:
                wait_secs = self._DETAIL_API_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"fetchOpportunity attempt {attempt + 1} failed for ID {opportunity_id}: {e}, "
                    f"retrying in {wait_secs}s"
                )
                if attempt < self._DETAIL_API_MAX_RETRIES - 1:
                    time.sleep(wait_secs)
                else:
                    logger.error(f"fetchOpportunity gave up on ID {opportunity_id} after {self._DETAIL_API_MAX_RETRIES} attempts")
                    return None

        logger.error(f"fetchOpportunity exhausted retries for ID {opportunity_id}")
        return None

    def _parse_detail_api_response(self, data):
        """
        Extract detail fields from the fetchOpportunity API response.
        
        Opportunities can be either "synopsis" or "forecast" type.
        The detail data lives under data.synopsis or data.forecast respectively,
        with slightly different field names for description.
        """
        details = {}

        # Pick the right detail block — synopsis or forecast
        synopsis = data.get('synopsis') or {}
        forecast = data.get('forecast') or {}
        detail_block = synopsis or forecast

        if not detail_block:
            return None

        # Description — synopsis uses synopsisDesc, forecast uses forecastDesc
        desc = (
            detail_block.get('synopsisDesc')
            or detail_block.get('forecastDesc')
            or ''
        )
        if desc:
            desc = self._strip_html(desc)
            if desc and len(desc) >= 10:
                details['description'] = clean_text(desc)

        # Eligibility — combine applicant type labels + free-text eligibility
        eligibility_parts = []
        applicant_types = detail_block.get('applicantTypes', [])
        if applicant_types:
            for at in applicant_types:
                desc_text = at.get('description', '')
                if desc_text:
                    eligibility_parts.append(desc_text)

        additional_elig = detail_block.get('applicantEligibilityDesc', '')
        if additional_elig:
            additional_elig = self._strip_html(additional_elig)
            if additional_elig:
                eligibility_parts.append(additional_elig)

        if eligibility_parts:
            details['eligibility'] = '\n'.join(eligibility_parts)

        # Funding amount — prefer ceiling, fall back to floor
        ceiling = detail_block.get('awardCeiling') or detail_block.get('awardCeilingFormatted')
        floor = detail_block.get('awardFloor') or detail_block.get('awardFloorFormatted')
        funding_val = ceiling or floor
        if funding_val and str(funding_val) != '0':
            details['funding_amount'] = self._clean_funding(str(funding_val))

        # Deadline — synopsis uses responseDate, forecast uses estApplicationResponseDate
        close_date_str = (
            detail_block.get('responseDateDesc')
            or detail_block.get('responseDate')
            or detail_block.get('estApplicationResponseDate')
            or detail_block.get('estApplicationResponseDateDesc')
        )
        if close_date_str:
            parsed_deadline = parse_date(close_date_str)
            if parsed_deadline:
                details['deadline'] = parsed_deadline

        # Category
        opp_category = data.get('opportunityCategory', {})
        cat_desc = opp_category.get('description', '')
        if cat_desc:
            details['category'] = clean_text(cat_desc)
        else:
            funding_cats = detail_block.get('fundingActivityCategories', [])
            if funding_cats:
                cat_names = [fc.get('description', '') for fc in funding_cats if fc.get('description')]
                if cat_names:
                    details['category'] = ', '.join(cat_names)

        # Document URLs from attachment folders
        doc_urls = []
        for folder in data.get('synopsisAttachmentFolders', []):
            for att in folder.get('synopsisAttachments', []):
                filename = att.get('fileName', '')
                att_id = att.get('id')
                if filename and att_id:
                    doc_url = (
                        f"{self.base_url}/grantsws/rest/opportunity/att/download/"
                        f"{att_id}"
                    )
                    doc_urls.append(doc_url)
        if doc_urls:
            details['document_urls'] = doc_urls

        return details if details else None

    def _strip_html(self, text):
        """Remove HTML tags and entities from a string and clean up whitespace."""
        if not text:
            return ''
        import html
        cleaned = re.sub(r'<[^>]+>', ' ', text)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    # ─── Selenium Detail Page Layer (fallback only) ───────────────────

    def _fetch_detail_page(self, detail_url):
        """
        Fetch and parse a Grants.gov detail page using Selenium.
        Only used as fallback when the fetchOpportunity API fails.
        
        Returns:
            Dict with extracted detail fields, or None on failure.
        """
        if self._driver is None:
            return None

        try:
            self._driver.get(detail_url)

            try:
                WebDriverWait(self._driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except TimeoutException:
                logger.debug(f"readyState timeout for {detail_url}, continuing anyway")

            try:
                WebDriverWait(self._driver, config.GRANTS_GOV_DETAIL_PAGE_TIMEOUT).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'td, .usa-layout-docs__main, h1')
                    )
                )
            except TimeoutException:
                logger.warning(f"Detail page timed out waiting for container: {detail_url}")
                return None

            detail_label_timeout = max(15, config.GRANTS_GOV_DETAIL_PAGE_TIMEOUT)
            labels_found = False
            try:
                WebDriverWait(self._driver, detail_label_timeout).until(
                    lambda d: any(
                        kw in (d.page_source or '').lower()
                        for kw in ['description:', 'eligible applicants:', 'award ceiling:']
                    )
                )
                labels_found = True
            except TimeoutException:
                logger.warning(
                    f"Detail labels never appeared after {detail_label_timeout}s: {detail_url} "
                    f"— page may be blocked or JS failed to render"
                )

            render_wait = config.GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT + 3
            if not labels_found:
                render_wait += 5
            time.sleep(render_wait)

            page_source = self._driver.page_source or ''
            try:
                soup = self.parse_html(page_source)
                if soup and soup.body:
                    page_text = soup.body.get_text(separator='\n', strip=True)
                else:
                    page_text = ""
            except Exception as e:
                logger.warning(f"Failed to parse page source: {e}")
                return None

            if not page_text or len(page_text) < 100:
                logger.warning(f"Detail page appears empty ({len(page_text)} chars): {detail_url}")
                snippet = page_source[:500] if page_source else '(no source)'
                logger.debug(f"Page source snippet: {snippet}")
                return None

            details = self._parse_detail_text(page_text)

            if not details.get('description') and not details.get('eligibility'):
                logger.warning(
                    f"Parsed detail page but got no description/eligibility: {detail_url} "
                    f"(page_text length={len(page_text)})"
                )

            doc_urls = self._extract_document_urls()
            if doc_urls:
                details['document_urls'] = doc_urls

            return details

        except TimeoutException:
            logger.warning(f"Page load timed out: {detail_url}")
            return None
        except WebDriverException as e:
            logger.error(f"Selenium error on detail page {detail_url}: {e}")
            self._recover_driver()
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching detail page {detail_url}: {e}")
            return None

    def _parse_detail_text(self, page_text):
        """
        Parse the rendered page text to extract structured fields.
        
        The Grants.gov detail page renders as lines like:
            Label:
            Value text here
        or:
            Label: Value text here
        """
        details = {}
        lines = page_text.split('\n')

        for field_name, label_options in self.DETAIL_LABELS.items():
            value = self._find_label_value(lines, label_options)
            if value:
                if field_name == 'funding_amount':
                    details[field_name] = self._clean_funding(value)
                elif field_name == 'deadline':
                    parsed = parse_date(value)
                    if parsed:
                        details[field_name] = parsed
                elif field_name == 'eligibility':
                    details[field_name] = clean_text(value, preserve_newlines=True)
                else:
                    details[field_name] = clean_text(value)

        return details

    def _find_label_value(self, lines, label_options):
        """
        Search through page text lines for a label and return its value.
        
        Handles two formats:
            1. "Label: Value on same line"
            2. "Label:" on one line, value on the next line(s)
        """
        for label in label_options:
            label_lower = label.lower().rstrip(':')

            for i, line in enumerate(lines):
                stripped = line.strip()
                stripped_lower = stripped.lower()

                if label_lower not in stripped_lower:
                    continue

                label_pos = stripped_lower.find(label_lower)
                after_label = stripped[label_pos + len(label_lower):].strip()
                if after_label.startswith(':'):
                    after_label = after_label[1:].strip()

                value_parts = []
                if after_label and self._is_valid_value(after_label):
                    value_parts.append(after_label)

                for j in range(i + 1, min(i + 40, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        if value_parts:
                            break
                        continue
                    if self._is_known_label(next_line):
                        break
                    value_parts.append(next_line)

                if value_parts:
                    return '\n'.join(value_parts)

        return None

    def _is_known_label(self, text):
        """Check if a line of text is a known label header."""
        text_lower = text.lower().strip()
        all_labels = []
        for labels in self.DETAIL_LABELS.values():
            all_labels.extend(labels)

        section_headers = [
            'eligibility', 'additional information', 'agency name',
            'description', 'grantor contact', 'link to additional',
            'version', 'posted date', 'last updated', 'archive date',
            'award ceiling', 'award floor', 'estimated total',
            'category explanation', 'expected number of awards',
            'assistance listings', 'cost sharing or matching requirements',
            'funding instrument type'
        ]
        all_labels.extend(section_headers)

        for label in all_labels:
            if text_lower.startswith(label.lower().rstrip(':')):
                return True
        return False

    def _is_valid_value(self, text):
        """Check if extracted text is a valid value (not garbage/fragment)."""
        if not text or len(text) < 5:
            return False
        alnum_count = sum(1 for c in text if c.isalnum())
        if alnum_count < 3:
            return False
        if text[0] in '"\')}]':
            return False
        return True

    def _extract_document_urls(self):
        """Extract document/attachment URLs from the current Selenium page."""
        try:
            links = self._driver.find_elements(By.CSS_SELECTOR, 'a[href]')
            doc_urls = []
            for link in links:
                href = link.get_attribute('href') or ''
                if any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '/attachment']):
                    if href not in doc_urls:
                        doc_urls.append(href)
            return doc_urls
        except Exception:
            return []

    def _clean_funding(self, value):
        """
        Clean and normalize a funding amount string.
        
        Input examples: "$ 300,000", "$5,000,000", "300000", "$1M"
        Output: "$300,000", "$5,000,000", "$300,000", "$1M"
        """
        if not value:
            return None

        value = value.strip()

        if '$' in value:
            value = re.sub(r'\$\s+', '$', value)
            return value

        try:
            num = float(value.replace(',', ''))
            if num >= 1:
                return f"${num:,.0f}"
        except ValueError:
            pass

        return value if value else None

    def _recover_driver(self):
        """Attempt to recover from a Selenium crash."""
        logger.info("Attempting to recover Selenium driver...")
        self._quit_driver()
        if self._init_driver():
            logger.info("Selenium driver recovered successfully")
        else:
            logger.warning("Selenium driver recovery failed — "
                         "continuing without Selenium fallback")

    # ─── Data Merging ─────────────────────────────────────────────────

    def _merge_details(self, opportunity, details):
        """
        Merge detail data into the opportunity dict.
        
        Rules:
            - Detail values fill in empty/None API fields.
            - Never overwrite a good value with None.
        """
        for field in ['description', 'eligibility', 'funding_amount']:
            detail_val = details.get(field)
            if detail_val and not opportunity.get(field):
                opportunity[field] = detail_val

        if details.get('category'):
            opportunity['category'] = details.get('category')

        detail_deadline = details.get('deadline')
        if detail_deadline and not opportunity.get('deadline'):
            opportunity['deadline'] = detail_deadline

        detail_docs = details.get('document_urls', [])
        if detail_docs:
            existing = opportunity.get('document_urls', []) or []
            merged = list(set(existing + detail_docs))
            opportunity['document_urls'] = merged

        return opportunity


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Grants.gov scraper standalone.",
        epilog=(
            "Examples:\n"
            "  python -m scrapers.grants_gov                          # full run, 19 keywords, max 3 pages\n"
            "  python -m scrapers.grants_gov --keywords health energy # only 2 keywords\n"
            "  python -m scrapers.grants_gov --max-pages 1 --dry-run  # quick test, no DB writes\n"
            "  python -m scrapers.grants_gov --dry-run --keywords health --max-pages 1  # minimal test\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--keywords', nargs='+', default=None,
        help='Search keywords (default: all 19 built-in keywords)',
    )
    parser.add_argument(
        '--max-pages', type=int, default=3,
        help='Max API pages per keyword, 25 results each (default: 3)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Scrape and print results but do NOT write to Supabase',
    )
    args = parser.parse_args()

    if args.dry_run:
        print("🧪 DRY-RUN MODE — results will be printed but NOT saved to Supabase\n")
        def _dry_add(self, opp):
            self.opportunities.append(opp)
            self._new_count += 1
            return True
        BaseScraper.add_opportunity = _dry_add
        db.opportunity_exists = lambda *a, **kw: False

    scraper = GrantsGovScraper()

    try:
        opps = scraper.scrape(keywords=args.keywords, max_pages=args.max_pages)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped manually!")
        opps = scraper.opportunities
    except Exception as e:
        print(f"\n\n💥 Crashed: {e}")
        opps = scraper.opportunities

    print(f"\n{'=' * 60}")
    print(f"Total opportunities collected: {len(opps)}")
    print(f"{'=' * 60}\n")

    for i, opp in enumerate(opps[:5]):
        print(f"--- #{i + 1} ---")
        for k, v in opp.items():
            val = str(v)
            if len(val) > 200:
                val = val[:200] + '...'
            print(f"  {k}: {val}")
        print()

    if len(opps) > 5:
        print(f"  ... and {len(opps) - 5} more.\n")

    if args.dry_run:
        print("🧪 Dry run complete — nothing was written to Supabase.")
    else:
        print(f"✅ All {len(opps)} opportunities were saved to Supabase during scraping.")
        try:
            print(f"📊 DB Stats: {db.get_stats()}")
        except Exception:
            pass

    sys.exit(0)
