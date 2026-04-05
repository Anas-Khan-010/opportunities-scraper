import re
import time
from datetime import datetime
from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity
from database.db import db

# Selenium imports
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
    
    Architecture:
        1. search2 API (POST) → paginated keyword search → basic fields
        2. Selenium (per opportunity) → JS-rendered detail page → description, 
           eligibility, funding, document links
        3. Merge both sources → validate → return opportunities
    
    Graceful degradation:
        - If Selenium fails for ANY reason, the opportunity is still returned
          with API-only data (description/eligibility will be empty).
        - Each opportunity is isolated — one failure never crashes the batch.
    """

    # Labels to extract from detail page text (case-insensitive matching)
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
        self._driver = None

    # ─── Selenium Lifecycle ───────────────────────────────────────────

    def _init_driver(self):
        """Initialize a headless Chrome driver. Returns True on success."""
        if self._driver is not None:
            return True
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            # Suppress noisy Chrome logs
            options.add_argument('--log-level=3')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])

            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(30)
            logger.info("Selenium Chrome driver initialized successfully")
            return True
        except WebDriverException as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            logger.warning("Continuing in API-only mode (no detail page scraping)")
            self._driver = None
            return False

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
                      Defaults to ["health", "education", "technology", 
                      "environment", "community"].
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

        # Initialize Selenium once for all detail fetches
        selenium_available = self._init_driver()
        if not selenium_available:
            logger.warning("Detail page scraping disabled — API-only mode")
            logger.info("⚠️ Detail page scraping disabled — running in API-only mode")
        else:
            logger.info("✅ Chrome driver initialized")

        seen_ids = set()  # Track IDs across keywords to avoid duplicate processing
        keyword_results = {}

        try:
            for keyword in keywords:
                logger.info(f"Searching keyword: '{keyword}'")
                logger.info(f"\n🔍 Searching keyword: '{keyword}'")
                keyword_count = 0
                sequential_duplicates = 0
                skip_keyword = False

                for page in range(max_pages):
                    if skip_keyword:
                        break
                        
                    # Step 1: Fetch a page of results from the API
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

                        # Skip if already processed in this current run
                        if opp_id in seen_ids:
                            continue
                        seen_ids.add(opp_id)

                        # Step 2: Parse API fields into opportunity dict
                        opportunity = self._parse_api_result(opp_data)
                        if opportunity is None:
                            continue

                        # DB Deduplication Check: if it already exists in Supabase, skip Selenium
                        if db.opportunity_exists(opportunity['source_url']):
                            sequential_duplicates += 1
                            logger.info(f"  ⏭️  Skipped DB duplicate: {opportunity['title'][:50]}...")
                            
                            # If we hit 10 duplicates in a row, assume everything older is also a duplicate
                            if sequential_duplicates >= 10:
                                logger.info(f"  🛑 Hit 10 duplicates in a row. Skipping rest of keyword '{keyword}'.")
                                skip_keyword = True
                                break
                            continue
                        
                        # Not a duplicate, reset the duplicate counter
                        sequential_duplicates = 0

                        # Step 3: Enrich with detail page (Selenium)
                        if selenium_available:
                            details = self._fetch_detail_page(opportunity['source_url'])
                            if details:
                                opportunity = self._merge_details(opportunity, details)

                        # Step 4: Auto-categorize only if no official category was found
                        if not opportunity.get('category'):
                            opportunity['category'] = categorize_opportunity(
                                opportunity['title'] or '',
                                opportunity['description'] or ''
                            )

                        self.opportunities.append(opportunity)
                        keyword_count += 1
                        logger.info(f"  ✅ Extracted: {opportunity['title'][:60]}...")

                    logger.info(f"📄 Page {page + 1} complete. Total for '{keyword}' so far: {keyword_count}")
                    
                keyword_results[keyword] = keyword_count
                logger.info(f"🏁 Keyword '{keyword}' complete. Found {keyword_count} new opportunities.")

        finally:
            # Always clean up Selenium
            self._quit_driver()

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, element):
        """Required by BaseScraper. Delegates to _parse_api_result."""
        return self._parse_api_result(element)

    # ─── API Layer ────────────────────────────────────────────────────

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
            # JSON decode error
            logger.error(f"Invalid JSON response from API (keyword='{keyword}', "
                        f"page={page + 1}): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in API request (keyword='{keyword}', "
                        f"page={page + 1}): {e}")
            return None

    def _parse_api_result(self, opp_data):
        """
        Parse one opportunity from API response into our standard dict.
        
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

    # ─── Selenium Detail Page Layer ───────────────────────────────────

    def _fetch_detail_page(self, detail_url):
        """
        Fetch and parse a Grants.gov detail page using Selenium.
        
        Returns:
            Dict with extracted detail fields, or None on failure.
            The dict may contain only SOME fields if parsing is partial.
        """
        if self._driver is None:
            return None

        try:
            self._driver.get(detail_url)

            # Wait for main content to render
            try:
                WebDriverWait(self._driver, config.GRANTS_GOV_DETAIL_PAGE_TIMEOUT).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'td, .usa-layout-docs__main, h1')
                    )
                )
            except TimeoutException:
                logger.warning(f"Detail page timed out: {detail_url}")
                return None

            # Give JS a bit more time to finish rendering
            time.sleep(config.GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT)

            # Extract the full body text using BeautifulSoup to preserve <br> as newlines
            try:
                soup = self.parse_html(self._driver.page_source)
                if soup and soup.body:
                    page_text = soup.body.get_text(separator='\n', strip=True)
                else:
                    page_text = ""
            except Exception as e:
                logger.warning(f"Failed to parse page source: {e}")
                return None

            if not page_text or len(page_text) < 100:
                logger.warning(f"Detail page appears empty: {detail_url}")
                return None

            # Parse the text into structured fields
            details = self._parse_detail_text(page_text)

            # Also try to extract document/attachment URLs from the page source
            doc_urls = self._extract_document_urls()
            if doc_urls:
                details['document_urls'] = doc_urls

            return details

        except TimeoutException:
            logger.warning(f"Page load timed out: {detail_url}")
            return None
        except WebDriverException as e:
            logger.error(f"Selenium error on detail page {detail_url}: {e}")
            # Attempt to recover the driver for next opportunity
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
        
        We extract values by finding known label strings and taking
        the text that follows them.
        """
        details = {}
        lines = page_text.split('\n')

        for field_name, label_options in self.DETAIL_LABELS.items():
            value = self._find_label_value(lines, label_options)
            if value:
                # For funding, try to format as a clean dollar amount
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

                # Check if this line contains the label
                if label_lower not in stripped_lower:
                    continue

                # Format 1: "Label: Value" on same line
                # Find the label text and take everything after it
                label_pos = stripped_lower.find(label_lower)
                after_label = stripped[label_pos + len(label_lower):].strip()
                # Remove leading colon if present
                if after_label.startswith(':'):
                    after_label = after_label[1:].strip()

                value_parts = []
                if after_label and self._is_valid_value(after_label):
                    value_parts.append(after_label)

                # Format 2: Value is on the next non-empty line(s) (or continues from Format 1)
                for j in range(i + 1, min(i + 40, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        if value_parts:
                            break  # End of value block
                        continue  # Skip empty lines before value
                    
                    # Stop if we hit another known label
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
        
        # Also check for common section headers
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
        """
        Check if extracted text is a valid value (not garbage/fragment).
        
        Rejects:
            - Text shorter than 5 chars
            - Text that is mostly punctuation/quotes
            - Text that doesn't contain any alphanumeric content
        """
        if not text or len(text) < 5:
            return False
        # Count alphanumeric characters
        alnum_count = sum(1 for c in text if c.isalnum())
        if alnum_count < 3:
            return False
        # Reject if it starts with a quote or closing paren (likely a fragment)
        if text[0] in '"\')}]':
            return False
        return True

    def _extract_document_urls(self):
        """Extract document/attachment URLs from the current page."""
        try:
            links = self._driver.find_elements(By.CSS_SELECTOR, 'a[href]')
            doc_urls = []
            for link in links:
                href = link.get_attribute('href') or ''
                # Look for PDF, document, or attachment links
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
        
        # If it already has a $ sign, clean up spacing
        if '$' in value:
            # Remove spaces between $ and numbers: "$ 300,000" -> "$300,000"
            value = re.sub(r'\$\s+', '$', value)
            return value
        
        # If it's a plain number, format it
        try:
            # Remove commas and try to parse
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
                         "continuing in API-only mode")

    # ─── Data Merging ─────────────────────────────────────────────────

    def _merge_details(self, opportunity, details):
        """
        Merge detail page data into the opportunity dict.
        
        Rules:
            - Detail page values override API values ONLY if the API value 
              is empty/None and the detail value is non-empty.
            - For deadline: detail page may have more accurate date.
            - Never overwrite a good value with None.
        """
        for field in ['description', 'eligibility', 'funding_amount']:
            detail_val = details.get(field)
            if detail_val and not opportunity.get(field):
                opportunity[field] = detail_val

        # Category: always prefer detail page over auto-guess
        if details.get('category'):
            opportunity['category'] = details.get('category')

        # Deadline: prefer detail page if API didn't have one
        detail_deadline = details.get('deadline')
        if detail_deadline and not opportunity.get('deadline'):
            opportunity['deadline'] = detail_deadline

        # Document URLs: merge
        detail_docs = details.get('document_urls', [])
        if detail_docs:
            existing = opportunity.get('document_urls', []) or []
            merged = list(set(existing + detail_docs))
            opportunity['document_urls'] = merged

        return opportunity


if __name__ == "__main__":
    from database.db import db
    import sys

    scraper = GrantsGovScraper()
    
    try:
        # Scrape with default keywords (all 19 of them) and max 3 pages each
        opps = scraper.scrape(max_pages=3)
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
                print(f"  {k}: {str(v)[:150]}")
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
        sys.exit(0 if inserted > 0 or len(opps) == 0 else 1)
