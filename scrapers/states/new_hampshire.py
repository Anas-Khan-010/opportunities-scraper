"""
New Hampshire Procurement scraper — newhampshirebids.com

Scrapes active bid solicitations and RFPs from the New Hampshire Bid
Network, which aggregates NH state and local government procurement
opportunities.

The official NH procurement portal (apps.das.nh.gov) employs aggressive
bot protection that blocks headless browsers, so this scraper uses the
publicly accessible newhampshirebids.com mirror instead.

Detail pages provide richer data including scope descriptions, deadlines,
and PDF attachments. PDF enrichment extracts description, eligibility,
and funding_amount.

Source: https://www.newhampshirebids.com/
"""

import re
import time
import urllib.parse

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity, extract_funding_amount


LISTING_URL = "https://www.newhampshirebids.com/"
BASE_URL = "https://www.newhampshirebids.com"


class NewHampshireBidsScraper(BaseScraper):
    """Scrapes NH procurement bids from newhampshirebids.com."""

    def __init__(self):
        super().__init__("New Hampshire Procurement")
        self.max_pages = getattr(config, "NH_PROCUREMENT_MAX_PAGES", 10)

    def scrape(self):
        logger.info("Starting New Hampshire Procurement scraper (newhampshirebids.com)...")
        self._scrape_listings()
        self.log_summary()
        return self.opportunities

    def _scrape_listings(self):
        page_url = LISTING_URL
        page = 1

        while page <= self.max_pages and not self.reached_limit():
            logger.info(f"NH: fetching page {page}: {page_url}")
            resp = self.fetch_page(page_url)
            if not resp:
                logger.error(f"NH: failed to fetch page {page}")
                break

            soup = self.parse_html(resp.text)
            rows = self._extract_rows(soup)

            if not rows:
                logger.info(f"NH: no rows on page {page}, stopping.")
                break

            page_new = 0
            for row_data in rows:
                if self.reached_limit():
                    break

                opp = self._build_opportunity(row_data)
                if not opp:
                    continue

                self._enrich_from_detail(opp)

                if opp.get('document_urls'):
                    self.enrich_from_documents(opp)

                is_new = self.add_opportunity(opp)
                if is_new:
                    page_new += 1

            logger.info(f"NH: page {page} — {len(rows)} rows, {page_new} new")

            next_url = self._find_next_page(soup)
            if not next_url:
                break
            page_url = next_url
            page += 1

    def _extract_rows(self, soup):
        """Parse bid rows from the listing table."""
        rows = []

        table = soup.find('table')
        if table:
            for tr in table.find_all('tr'):
                cells = tr.find_all('td')
                if len(cells) < 2:
                    continue

                date_text = clean_text(cells[0].get_text())
                title_cell = cells[1]

                link = title_cell.find('a', href=True)
                if not link:
                    continue

                title = clean_text(link.get_text())
                if not title or len(title) < 5:
                    continue

                href = link['href']
                if not href.startswith('http'):
                    href = BASE_URL + href

                scope = None
                scope_tr = tr.find_next_sibling('tr')
                if scope_tr:
                    scope_text = clean_text(scope_tr.get_text())
                    if scope_text and scope_text.lower().startswith('scope:'):
                        scope = scope_text[6:].strip()

                rows.append({
                    'title': title,
                    'detail_url': href,
                    'posted_date': date_text,
                    'scope': scope,
                })

            return rows

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/bid_opportunities/' not in href:
                continue
            title = clean_text(a_tag.get_text())
            if not title or len(title) < 5:
                continue
            if not href.startswith('http'):
                href = BASE_URL + href

            rows.append({
                'title': title,
                'detail_url': href,
                'posted_date': None,
                'scope': None,
            })

        return rows

    def _build_opportunity(self, data):
        title = data.get('title', '')
        if not title:
            return None

        opp_type = 'rfp'
        lower_title = title.lower()
        if '(rfq)' in lower_title:
            opp_type = 'rfq'
        elif '(rfb)' in lower_title or '(ifb)' in lower_title:
            opp_type = 'rfb'

        posted = parse_date(data.get('posted_date')) if data.get('posted_date') else None

        description = data.get('scope')
        category = categorize_opportunity(title, description or '')

        return {
            'title': title,
            'organization': 'State of New Hampshire',
            'description': description,
            'eligibility': None,
            'funding_amount': None,
            'deadline': None,
            'category': category,
            'location': 'New Hampshire',
            'source': self.source_name,
            'source_url': data.get('detail_url', LISTING_URL),
            'opportunity_number': None,
            'posted_date': posted,
            'document_urls': [],
            'opportunity_type': opp_type,
        }

    def _enrich_from_detail(self, opp):
        """Fetch the detail page for richer data."""
        detail_url = opp.get('source_url', '')
        if not detail_url or detail_url == LISTING_URL:
            return

        try:
            resp = self.fetch_page(detail_url)
            if not resp:
                return

            soup = self.parse_html(resp.text)
            # Restrict text extraction to the main content area to avoid sidebars/footers
            content_area = (
                soup.find('div', id=re.compile(r'content|main|body', re.I)) or
                soup.find('div', class_=re.compile(r'content|detail|body|article', re.I)) or
                soup.find('article') or
                soup.find('main')
            )
            text_for_parsing = content_area.get_text(separator='\n', strip=True) if content_area else full_text

            if not opp.get('description') or len(opp.get('description', '')) < 50:
                if content_area:
                    desc = clean_text(content_area.get_text(separator=' '))
                    if desc and len(desc) > 20:
                        opp['description'] = desc[:2000]

            deadline_pattern = re.search(
                r'(?:deadline|due\s*date|closing|closes|bid\s*opening|bids?\s*due)[:\s]*'
                r'(\w+\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[AaPp][Mm])?'
                r'|\d{1,2}/\d{1,2}/\d{4})',
                text_for_parsing, re.IGNORECASE,
            )
            if deadline_pattern and not opp.get('deadline'):
                opp['deadline'] = parse_date(deadline_pattern.group(1))

            if not opp.get('opportunity_number'):
                # NH specific: Solicitation # or Bid #
                bid_pattern = re.search(
                    r'(?:bid\s*(?:number|#|no\.?)|solicitation\s*(?:number|#|no\.?)|rfp\s*(?:number|#|no\.?)|event\s*id)\s*[:\s]*([\w\-\.\/]+)',
                    text_for_parsing, re.IGNORECASE,
                )
                if bid_pattern:
                    opp['opportunity_number'] = bid_pattern.group(1).rstrip('.,;')

            if not opp.get('opportunity_number'):
                title = opp.get('title', '')
                title_num = re.search(
                    r'(?:RFP|RFQ|RFB|IFB|Bid|Solicitation)\s*[#:\-]?\s*([\w\-]+\d[\w\-]*)',
                    title, re.IGNORECASE,
                )
                if title_num:
                    opp['opportunity_number'] = title_num.group(1).rstrip('.,;)')

            if not opp.get('eligibility'):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if elig:
                    opp['eligibility'] = elig

            if not opp.get('funding_amount'):
                amount = extract_funding_amount(text_for_parsing)
                if amount:
                    opp['funding_amount'] = amount

            doc_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href or href.startswith(('mailto:', 'javascript:')):
                    continue
                if any(href.lower().endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')):
                    full_url = href if href.startswith('http') else urllib.parse.urljoin(BASE_URL, href)
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]


        except Exception as exc:
            logger.debug(f"NH: detail enrichment failed for {detail_url}: {exc}")

    def _find_next_page(self, soup):
        """Find the 'Previous Business Opportunities' pagination link."""
        for a in soup.find_all('a', href=True):
            raw = clean_text(a.get_text())
            if not raw:
                continue
            text = raw.lower()
            if 'previous' in text or 'older' in text or 'next' in text:
                href = a['href']
                if not href.startswith('http'):
                    href = BASE_URL + href
                return href
        return None

    def parse_opportunity(self, element):
        return None


def get_new_hampshire_scrapers():
    return [NewHampshireBidsScraper()]
