"""
RFPMart scraper — scrapes US government RFPs, bids, and contracts
from rfpmart.com.

Listing page: static HTML with pagination (usa-rfp-bids.html, page-2, etc.)
Detail page:  full description, scope, NAICS, notice type — all public.

Uses plain requests + BeautifulSoup (server-rendered HTML).
"""

import re
import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = config.RFPMART_BASE_URL
LISTING_URL = f'{BASE_URL}/usa-rfp-bids.html'
MAX_PAGES = config.RFPMART_MAX_PAGES

DELAY_BETWEEN_PAGES = (1.5, 3.0)
DELAY_BETWEEN_DETAILS = (1.0, 2.5)

_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
)


class RFPMartScraper(BaseScraper):
    """Scrapes RFPMart USA RFP listings with detail page enrichment."""

    def __init__(self):
        super().__init__('RFPMart')

    def scrape(self):
        logger.info(f"Starting RFPMart scraper (max {MAX_PAGES} pages)...")

        seen_urls = set()

        for page in range(1, MAX_PAGES + 1):
            page_url = LISTING_URL if page == 1 else f'{BASE_URL}/usa-rfp-bids-page-{page}.html'

            logger.info(f"RFPMart: fetching page {page}...")
            resp = self.fetch_page(page_url, headers={'User-Agent': _USER_AGENT})
            if resp is None:
                logger.warning(f"RFPMart: failed to fetch page {page}, stopping.")
                break

            items = self._parse_listing_page(resp.text, seen_urls)
            if not items:
                logger.info(f"RFPMart: no items on page {page}, stopping.")
                break

            for opp in items:
                self._enrich_from_detail(opp)
                self.add_opportunity(opp)
                if self.reached_limit():
                    break

            logger.info(f"RFPMart: page {page} — {len(items)} RFPs")

            if self.reached_limit():
                break
            time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

        self.log_summary()
        return self.opportunities

    def _parse_listing_page(self, html, seen_urls):
        soup = self.parse_html(html)
        items = []

        listing_ul = soup.select_one('ul.rfpmart_india-categoryDetailLists')
        if not listing_ul:
            return items

        for li in listing_ul.find_all('li', recursive=False):
            try:
                opp = self._parse_listing_item(li, seen_urls)
                if opp:
                    items.append(opp)
            except Exception as exc:
                logger.debug(f"RFPMart: listing parse error: {exc}")

        return items

    def _parse_listing_item(self, li, seen_urls):
        link = li.select_one('.rfpmartIN-descriptionCategory a[href]')
        if not link:
            return None

        title_raw = clean_text(link.get_text())
        href = (link.get('href') or '').strip()
        if not title_raw or not href:
            return None

        source_url = urllib.parse.urljoin(BASE_URL + '/', href)
        if source_url in seen_urls:
            return None
        seen_urls.add(source_url)

        opp_number = None
        title = title_raw
        opp_match = re.match(r'^(US-\w+-\d+)\s*-\s*(.+?)(?:\s*-\s*Deadline\s.+)?$', title_raw, re.I)
        if opp_match:
            opp_number = opp_match.group(1)
            title = clean_text(opp_match.group(2))

        posted_date = None
        post_span = li.select_one('span.post-date')
        if post_span:
            posted_date = parse_date(clean_text(post_span.get_text()))

        deadline = None
        expiry_span = li.select_one('span.expiry-date')
        if expiry_span:
            deadline = parse_date(clean_text(expiry_span.get_text()))

        category = categorize_opportunity(title, '')

        return {
            'title': title,
            'organization': None,
            'description': None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': 'United States',
            'source': 'RFPMart',
            'source_url': source_url,
            'opportunity_number': opp_number,
            'posted_date': posted_date,
            'document_urls': [],
            'opportunity_type': 'rfp',
        }

    def _enrich_from_detail(self, opp):
        """Fetch the detail page and extract rich public data."""
        detail_url = opp.get('source_url', '')
        if not detail_url:
            return

        time.sleep(random.uniform(*DELAY_BETWEEN_DETAILS))
        resp = self.fetch_page(detail_url, headers={'User-Agent': _USER_AGENT})
        if resp is None:
            return

        try:
            soup = self.parse_html(resp.text)
            container = soup.select_one('section.col-3-box') or soup.select_one('.cat-des') or soup

            self._extract_detail_fields(container, opp)
        except Exception as exc:
            logger.debug(f"RFPMart: detail parse error for {detail_url}: {exc}")

    def _extract_detail_fields(self, container, opp):
        desc_parts = []
        scope_parts = []
        in_scope = False

        for p in container.find_all('p'):
            text = p.get_text(separator=' ', strip=True)
            if not text:
                continue

            strong = p.find('strong')
            label = clean_text(strong.get_text()) if strong else ''
            label_lower = label.lower()

            is_bold_p = 'fw-bold' in (p.get('class') or [])
            text_lower_trimmed = text.lower()[:60]

            if (label and 'posted date' in label_lower) or (is_bold_p and 'posted date' in text_lower_trimmed):
                raw = text.split(':', 1)[1].strip() if ':' in text else ''
                if raw and not opp.get('posted_date'):
                    opp['posted_date'] = parse_date(raw)
                continue

            if label and 'notice type' in label_lower:
                raw = text.split(':', 1)[1].strip() if ':' in text else ''
                if raw:
                    opp['eligibility'] = clean_text(raw)
                continue

            if 'Product' in text and 'ID:' in text and 'RFP' in text:
                raw = text.split('ID:', 1)[1].strip()
                if raw and not opp.get('opportunity_number'):
                    opp['opportunity_number'] = clean_text(raw)
                continue

            if (label and 'expiry date' in label_lower) or (is_bold_p and 'expiry date' in text_lower_trimmed):
                raw = text.split(':', 1)[1].strip() if ':' in text else ''
                if raw and not opp.get('deadline'):
                    opp['deadline'] = parse_date(raw)
                continue

            if label and 'naics' in label_lower:
                raw = text.split(':', 1)[1].strip() if ':' in text else ''
                if raw:
                    naics = clean_text(raw)[:100]
                    existing_cat = opp.get('category') or ''
                    opp['category'] = f"{existing_cat} | NAICS: {naics}".strip(' |') if existing_cat else f"NAICS: {naics}"
                continue

            if (label and 'category' in label_lower) or (is_bold_p and 'category' in text_lower_trimmed):
                a_tag = p.find('a')
                if a_tag:
                    cat = clean_text(a_tag.get_text())
                    if cat:
                        existing = opp.get('category') or ''
                        if 'NAICS' in existing:
                            opp['category'] = f"{cat} | {existing}"
                        else:
                            opp['category'] = cat
                continue

            if (label and 'state' in label_lower) or (is_bold_p and 'state' in text_lower_trimmed):
                a_tag = p.find('a')
                if a_tag:
                    state_val = clean_text(a_tag.get_text())
                    if state_val and state_val != 'USA':
                        opp['location'] = state_val
                continue

            if (label and 'country' in label_lower) or (is_bold_p and 'country' in text_lower_trimmed):
                continue

            if 'Cost to Download' in text:
                continue

            if 'Scope of Service' in text:
                in_scope = True
                continue

            if in_scope:
                scope_parts.append(text)
                in_scope = False
            elif len(text) > 50:
                desc_parts.append(text)

        description = ''
        if desc_parts:
            description = ' '.join(desc_parts)
        if scope_parts:
            scope_text = ' '.join(scope_parts)
            if description:
                description = f"{description}\n\nScope: {scope_text}"
            else:
                description = scope_text

        if description and len(description) > 30:
            opp['description'] = description[:2000]

    def parse_opportunity(self, element):
        return None


def get_rfpmart_scrapers():
    """Return a list containing the RFPMart scraper instance."""
    return [RFPMartScraper()]
