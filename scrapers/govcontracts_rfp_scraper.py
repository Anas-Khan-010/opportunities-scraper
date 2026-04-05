"""
GovernmentContracts.us RFP scraper — scrapes state & local procurement
opportunities from governmentcontracts.us.

Primary aggregated RFP source covering all 50 US states with 29,000+ active
contract opportunities.  Uses plain requests + BeautifulSoup (no Selenium)
since the site is server-rendered HTML.

Listing URL pattern:
  /government-contracts/?gov=sl&state={XX}&sort=postdesc&page={N}
  where XX is the 2-letter state abbreviation.

Detail pages are behind a login wall so we only extract data from listings.
"""

import re
import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = 'https://www.governmentcontracts.us'
LISTING_PATH = '/government-contracts/'

STATES = {
    'AL': 'Alabama',       'AK': 'Alaska',        'AZ': 'Arizona',
    'AR': 'Arkansas',      'CA': 'California',     'CO': 'Colorado',
    'CT': 'Connecticut',   'DE': 'Delaware',       'FL': 'Florida',
    'GA': 'Georgia',       'HI': 'Hawaii',         'ID': 'Idaho',
    'IL': 'Illinois',      'IN': 'Indiana',        'IA': 'Iowa',
    'KS': 'Kansas',        'KY': 'Kentucky',       'LA': 'Louisiana',
    'ME': 'Maine',         'MD': 'Maryland',       'MA': 'Massachusetts',
    'MI': 'Michigan',      'MN': 'Minnesota',      'MS': 'Mississippi',
    'MO': 'Missouri',      'MT': 'Montana',        'NE': 'Nebraska',
    'NV': 'Nevada',        'NH': 'New Hampshire',  'NJ': 'New Jersey',
    'NM': 'New Mexico',    'NY': 'New York',       'NC': 'North Carolina',
    'ND': 'North Dakota',  'OH': 'Ohio',           'OK': 'Oklahoma',
    'OR': 'Oregon',        'PA': 'Pennsylvania',   'RI': 'Rhode Island',
    'SC': 'South Carolina','SD': 'South Dakota',   'TN': 'Tennessee',
    'TX': 'Texas',         'UT': 'Utah',           'VT': 'Vermont',
    'VA': 'Virginia',      'WA': 'Washington',     'WV': 'West Virginia',
    'WI': 'Wisconsin',     'WY': 'Wyoming',
}

MAX_PAGES_PER_STATE = 5
DELAY_BETWEEN_REQUESTS = (1.0, 2.0)
DELAY_BETWEEN_STATES = (1.5, 3.0)

_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
)


class GovContractsRFPScraper(BaseScraper):
    """
    Scrapes GovernmentContracts.us — a US procurement aggregator with 29,000+
    active state & local contract/RFP opportunities across all 50 states.
    """

    def __init__(self):
        super().__init__('GovernmentContracts.us RFPs')
        self.session.headers.update({
            'User-Agent': _USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def scrape(self):
        logger.info("Starting GovernmentContracts.us RFP scraper (all 50 states)...")

        for abbr in sorted(STATES):
            state_name = STATES[abbr]
            try:
                self._scrape_state(abbr, state_name)
            except Exception as exc:
                logger.error(f"GovContracts: error scraping {state_name}: {exc}")

        self.log_summary()
        return self.opportunities

    def _scrape_state(self, abbr, state_name):
        count_before = len(self.opportunities)
        seen_ids = set()

        for page in range(1, MAX_PAGES_PER_STATE + 1):
            params = {'gov': 'sl', 'state': abbr, 'sort': 'postdesc'}
            if page > 1:
                params['page'] = page

            time.sleep(random.uniform(*DELAY_BETWEEN_REQUESTS))
            resp = self.fetch_page(f'{BASE_URL}{LISTING_PATH}', params=params)
            if resp is None:
                break

            page_items = self._parse_listing_page(resp.text, state_name, seen_ids)
            if not page_items:
                break

            self.opportunities.extend(page_items)

            if not self._has_next_page(resp.text, page):
                break

        added = len(self.opportunities) - count_before
        if added > 0:
            logger.info(f"GovContracts: {state_name} — {added} RFPs")

        time.sleep(random.uniform(*DELAY_BETWEEN_STATES))

    # ------------------------------------------------------------------
    # Listing page parsing
    # ------------------------------------------------------------------

    def _parse_listing_page(self, html, state_name, seen_ids):
        soup = self.parse_html(html)
        items = []

        for div in soup.find_all('div', class_='bid-item'):
            try:
                opp = self._parse_listing_item(div, state_name, seen_ids)
                if opp:
                    items.append(opp)
            except Exception as exc:
                logger.debug(f"GovContracts: listing parse error: {exc}")

        return items

    def _parse_listing_item(self, div, state_name, seen_ids):
        h4 = div.find('h4')
        if not h4:
            return None
        link = h4.find('a', href=True)
        if not link:
            return None

        title = clean_text(link.get_text())
        if not title or len(title) < 5:
            return None

        href = link['href']
        opp_id = self._extract_id(href)
        if opp_id:
            if opp_id in seen_ids:
                return None
            seen_ids.add(opp_id)

        source_url = urllib.parse.urljoin(BASE_URL, href.split('?')[0])

        state_tag = div.find('strong')
        location = clean_text(state_tag.get_text()) if state_tag else state_name

        due_date = None
        posted_date = None
        for p in div.find_all('p', class_='bids-item-date'):
            text = p.get_text()
            if 'Due:' in text:
                due_date = parse_date(text.replace('Due:', '').strip())
            elif 'Posted:' in text:
                posted_date = parse_date(text.replace('Posted:', '').strip())

        category = categorize_opportunity(title, '')

        return {
            'title': title,
            'organization': None,
            'description': None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': due_date,
            'category': category,
            'location': location,
            'source': f'GovContracts - {location} RFPs',
            'source_url': source_url,
            'opportunity_number': None,
            'posted_date': posted_date,
            'document_urls': [],
            'opportunity_type': 'rfp',
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_id(href):
        m = re.search(r'opportunity-details/(\w+)\.htm', href)
        return m.group(1) if m else None

    @staticmethod
    def _has_next_page(html, current_page):
        pattern = rf'data-ci-pagination-page="{current_page + 1}"'
        return bool(re.search(pattern, html))

    def parse_opportunity(self, element):
        return None


def get_govcontracts_rfp_scrapers():
    """Return a list containing the single GovContracts scraper instance."""
    return [GovContractsRFPScraper()]
