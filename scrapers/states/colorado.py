"""
Colorado Procurement scraper — BidNet Direct (Colorado partner page).

Source: https://www.bidnetdirect.com/colorado

Notes:
  - The previous CGI Advantage VSS endpoint at vss.state.co.us was a Google
    Sites informational landing page (not the real procurement app), and
    the actual app at prd.co.cgiadvantage.com is intermittently 500. We
    target BidNet Direct (Colorado's official regional partner) which is
    reliable and ships the bid list as plain HTML.
  - BidNet bids render as ``tr.mets-table-row`` rows inside ``table.mets-table``.
    Per-row sub-selectors:
      * title       : ``.sol-title a.solicitation-link``
      * deadline    : ``.sol-closing-date`` (text contains an icon-prefix
                      like "Clock Closing 05/22/2026" — we regex out the date)
      * organization: ``.sol-region``
"""

import random
import re
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


_DATE_RE = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b')


class ColoradoProcurementScraper(BaseScraper):
    """Colorado Procurement scraper — BidNet Direct (Colorado)."""

    SEARCH_URL = "https://www.bidnetdirect.com/colorado"
    BASE = "https://www.bidnetdirect.com"

    def __init__(self):
        super().__init__("Colorado Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        # Try plain HTTP first — BidNet renders the bid list server-side.
        html = None
        try:
            resp = self.fetch_page(self.SEARCH_URL, timeout=30)
            if resp is not None and resp.text:
                html = resp.text
                logger.info("Colorado: fetched BidNet via HTTP")
        except Exception as exc:
            logger.debug(f"Colorado HTTP fetch failed: {exc}")

        if not html:
            driver = SeleniumDriverManager.get_driver(use_proxy=True)
            if driver:
                try:
                    driver.get(self.SEARCH_URL)
                    time.sleep(random.uniform(6, 10))
                    html = driver.page_source
                except Exception as exc:
                    logger.warning(f"Colorado Selenium fetch failed: {exc}")

        if not html:
            logger.error("Colorado: could not fetch BidNet listing")
            self.log_summary()
            return self.opportunities

        soup = BeautifulSoup(html, 'html.parser')
        self._parse_bidnet(soup)
        self.log_summary()
        return self.opportunities

    def _parse_bidnet(self, soup):
        """Parse BidNet Direct's bid table.

        Each open bid is a ``tr.mets-table-row`` inside ``table.mets-table``.
        ``div.sol-content-container`` is the page-level wrapper around the
        whole list (only one of those exists), so we don't iterate it.
        """
        rows = soup.select('tr.mets-table-row')
        if not rows:
            # Fallback if BidNet flips to a card layout.
            rows = soup.select('div.sol-row, div[class*="solicitation-card"]')

        logger.info(f"Colorado BidNet: found {len(rows)} bid rows")

        for row in rows:
            if self.reached_limit():
                break
            try:
                title_link = (
                    row.select_one('div.sol-title a.solicitation-link')
                    or row.select_one('.sol-title a')
                    or row.select_one('a.solicitation-link')
                    or row.find('a', href=True)
                )
                if not title_link:
                    continue
                title = clean_text(title_link.get_text(' ', strip=True))
                if not title or len(title) < 5:
                    continue

                href = (title_link.get('href') or '').strip()
                if not href or href.lower().startswith(('javascript:', 'mailto:', '#')):
                    detail_url = None
                else:
                    detail_url = href if href.startswith('http') else urljoin(self.BASE, href)

                deadline_el = row.select_one('.sol-closing-date, .sol-due-date')
                deadline_str = clean_text(deadline_el.get_text(' ', strip=True)) if deadline_el else ''
                # Strip "Clock Closing", "Closing", icon labels — keep just the date.
                deadline_clean = ''
                if deadline_str:
                    m = _DATE_RE.search(deadline_str)
                    deadline_clean = m.group(1) if m else deadline_str

                org_el = row.select_one('.sol-region, .sol-organization')
                org = clean_text(org_el.get_text(' ', strip=True)) if org_el else ''

                opp_num_el = row.select_one(
                    '.sol-number, .sol-id, [class*="solicitation-number"], [class*="bid-number"]'
                )
                opp_num = clean_text(opp_num_el.get_text(' ', strip=True)) if opp_num_el else None
                # BidNet encodes bid # as the URL slug tail. Strip query/fragment
                # first — BidNet appends ?purchasingGroupId=…&origin=… tracking
                # params we don't want polluting the opportunity_number.
                if not opp_num and detail_url:
                    path = urlparse(detail_url).path
                    tail = path.rstrip('/').rsplit('/', 1)[-1]
                    if tail and any(ch.isdigit() for ch in tail):
                        opp_num = tail[:64]

                anchor = opp_num or title[:80].replace(' ', '_')
                source_url = detail_url or f"{self.SEARCH_URL}#{anchor}"

                self.add_opportunity({
                    'title': title,
                    'organization': org or 'State of Colorado',
                    'description': None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': parse_date(deadline_clean) if deadline_clean else None,
                    'category': categorize_opportunity(title, ''),
                    'location': 'Colorado',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_num,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except Exception as e:
                logger.debug(f"  CO BidNet row failed: {e}")
                continue

    def parse_opportunity(self, element):
        """Required by BaseScraper. Row parsing is inlined in _parse_bidnet."""
        return None


def get_colorado_scrapers():
    return [ColoradoProcurementScraper()]
