import re
import time
import random
import html as html_lib
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
        2. noticedesc API (v1) per opportunity -> fetch HTML description
        3. Parse HTML description into plain text
        4. Extract resourceLinks for document downloads
    
    Rate-limit awareness:
        SAM.gov enforces DAILY API call limits (not per-minute):
          - Basic key: 10 calls/day
          - Entity Registration key: 1,000 calls/day
          - Federal key (.gov/.mil): 10,000 calls/day
        
        Both the search endpoint and the noticedesc endpoint count toward
        the same daily quota. A single run budgets its calls via
        SAM_GOV_MAX_REQUESTS to avoid exhausting the key.
    """

    _DESC_BACKOFF_BASE = 5
    RATE_LIMITED = 'RATE_LIMITED'

    def __init__(self):
        super().__init__('SAM.gov')
        self.base_url = config.SAM_GOV_BASE_URL
        self.api_url = config.SAM_GOV_API_URL
        self.api_key = config.SAM_GOV_API_KEY
        self._opp_delay = config.SAM_GOV_OPP_DELAY
        self._page_delay = config.SAM_GOV_PAGE_DELAY

    def scrape(self, max_pages=5):
        """Scrape contract opportunities from SAM.gov.

        Uses an API call budget (SAM_GOV_MAX_REQUESTS) shared across
        search calls AND description fetches. Each search page costs 1 call,
        each description fetch costs 1 call.

        With a basic key (10/day), a typical budget of 10 means:
          - 1 search call + up to 9 description fetches = 10 total
        """
        logger.info(f"Starting {self.source_name} scraper...")

        if not self.api_key:
            logger.warning("SAM.gov API key not configured. Get free key at https://sam.gov/data-services/")
            logger.warning("Add SAM_GOV_API_KEY to .env file to enable this scraper")
            return self.opportunities

        api_budget = config.SAM_GOV_MAX_REQUESTS
        api_calls_made = 0

        today = datetime.now()
        posted_to = today.strftime('%m/%d/%Y')
        posted_from = (today - timedelta(days=180)).strftime('%m/%d/%Y')

        logger.info(f"Searching from {posted_from} to {posted_to}")
        logger.info(
            f"API budget: {api_budget} total calls this run "
            f"(search + descriptions combined)"
        )

        sequential_duplicates = 0
        desc_fetched = 0
        desc_skipped_budget = 0

        rate_limited = False

        for page in range(max_pages):
            if rate_limited:
                break
            if api_calls_made >= api_budget:
                logger.info(f"API budget exhausted ({api_calls_made}/{api_budget}). Stopping.")
                break

            try:
                params = {
                    'api_key': self.api_key,
                    'limit': 50,
                    'offset': page * 50,
                    'postedFrom': posted_from,
                    'postedTo': posted_to,
                }

                response = self._api_call_get(self.api_url, params=params)

                if response is self.RATE_LIMITED:
                    rate_limited = True
                    break

                api_calls_made += 1
                remaining = api_budget - api_calls_made

                if not response:
                    logger.warning(f"Failed to fetch page {page + 1}")
                    continue

                data = response.json()

                if 'opportunitiesData' not in data or not data['opportunitiesData']:
                    logger.info(f"No more opportunities found on page {page + 1}")
                    break

                opps_data = data['opportunitiesData']
                logger.info(
                    f"Page {page + 1}: {len(opps_data)} opportunities "
                    f"(API calls: {api_calls_made}/{api_budget}, "
                    f"{remaining} remaining for descriptions)"
                )

                for opp in opps_data:
                    if rate_limited:
                        break

                    ui_link = opp.get('uiLink')
                    if not ui_link:
                        ui_link = f"{self.base_url}/workspace/contract/opp/{opp.get('noticeId')}/view"

                    if db.opportunity_exists(ui_link):
                        sequential_duplicates += 1
                        if sequential_duplicates >= 20:
                            logger.info("Hit 20 duplicates in a row. Stopping scraper.")
                            self.log_summary()
                            return self.opportunities
                        continue

                    sequential_duplicates = 0

                    can_fetch_desc = api_calls_made < api_budget
                    opportunity = self.parse_opportunity(opp, fetch_description=can_fetch_desc)

                    if opportunity:
                        desc_val = opportunity.get('description')

                        if desc_val is self.RATE_LIMITED:
                            opportunity['description'] = None
                            rate_limited = True
                            logger.info("Rate limited during description fetch. "
                                       "Saving remaining opportunities without descriptions.")

                        if can_fetch_desc and not rate_limited:
                            api_calls_made += 1
                            if desc_val and desc_val is not self.RATE_LIMITED:
                                desc_fetched += 1
                        elif not can_fetch_desc:
                            desc_skipped_budget += 1

                        self.add_opportunity(opportunity)
                        logger.info(
                            f"  ✅ Extracted: {opportunity['title'][:50]}... "
                            f"[desc={'✓' if opportunity.get('description') else '✗'}] "
                            f"({api_calls_made}/{api_budget} calls used)"
                        )

                    if self.reached_limit() or api_calls_made >= api_budget:
                        if api_calls_made >= api_budget:
                            logger.info(f"API budget exhausted mid-page ({api_calls_made}/{api_budget}).")
                        break

                if not rate_limited and api_calls_made < api_budget and page < max_pages - 1:
                    logger.info(f"Waiting {self._page_delay}s before next search page...")
                    time.sleep(self._page_delay)

            except Exception as e:
                logger.error(f"Error scraping page {page + 1}: {e}")
                continue

        logger.info(
            f"📊 SAM.gov run complete: {api_calls_made} API calls used of {api_budget} budget. "
            f"Descriptions fetched: {desc_fetched}, skipped (budget): {desc_skipped_budget}"
        )
        self.log_summary()
        return self.opportunities

    def _api_call_get(self, url, params=None):
        """Make a GET API call with rate-limit handling.

        Returns:
            Response object on success.
            None on 404 or non-retryable failure.
            self.RATE_LIMITED on 429 (caller should stop the entire run).
        """
        for attempt in range(3):
            try:
                delay = self._opp_delay + random.uniform(1.0, 3.0)
                time.sleep(delay)
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 404:
                    logger.debug(f"404 — no content at {url.split('?')[0]}")
                    return None

                if response.status_code == 429:
                    try:
                        body = response.json()
                        reset_time = body.get('nextAccessTime', 'unknown')
                        logger.error(
                            f"🛑 RATE LIMITED (429). Daily quota exhausted. "
                            f"Resets at: {reset_time}. Stopping all API calls."
                        )
                    except Exception:
                        logger.error("🛑 RATE LIMITED (429). Daily quota exhausted. Stopping all API calls.")
                    return self.RATE_LIMITED

                if response.status_code == 503:
                    wait = self._DESC_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"Service unavailable (503), waiting {wait}s")
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except Exception as e:
                if attempt < 2:
                    wait = self._DESC_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(f"API call failed: {e}, retrying in {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"API call failed after 3 attempts: {e}")
                    return None

        return None

    def _fetch_description(self, desc_url):
        """Fetch and clean the HTML description from the noticedesc endpoint.

        Returns:
            Description text on success.
            None on 404 or failure.
            self.RATE_LIMITED if the API quota is exhausted.
        """
        if not desc_url:
            return None

        parsed_url = urlparse(desc_url)
        query = parse_qs(parsed_url.query)
        query['api_key'] = [self.api_key]
        new_query = urlencode(query, doseq=True)
        auth_url = urlunparse(parsed_url._replace(query=new_query))

        response = self._api_call_get(auth_url)
        if response is self.RATE_LIMITED:
            return self.RATE_LIMITED
        if not response:
            return None

        try:
            data = response.json()
            html_content = data.get('description', '')

            if html_content:
                soup = self.parse_html(html_content)
                if soup:
                    text = soup.get_text(separator='\n\n', strip=True)
                    return clean_text(text, preserve_newlines=True)
        except Exception as e:
            logger.warning(f"Failed to parse description response: {e}")

        return None

    def parse_opportunity(self, opp_data, fetch_description=True):
        """Parse individual contract opportunity from API response."""
        try:
            title = clean_text(opp_data.get('title', ''))
            opportunity_number = clean_text(opp_data.get('solicitationNumber', ''))

            source_url = opp_data.get('uiLink')
            if not source_url:
                source_url = f"{self.base_url}/workspace/contract/opp/{opp_data.get('noticeId')}/view"

            posted_date = parse_date(opp_data.get('postedDate'))
            deadline = parse_date(opp_data.get('responseDeadLine'))

            organization = clean_text(opp_data.get('fullParentPathName', ''))
            if not organization and 'officeAddress' in opp_data:
                organization = f"Office in {opp_data['officeAddress'].get('city', '')}"

            category = opp_data.get('baseType', 'Contract')

            # Location from placeOfPerformance
            location = "United States"
            pop = opp_data.get('placeOfPerformance')
            if pop:
                city = ''
                state = ''
                country = ''
                if isinstance(pop.get('city'), dict):
                    city = pop['city'].get('name', '')
                if isinstance(pop.get('state'), dict):
                    state = pop['state'].get('code', '')
                if isinstance(pop.get('country'), dict):
                    country = pop['country'].get('name', '')
                loc_parts = [p for p in [city, state, country] if p]
                if loc_parts:
                    location = ", ".join(loc_parts)

            # Eligibility from set-aside
            eligibility = clean_text(
                opp_data.get('typeOfSetAsideDescription')
                or opp_data.get('typeOfSetAside', '')
            )
            if not eligibility or eligibility == 'NONE':
                eligibility = 'Unrestricted / No Set-Aside'

            # Description — the API 'description' field is a URL to the
            # noticedesc endpoint, not the actual text
            description = None
            if fetch_description:
                desc_url = opp_data.get('description', '')
                if desc_url and desc_url.startswith('http'):
                    description = self._fetch_description(desc_url)

            # Funding amount from award data (Award Notice types)
            funding_amount = None
            award = opp_data.get('award')
            if award and isinstance(award, dict):
                amount = award.get('amount')
                if amount:
                    try:
                        num = float(str(amount).replace(',', ''))
                        if num >= 1:
                            funding_amount = f"${num:,.0f}"
                    except (ValueError, TypeError):
                        pass

            # Document URLs from resourceLinks
            document_urls = []
            resource_links = opp_data.get('resourceLinks')
            if resource_links and isinstance(resource_links, list):
                document_urls = [url for url in resource_links if isinstance(url, str) and url.startswith('http')]

            if category and category.lower() in ['solicitation', 'presolicitation', 'sources sought', 'award notice']:
                guessed_cat = categorize_opportunity(title, description or '')
                if guessed_cat != 'General':
                    category = f"{category} - {guessed_cat}"

            opportunity = {
                'title': title,
                'organization': organization,
                'description': description,
                'eligibility': eligibility,
                'funding_amount': funding_amount,
                'deadline': deadline,
                'category': category or 'General',
                'location': location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opportunity_number,
                'posted_date': posted_date,
                'document_urls': document_urls,
                'opportunity_type': 'contract',
            }

            return opportunity

        except Exception as e:
            logger.error(f"Error parsing opportunity: {e}")
            return None


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the SAM.gov scraper standalone.",
        epilog=(
            "Examples:\n"
            "  python3 -m scrapers.sam_gov                         # full run\n"
            "  python3 -m scrapers.sam_gov --max-pages 1            # single page (~50 opps)\n"
            "  python3 -m scrapers.sam_gov --dry-run --max-pages 1  # test without DB writes\n"
            "  python3 -m scrapers.sam_gov --budget 100             # higher budget (entity key)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--max-pages', type=int, default=1,
        help='Max search pages to fetch, 50 results each (default: 1)',
    )
    parser.add_argument(
        '--budget', type=int, default=None,
        help='Override SAM_GOV_MAX_REQUESTS API call budget for this run',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Scrape and print results but do NOT write to Supabase',
    )
    args = parser.parse_args()

    if args.budget:
        config.SAM_GOV_MAX_REQUESTS = args.budget
        print(f"📋 API budget overridden to {args.budget} calls\n")

    if args.dry_run:
        print("🧪 DRY-RUN MODE — results will be printed but NOT saved to Supabase\n")
        def _dry_add(self, opp):
            self.opportunities.append(opp)
            self._new_count += 1
            return True
        BaseScraper.add_opportunity = _dry_add
        db.opportunity_exists = lambda *a, **kw: False

    scraper = SAMGovScraper()

    try:
        opps = scraper.scrape(max_pages=args.max_pages)
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
