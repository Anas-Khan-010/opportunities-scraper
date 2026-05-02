"""
West Virginia Procurement scraper — WV Purchasing Division Bids

The wvOASIS VSS host (``vss.wvoasis.gov``) requires authenticated
sessions and is unreliable from external networks (DNS / connect
timeouts during QA). The legacy bid bulletin at
``state.wv.us/admin/purchase/Bids/`` remains the most reliable
public source: it lists open solicitations as PDF links grouped by
date/agency.

We keep VSS configured as an optional secondary URL (in case the
network changes), but the primary ingestion path is now the legacy
listing — which is what humans actually browse — and we explicitly
filter out non-bid links (header/footer/nav links) so we don't
harvest junk like the QA wave 3i flagged.

Source: https://www.state.wv.us/admin/purchase/Bids/
"""

import re
import time
import random
import urllib.parse

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


_NON_BID_TEXTS = {
    'home', 'back', 'top', 'bottom', 'next', 'previous', 'wv.gov',
    'state of west virginia', 'state of wv', 'purchasing division',
    'mailto', 'email', 'contact', 'help', 'login', 'sign in',
    'pdf reader', 'adobe reader', 'site map', 'feedback',
}


class WestVirginiaProcurementScraper(BaseScraper):
    """Scrapes WV Purchasing Division bid bulletin (PDF-driven)."""

    LEGACY_URL = "https://www.state.wv.us/admin/purchase/Bids/"
    LEGACY_BASE = "https://www.state.wv.us/admin/purchase/Bids/"
    # VSS is kept here for documentation; not used unless a future fix
    # restores network reachability and a real session flow.
    VSS_URL = "https://vss.wvoasis.gov/"

    def __init__(self):
        super().__init__("West Virginia Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping West Virginia")
            return self.opportunities

        try:
            logger.info(f"  Accessing {self.LEGACY_URL}...")
            driver.get(self.LEGACY_URL)
            time.sleep(random.uniform(6, 10))
            self._scrape_legacy(driver)
        except Exception as exc:
            logger.error(f"West Virginia: error scraping legacy bid bulletin: {exc}")

        self.log_summary()
        return self.opportunities

    def _scrape_legacy(self, driver):
        """Parse the legacy purchasing division bid bulletin.

        The page is a flat list of PDF/HTM links (and sometimes embedded
        tables). We extract bid documents only — explicitly filtering
        out navigation links, mailto links, and JS / hash anchors.
        """
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Tables (when present) tend to be the cleanest source.
        tables = soup.find_all('table')
        if tables:
            table = max(
                tables,
                key=lambda t: len([r for r in t.find_all('tr') if r.find('td')]),
            )
            rows = [r for r in table.find_all('tr') if r.find('td')]
            for row in rows:
                if self.reached_limit():
                    return
                opp = self._parse_table_row(row)
                if opp:
                    self.add_opportunity(opp)
            if rows:
                logger.info(f"  Parsed {len(rows)} rows from WV bulletin table")
                return

        # Fallback: pure link extraction with strict filtering.
        seen = set()
        captured = 0
        for a in soup.find_all('a', href=True):
            if self.reached_limit():
                break
            href = (a.get('href') or '').strip()
            text = clean_text(a.get_text(separator=' ', strip=True))
            if not href or not text or len(text) < 6:
                continue
            hl = href.lower()
            if hl.startswith(('javascript:', '#', 'mailto:', 'tel:')):
                continue
            if text.lower() in _NON_BID_TEXTS:
                continue

            full_href = (
                href if href.startswith('http')
                else urllib.parse.urljoin(self.LEGACY_BASE, href)
            )

            is_doc = full_href.lower().endswith(('.pdf', '.doc', '.docx'))
            mentions_bid = any(
                kw in text.lower()
                for kw in ('rfp', 'rfq', 'ifb', 'itb', 'solicitation', 'bid', 'eoi')
            )
            if not (is_doc or mentions_bid):
                continue
            if full_href in seen:
                continue
            seen.add(full_href)

            opp = self._build_link_opportunity(text, full_href)
            if opp and self.add_opportunity(opp):
                captured += 1

        logger.info(f"  Captured {captured} bid links from WV bulletin")

    def _parse_table_row(self, row):
        cells = row.find_all('td')
        if len(cells) < 2:
            return None
        try:
            cell_texts = [
                clean_text(c.get_text(separator=' ', strip=True)) for c in cells
            ]
            link = row.find('a', href=True)
            if not link:
                return None
            href = (link.get('href') or '').strip()
            if not href or href.lower().startswith(('javascript:', '#', 'mailto:')):
                return None
            full_href = (
                href if href.startswith('http')
                else urllib.parse.urljoin(self.LEGACY_BASE, href)
            )

            title = clean_text(link.get_text(separator=' ', strip=True))
            if not title or len(title) < 5:
                title = max(cell_texts, key=len) if cell_texts else ''
            if not title or len(title) < 5:
                return None

            opp_number = None
            for txt in cell_texts:
                if re.match(r'^[A-Z0-9][A-Z0-9\-_]{2,30}$', txt):
                    opp_number = txt
                    break

            deadline = None
            for txt in cell_texts:
                if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', txt):
                    deadline = parse_date(txt)
                    if deadline:
                        break

            return {
                'title': title,
                'organization': 'State of West Virginia',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': categorize_opportunity(title, ''),
                'location': 'West Virginia',
                'source': self.source_name,
                'source_url': full_href,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': [full_href] if full_href.lower().endswith('.pdf') else [],
                'opportunity_type': 'bid',
            }
        except Exception as exc:
            logger.warning(f"WV row parse failed: {exc}")
            return None

    def _build_link_opportunity(self, title, url):
        if not title or len(title) < 5:
            return None
        doc_urls = [url] if url.lower().endswith('.pdf') else []
        return {
            'title': title,
            'organization': 'State of West Virginia',
            'description': None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': None,
            'category': categorize_opportunity(title, ''),
            'location': 'West Virginia',
            'source': self.source_name,
            'source_url': url,
            'opportunity_number': None,
            'posted_date': None,
            'document_urls': doc_urls,
            'opportunity_type': 'bid',
        }

    def parse_opportunity(self, element):
        # Required by BaseScraper. Row parsing is inlined in scrape().
        return None


def get_west_virginia_scrapers():
    return [WestVirginiaProcurementScraper()]


if __name__ == '__main__':
    scraper = WestVirginiaProcurementScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
