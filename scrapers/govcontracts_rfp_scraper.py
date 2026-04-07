"""
GovernmentContracts.us RFP scraper — scrapes state & local procurement
opportunities from governmentcontracts.us.

Primary aggregated RFP source covering all 50 US states.
Uses plain requests + BeautifulSoup (server-rendered HTML).

Listing page -> get titles, dates, detail links
Detail page  -> get agency, description, document URLs
"""

import re
import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = config.GOVCONTRACTS_BASE_URL
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

MAX_PAGES_PER_STATE = config.GOVCONTRACTS_MAX_PAGES_PER_STATE
DELAY_BETWEEN_REQUESTS = (1.0, 2.0)
DELAY_BETWEEN_DETAILS = (1.0, 2.0)
DELAY_BETWEEN_STATES = (1.5, 3.0)

_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
)


class GovContractsRFPScraper(BaseScraper):
    """
    Scrapes GovernmentContracts.us — a US procurement aggregator with
    active state & local contract/RFP opportunities across all 50 states.
    Visits detail pages for agency, description, and document URLs.
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
            if self.reached_limit():
                break
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

            for opp in page_items:
                self._enrich_from_detail(opp)
                self.add_opportunity(opp)
                if self.reached_limit():
                    break

            if self.reached_limit() or not self._has_next_page(resp.text, page):
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
            'opportunity_number': opp_id,
            'posted_date': posted_date,
            'document_urls': [],
            'opportunity_type': 'rfp',
        }

    # ------------------------------------------------------------------
    # Detail page enrichment
    # ------------------------------------------------------------------

    def _enrich_from_detail(self, opp):
        """Visit detail page and extract fields from the public table.
        Description, attachments, solicitation numbers, and publication URL
        are behind a login wall on most listings."""
        detail_url = opp.get('source_url', '')
        if not detail_url:
            return

        time.sleep(random.uniform(*DELAY_BETWEEN_DETAILS))
        resp = self.fetch_page(detail_url)
        if resp is None:
            return

        try:
            soup = self.parse_html(resp.text)
            container = soup.find('div', class_='detail-contents') or soup

            agency = self._extract_table_field(container, 'Agency')
            if agency:
                opp['organization'] = agency

            cat_raw = self._extract_table_field(container, 'Category')
            if cat_raw:
                opp['category'] = clean_text(cat_raw)[:200]

            gov_type = self._extract_table_field(container, 'Type of Government')
            if gov_type:
                opp['eligibility'] = gov_type

            desc = self._extract_table_field(container, 'Bid Description')
            if desc and 'log in' not in desc.lower() and 'access bid' not in desc.lower():
                opp['description'] = desc[:2000]

            sol_no = self._extract_table_field(container, 'Solicitation')
            if sol_no and 'log in' not in sol_no.lower():
                opp['opportunity_number'] = sol_no

            pub_url = self._extract_table_link(container, 'Publication URL')
            if pub_url:
                opp['document_urls'] = [pub_url]

            attachment_url = self._extract_table_link(container, 'Attachment')
            if attachment_url:
                existing = opp.get('document_urls') or []
                if attachment_url not in existing:
                    existing.append(attachment_url)
                opp['document_urls'] = existing

        except Exception as exc:
            logger.debug(f"GovContracts: detail parse error for {detail_url}: {exc}")

    @staticmethod
    def _extract_table_field(container, label):
        """Extract value from <tr><th>Label:</th><td>value</td></tr> pattern."""
        for th in container.find_all('th'):
            if label.lower() in th.get_text().lower():
                td = th.find_next_sibling('td')
                if td:
                    val = clean_text(td.get_text())
                    if val:
                        return val
        return None

    @staticmethod
    def _extract_table_link(container, label):
        """Extract an <a href> URL from a table row, ignoring login-gated links."""
        for th in container.find_all('th'):
            if label.lower() in th.get_text().lower():
                td = th.find_next_sibling('td')
                if td:
                    a = td.find('a', href=True)
                    if a:
                        href = a.get('href', '').strip()
                        if href and 'signin' not in href and 'login' not in href:
                            return href
        return None

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
