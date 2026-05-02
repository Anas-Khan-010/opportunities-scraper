"""
Washington Procurement scraper — DES WEBS + DES landing page.

Sources:
  1. https://pr-webs-vendor.des.wa.gov/  — Official WEBS (Washington Electronic Business Solution)
  2. https://des.wa.gov/services/contracting-purchasing  — DES landing page

Notes:
  - Uses Selenium 4 ``find_elements(By.TAG_NAME, ...)`` (the 3.x
    ``find_elements_by_tag_name`` API is gone).
  - Header-aware column mapping for the WEBS grid.
  - Filters non-bid noise links on the DES landing page.
"""

import re
import time
import random
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


# Generic navigation labels we don't want to log as "opportunities".
_NON_BID_TEXTS = {
    'home', 'about', 'contact', 'login', 'sign in', 'register', 'help',
    'español', 'site map', 'privacy', 'terms', 'accessibility', 'careers',
    'press releases', 'news', 'public records',
}


class WashingtonProcurementScraper(BaseScraper):
    """Washington Procurement scraper — WEBS BidCalendar + apps.des.wa.gov.

    The previous URLs were wrong:
      - ``pr-webs-vendor.des.wa.gov/`` is a frameset whose data-bearing
        frame is the vendor LOGIN page, not the solicitations list. The
        public bid calendar lives at ``BidCalendar.aspx``.
      - ``des.wa.gov/services/contracting-purchasing`` returns a 404
        Drupal page (the path was renamed). We use the apps host for
        statewide contracts as the secondary source.
    """

    SEARCH_URLS = [
        "https://pr-webs-vendor.des.wa.gov/BidCalendar.aspx",
        "https://apps.des.wa.gov/DESContracts/",
    ]

    def __init__(self):
        super().__init__("Washington Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Washington")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(6, 10))

                # Skip Drupal 404 pages quickly so we don't burn time.
                cur = (driver.current_url or '').lower()
                if 'oops-page-not-found' in cur or '404' in (driver.title or '').lower():
                    logger.warning(f"  Washington: {url} resolved to a 404 page, skipping")
                    continue

                if "pr-webs-vendor" in url:
                    self._scrape_webs(driver, url)
                else:
                    self._scrape_des(driver, url)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Washington at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_webs(self, driver, base_url):
        """Parse Washington WEBS BidCalendar.aspx.

        WEBS renders its grid as ``table#DataGrid1`` whose rows are *outer*
        ``<tr>``s containing a *nested* ``<table>`` with three columns:
          col 0: close date (and amendment date as a sub-row)
          col 1: title link → ``Search_BidDetails.aspx?ID=…`` + Ref # span
                 + a description sub-row (``<td colspan="2">``)
          col 2: contact name
        ``find_all('tr')`` is recursive in BeautifulSoup, so we must use
        ``recursive=False`` to skip the nested header/sub-rows.
        """
        try:
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            grid = soup.find('table', id='DataGrid1') or soup.find('table', id=lambda x: x and 'DataGrid' in x)

            if grid is not None:
                # html.parser materializes an implicit <tbody>, so direct
                # tr-children of <table> may be empty even when the grid is
                # populated. Descend into <tbody> first when available.
                container = grid.find('tbody') or grid
                outer_rows = container.find_all('tr', recursive=False)
                # First row is the column header; every subsequent outer
                # <tr> contains one nested table per opportunity.
                outer_rows = outer_rows[1:] if len(outer_rows) > 1 else outer_rows
            else:
                outer_rows = soup.select('tr[class*="row"], tr[id*="row"]')

            for outer in outer_rows:
                if self.reached_limit():
                    break
                try:
                    nested = outer.find('table')
                    target = nested if nested is not None else outer

                    # The detail link is the cleanest anchor for a real bid row.
                    detail_link = target.find(
                        'a', href=lambda h: h and 'Search_BidDetails.aspx' in h
                    )
                    if detail_link is None:
                        continue
                    title = clean_text(detail_link.get_text(' ', strip=True))
                    if not title or len(title) < 5:
                        continue

                    href = detail_link.get('href', '').strip()
                    detail_url = (
                        href if href.startswith('http') else urljoin(base_url, href)
                    )

                    # Pull cells from the nested table only — top-level <td>s
                    # of `outer` are the entire row container.
                    cells = target.find_all('td', recursive=True)

                    # Close date — first <td> typically contains it as plain
                    # text. Use a regex to be robust against icons/labels.
                    deadline_str = None
                    if cells:
                        date_text = clean_text(cells[0].get_text(' ', strip=True))
                        if date_text:
                            m = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', date_text)
                            deadline_str = m.group(1) if m else date_text

                    # Ref # lives in <span class="text-small"><b>Ref #: </b>…</span>
                    opp_num = None
                    ref_span = target.find('span', class_=lambda c: c and 'text-small' in c)
                    if ref_span:
                        ref_text = clean_text(ref_span.get_text(' ', strip=True))
                        m = re.search(r'Ref\s*#?:?\s*(.+)', ref_text, flags=re.IGNORECASE)
                        opp_num = (m.group(1) if m else ref_text)[:64] or None

                    anchor = opp_num or title[:80].replace(' ', '_')
                    source_url = detail_url or f"{base_url}#{anchor}"

                    self.add_opportunity({
                        'title': title,
                        'organization': 'State of Washington',
                        'description': None,
                        'eligibility': None,
                        'funding_amount': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'Washington',
                        'source': self.source_name,
                        'source_url': source_url,
                        'opportunity_number': opp_num,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except Exception as e:
                    logger.debug(f"  WA WEBS row failed: {e}")
                    continue
        except Exception as e:
            logger.warning(f"WEBS parse failure: {e}")

    def _scrape_des(self, driver, base_url):
        """DES landing-page link parser, with strict bid-link filtering."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        seen = set()
        for link in soup.find_all('a', href=True):
            if self.reached_limit():
                break
            href = link.get('href', '').strip()
            text = clean_text(link.get_text(' ', strip=True))
            if not href or not text or len(text) < 10:
                continue
            hl = href.lower()
            if hl.startswith(('javascript:', 'mailto:', '#')):
                continue
            tl = text.lower()
            if tl in _NON_BID_TEXTS:
                continue

            full = href if href.startswith('http') else urljoin('https://des.wa.gov', href)
            if full in seen:
                continue

            is_doc = full.lower().endswith(('.pdf', '.doc', '.docx'))
            is_bid_keyword = any(kw in tl for kw in ('bid', 'rfp', 'rfq', 'rfi', 'itb', 'solicitation'))
            if not (is_doc or is_bid_keyword):
                continue
            seen.add(full)

            self.add_opportunity({
                'title': text[:300],
                'organization': 'State of Washington',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(text, ''),
                'location': 'Washington',
                'source': self.source_name,
                'source_url': full,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [full] if is_doc else [],
                'opportunity_type': 'bid',
            })

    def parse_opportunity(self, element):
        """Required by BaseScraper. Row parsing is inlined in scrape()."""
        return None


def get_washington_scrapers():
    return [WashingtonProcurementScraper()]
