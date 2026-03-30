from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity
from database.db import db


class GrantsGovAgencyScraper(BaseScraper):
    """
    Base class for federal agency scrapers that use the Grants.gov search2 API
    filtered by agency code.

    Each subclass configures its agency_code, source_name, organization_name,
    and default_category. The base handles pagination, parsing, deduplication,
    and rate limiting (inherited from BaseScraper.fetch_page).

    These scrapers are API-only (no Selenium). If grants_gov.py runs later with
    keyword searches, it will skip DB-duplicates automatically.
    """

    def __init__(self, source_name, agency_code, organization_name, default_category):
        super().__init__(source_name)
        self.agency_code = agency_code
        self.organization_name = organization_name
        self.default_category = default_category
        self.api_url = config.GRANTS_GOV_API_URL
        self.base_url = config.GRANTS_GOV_BASE_URL

    def scrape(self, max_pages=5):
        logger.info(f"Starting {self.source_name} scraper (agency={self.agency_code})...")

        seen_ids = set()

        for page in range(max_pages):
            opp_hits = self._search_api(page)

            if opp_hits is None:
                logger.warning(f"API request failed for {self.source_name}, "
                               f"page={page + 1} — stopping")
                break

            if not opp_hits:
                logger.info(f"No more results for {self.source_name} after page {page + 1}")
                break

            for opp_data in opp_hits:
                opp_id = opp_data.get('id')
                if opp_id in seen_ids:
                    continue
                seen_ids.add(opp_id)

                opportunity = self._parse_api_result(opp_data)
                if opportunity is None:
                    continue

                if db.opportunity_exists(opportunity['source_url']):
                    continue

                self.opportunities.append(opportunity)

            logger.info(f"Page {page + 1} complete for {self.source_name}. "
                        f"Total so far: {len(self.opportunities)}")

        self.log_summary()
        return self.opportunities

    def _search_api(self, page):
        """Fetch one page of results from the search2 API for this agency."""
        payload = {
            "keyword": "",
            "agencies": self.agency_code,
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

            data = response.json().get('data', {})
            return data.get('oppHits') or []

        except ValueError as e:
            logger.error(f"Invalid JSON from API for {self.source_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in API request for {self.source_name}: {e}")
            return None

    def _parse_api_result(self, opp_data):
        """Parse one opportunity from API response into our standard dict."""
        try:
            opp_id = opp_data.get('id')
            title = clean_text(opp_data.get('title', ''))

            if not title or not opp_id:
                return None

            opportunity_number = clean_text(opp_data.get('number', ''))
            source_url = f"{self.base_url}/search-results-detail/{opp_id}"
            agency = clean_text(opp_data.get('agency', '')) or self.organization_name
            posted_date = parse_date(opp_data.get('openDate'))
            deadline = parse_date(opp_data.get('closeDate'))

            category = self.default_category
            if not category:
                category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': agency,
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'United States',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opportunity_number,
                'posted_date': posted_date,
                'document_urls': [],
                'full_document': None,
            }
        except Exception as e:
            logger.error(f"Error parsing API result for {self.source_name}: {e}")
            return None

    def parse_opportunity(self, element):
        """Required by BaseScraper. Delegates to _parse_api_result."""
        return self._parse_api_result(element)


# ─── Agency Subclasses ────────────────────────────────────────────────

class DOEScraper(GrantsGovAgencyScraper):
    """Department of Energy grants via Grants.gov API (agency code: DOE)"""
    def __init__(self):
        super().__init__(
            source_name='DOE Grants',
            agency_code='DOE',
            organization_name='U.S. Department of Energy',
            default_category='Energy',
        )


class DOEScienceScraper(GrantsGovAgencyScraper):
    """DOE Office of Science grants via Grants.gov API (agency code: PAMS)"""
    def __init__(self):
        super().__init__(
            source_name='DOE Science Grants',
            agency_code='PAMS',
            organization_name='U.S. Department of Energy - Office of Science',
            default_category='Research',
        )


class USDAGrantsScraper(GrantsGovAgencyScraper):
    """USDA grants via Grants.gov API (agency code: USDA)"""
    def __init__(self):
        super().__init__(
            source_name='USDA Grants',
            agency_code='USDA',
            organization_name='U.S. Department of Agriculture',
            default_category='Agriculture',
        )


class EPAGrantsScraper(GrantsGovAgencyScraper):
    """EPA grants via Grants.gov API (agency code: EPA)"""
    def __init__(self):
        super().__init__(
            source_name='EPA Grants',
            agency_code='EPA',
            organization_name='U.S. Environmental Protection Agency',
            default_category='Environment',
        )


class HUDGrantsScraper(GrantsGovAgencyScraper):
    """HUD grants via Grants.gov API (agency code: HUD)"""
    def __init__(self):
        super().__init__(
            source_name='HUD Grants',
            agency_code='HUD',
            organization_name='U.S. Department of Housing and Urban Development',
            default_category='Housing',
        )


class SBAGrantsScraper(GrantsGovAgencyScraper):
    """SBA grants via Grants.gov API (agency code: SBA)"""
    def __init__(self):
        super().__init__(
            source_name='SBA Grants',
            agency_code='SBA',
            organization_name='U.S. Small Business Administration',
            default_category='Business',
        )
