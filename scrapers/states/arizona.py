"""
Arizona Procurement Portal scraper — APP (Ivalua platform).

Source: https://app.az.gov/page.aspx/en/rfp/request_browse_public

Notes:
  - The portal serves the full Ivalua RFx grid as static HTML — JS isn't
    required and direct ``requests`` calls return 200 with the complete
    payload. We use HTTP first; Selenium remains as a fallback because
    headless Chrome was crashing on this page in QA.
  - Header-aware column mapping (Arizona labels the title column "Label",
    not "Title", so we whitelist that explicitly).
  - The detail-page URL pattern is ``/page.aspx/en/bpm/process_manage_extranet/<id>``.
"""

import random
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class ArizonaProcurementPortalScraper(BaseScraper):
    """Scrapes RFPs and Bids from the Arizona Procurement Portal (APP) — Ivalua."""

    SEARCH_URL = "https://app.az.gov/page.aspx/en/rfp/request_browse_public"
    BASE = "https://app.az.gov"

    def __init__(self):
        super().__init__("Arizona Procurement Portal")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        html = self._fetch_html_first()
        if html is None:
            html = self._fetch_via_selenium()

        if not html:
            logger.error("Arizona APP: could not fetch listing via HTTP or Selenium")
            self.log_summary()
            return self.opportunities

        if "Just a moment" in html or "cf-chl" in html:
            logger.warning("Arizona APP: landed on Cloudflare interstitial")
            self.log_summary()
            return self.opportunities

        soup = BeautifulSoup(html, 'html.parser')
        self._parse_grid(soup)

        self.log_summary()
        return self.opportunities

    def _fetch_html_first(self):
        """Try plain HTTP first — Ivalua serves the grid as static HTML here."""
        try:
            resp = self.fetch_page(self.SEARCH_URL, timeout=30)
            if resp is not None and resp.text and 'grid' in resp.text.lower():
                logger.info("Arizona APP: fetched via HTTP (no Selenium)")
                return resp.text
        except Exception as exc:
            logger.debug(f"Arizona APP: HTTP fetch failed: {exc}")
        return None

    def _fetch_via_selenium(self):
        """Selenium fallback if HTTP doesn't return a usable grid."""
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            return None
        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(8, 12))
            if "Just a moment" in driver.page_source:
                logger.info("  Arizona APP: waiting for Cloudflare bypass...")
                time.sleep(15)
            return driver.page_source
        except Exception as exc:
            logger.warning(f"Arizona APP: Selenium fetch failed: {exc}")
            return None

    def _parse_grid(self, soup):
        """Parse the Ivalua RFx grid using header-aware column mapping."""
        target_table = None
        header_map = {}
        for table in soup.find_all('table'):
            head = table.find('thead') or table.find('tr')
            if not head:
                continue
            cells = head.find_all(['th', 'td'])
            # clean_text returns None for empty input, so coerce to '' before
            # .lower() — Ivalua header rows include empty spacer/action <th>s.
            labels = [
                ((clean_text(c.get_text(' ', strip=True)) or '').lower())
                for c in cells
            ]
            joined = ' '.join(labels)
            if not any(kw in joined for kw in ('label', 'title', 'reference', 'rfx', 'agency', 'commodity')):
                continue
            for i, label in enumerate(labels):
                if label and label not in header_map:
                    header_map[label] = i
            target_table = table
            break

        if target_table is None:
            logger.warning("Arizona APP: no Ivalua grid table found on page")
            return

        tbody = target_table.find('tbody')
        rows = tbody.find_all('tr') if tbody else target_table.find_all('tr')[1:]

        def _idx(*needles):
            for needle in needles:
                for label, idx in header_map.items():
                    if needle in label:
                        return idx
            return None

        # Arizona Ivalua headers: Code, Label, Publication begin date, Commodity,
        # Agency, Publication end date, Status, RFx Awarded, Remaining time, Begin, End, Editing
        i_num = _idx('code', 'reference', 'rfx number')
        i_title = _idx('label', 'title', 'object', 'name', 'description')
        i_type = _idx('rfx type', 'type', 'family', 'commodity')
        i_org = _idx('agency', 'organization', 'department', 'buyer')
        # Arizona's "Publication end date" column is virtually always empty.
        # The real bid-submission deadline is in "End (UTC-7)". Prefer it.
        i_deadline = _idx('end (utc', 'close', 'due', 'publication end', 'end date', 'opening')

        parsed = 0
        for row in rows:
            if self.reached_limit():
                break
            cells = row.find_all('td')
            if len(cells) < 4:
                continue

            try:
                def _cell(i):
                    if i is not None and i < len(cells):
                        return clean_text(cells[i].get_text(' ', strip=True))
                    return ''

                opp_num = _cell(i_num)
                title = _cell(i_title)
                rfx_type = _cell(i_type)
                org = _cell(i_org)
                deadline_str = _cell(i_deadline)

                if not title or len(title) < 5:
                    continue

                detail_url = None
                for link in row.find_all('a', href=True):
                    href = link.get('href', '').strip()
                    if not href:
                        continue
                    hl = href.lower()
                    if hl.startswith(('javascript:', 'mailto:', '#')):
                        continue
                    detail_url = href if href.startswith('http') else urljoin(self.BASE, href)
                    break

                anchor = opp_num or title[:80].replace(' ', '_')
                source_url = detail_url or f"{self.SEARCH_URL}#{anchor}"

                self.add_opportunity({
                    'title': title,
                    'organization': org or "State of Arizona",
                    'description': f"Commodity: {rfx_type}" if rfx_type else None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, rfx_type or ''),
                    'location': 'Arizona',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_num,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'rfp',
                })
                parsed += 1
            except Exception as e:
                logger.debug(f"  Arizona row parse failed: {e}")
                continue

        logger.info(f"Arizona APP: parsed {parsed} opportunities from grid")

    def parse_opportunity(self, element):
        """Required by BaseScraper. Row parsing is inlined in _parse_grid."""
        return None


def get_arizona_scrapers():
    return [ArizonaProcurementPortalScraper()]
