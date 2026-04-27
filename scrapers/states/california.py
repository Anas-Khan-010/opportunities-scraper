"""
California Grants Portal scraper — grants.ca.gov / data.ca.gov

Scrapes California state grant opportunities from the official CKAN
open-data API.  Returns ~160 active grants with rich metadata including
eligibility, funding amounts, deadlines, and categories.

Source: https://grants.ca.gov
API:    https://data.ca.gov/api/3/action/datastore_search_sql
"""

import urllib.parse

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity, extract_funding_amount


class CaliforniaGrantsScraper(BaseScraper):
    """Scrapes California state grants from the CKAN open-data API."""

    def __init__(self):
        super().__init__('California Grants Portal')
        self.api_url = config.CA_GRANTS_API_URL
        self.resource_id = config.CA_GRANTS_RESOURCE_ID

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (CKAN API)...")
        self._scrape_ckan()
        self.log_summary()
        return self.opportunities

    def _scrape_ckan(self):
        page_size = 100
        offset = 0

        count_sql = (
            f'SELECT COUNT(*) FROM "{self.resource_id}" WHERE "Status" = \'active\''
        )
        total = None
        try:
            resp = self.fetch_page(self.api_url, params={'sql': count_sql})
            if resp:
                total = resp.json()['result']['records'][0]['count']
                logger.info(f"California: {total} active records in API")
        except Exception:
            pass

        while True:
            sql = (
                f'SELECT * FROM "{self.resource_id}" '
                f"WHERE \"Status\" = 'active' "
                f'ORDER BY "_id" ASC '
                f'LIMIT {page_size} OFFSET {offset}'
            )
            try:
                response = self.fetch_page(self.api_url, params={'sql': sql})
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
                        if opp.get('document_urls'):
                            self.enrich_from_documents(opp)
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
                f"California - {geography}" if geography else 'California'
            )

            funding = clean_text(record.get('EstAvailFunds', ''))
            if not funding:
                est_amounts = clean_text(record.get('EstAmounts', ''))
                if est_amounts:
                    amt = extract_funding_amount(est_amounts)
                    funding = amt if amt else est_amounts

            opp = {
                'title': title,
                'organization': clean_text(record.get('AgencyDept', ''))
                    or 'State of California',
                'description': description,
                'eligibility': eligibility,
                'funding_amount': funding,
                'deadline': deadline,
                'category': category,
                'location': location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': portal_id or None,
                'posted_date': parse_date(record.get('OpenDate', '')),
                'document_urls': [],
                'opportunity_type': 'grant',
            }

            if grant_url:
                self._enrich_doc_urls(opp, grant_url)

            return opp
        except Exception as e:
            logger.error(f"Error parsing California API record: {e}")
            return None

    def _enrich_doc_urls(self, opp, grant_url):
        """Fetch the grant application page and scrape for document links."""
        try:
            resp = self.fetch_page(grant_url)
            if not resp or resp.status_code != 200:
                return

            soup = self.parse_html(resp.text)
            doc_urls = []
            for a in soup.select('a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"]'):
                href = a.get('href', '').strip()
                if href:
                    full = href if href.startswith('http') else urllib.parse.urljoin(grant_url, href)
                    if full not in doc_urls:
                        doc_urls.append(full)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]
        except Exception as exc:
            logger.debug(f"CA: doc URL enrichment failed for {grant_url}: {exc}")


def get_california_scrapers():
    """Create scraper instances for the California Grants Portal."""
    return [CaliforniaGrantsScraper()]
