"""
Arkansas Procurement scraper — ARBuy (Periscope/BuySpeed PrimeFaces portal)

ARBuy actually runs on Periscope/BuySpeed (a JSF/PrimeFaces app), NOT
Ivalua. Public bids live under ``/bso/external/publicBids.sdo``. The
old code targeted an Ivalua URL/markup that never matches and silently
swallowed every row.

Source listing: https://arbuy.arkansas.gov/bso/external/publicBids.sdo
Detail pages:   https://arbuy.arkansas.gov/bso/external/bidDetail.sdo?bidId=...
"""

import time
import random

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class ArkansasProcurementScraper(BaseScraper):
    """Scrapes open bids from ARBuy (Periscope/BuySpeed)."""

    BASE_URL = "https://arbuy.arkansas.gov"
    SEARCH_URLS = [
        f"{BASE_URL}/bso/external/publicBids.sdo",
        # Fallback to the JSF-style URL some BuySpeed deployments expose.
        f"{BASE_URL}/bso/view/search/external/advancedSearchBid.xhtml?openBids=true",
    ]
    _DETAIL_MARKERS = ('/bso/external/bidDetail.sdo', '/bso/external/bidDetail.xhtml')

    def __init__(self):
        super().__init__("Arkansas ARBuy Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        # ARBuy responds 200 to direct hits; no proxy / Cloudflare bypass needed.
        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping Arkansas")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(6, 10))

                if self._scrape_buyspeed(driver, url):
                    break
            except Exception as exc:
                logger.warning(f"Arkansas: error at {url}: {exc}")

        self.log_summary()
        return self.opportunities

    def _scrape_buyspeed(self, driver, listing_url):
        """Parse the BuySpeed/PrimeFaces public bids table on the current page."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # BuySpeed/PrimeFaces uses ui-datatable-data; older deployments use
        # a generic <table> inside the form. Pick the table with the most
        # data rows defensively.
        tables = soup.find_all('table')
        if not tables:
            logger.info("Arkansas: no tables on page")
            return False
        table = max(
            tables,
            key=lambda t: len([r for r in t.find_all('tr') if r.find('td')]),
        )

        header_map = self._extract_header_map(table)
        rows = [r for r in table.find_all('tr') if r.find('td')]
        if not rows:
            logger.info("Arkansas: data table found but no rows")
            return False

        before = len(self.opportunities)
        for row in rows:
            if self.reached_limit():
                break
            opp = self._parse_row(row, header_map, listing_url)
            if opp:
                self.add_opportunity(opp)

        logger.info(
            f"Arkansas: parsed {len(rows)} rows, "
            f"{len(self.opportunities) - before} new opportunities"
        )
        return len(self.opportunities) > before

    @staticmethod
    def _extract_header_map(table):
        head = table.find('tr')
        if not head:
            return {}
        cells = head.find_all(['th', 'td'])
        out = {}
        for idx, c in enumerate(cells):
            label = (clean_text(c.get_text(separator=' ', strip=True)) or '').lower()
            if label:
                out[label] = idx
        return out

    @staticmethod
    def _idx_for(header_map, *keywords):
        for label, idx in header_map.items():
            for kw in keywords:
                if kw in label:
                    return idx
        return None

    def _parse_row(self, row, header_map, listing_url):
        cells = row.find_all('td')
        if len(cells) < 3:
            return None

        try:
            cell_texts = [clean_text(c.get_text(separator=' ', strip=True)) for c in cells]

            i_num = self._idx_for(header_map, 'bid #', 'solicitation', 'bid number')
            i_desc = self._idx_for(header_map, 'description', 'title')
            i_org = self._idx_for(header_map, 'agency', 'department', 'organization', 'buyer')
            i_open = self._idx_for(header_map, 'open date', 'posted', 'issued')
            i_close = self._idx_for(header_map, 'close date', 'closing', 'opening', 'due')

            def at(i):
                if i is None or i >= len(cell_texts):
                    return ''
                return cell_texts[i]

            opp_number = at(i_num) or (cell_texts[0] if cell_texts else '')
            title = at(i_desc) or (cell_texts[1] if len(cell_texts) > 1 else '')
            org = at(i_org)
            posted_str = at(i_open)
            deadline_str = at(i_close)

            if not title or len(title) < 5:
                return None

            posted_date = parse_date(posted_str) if posted_str else None
            deadline = parse_date(deadline_str) if deadline_str else None

            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = (link.get('href') or '').strip()
                if not href:
                    continue
                hl = href.lower()
                if hl.startswith(('javascript:', 'mailto:', '#')):
                    continue
                if not href.startswith('http'):
                    href = self.BASE_URL + ('' if href.startswith('/') else '/') + href.lstrip('/')

                if any(m in hl for m in self._DETAIL_MARKERS):
                    detail_url = href
                elif hl.endswith(('.pdf', '.doc', '.docx')):
                    doc_urls.append(href)

            if detail_url:
                source_url = detail_url
            elif opp_number:
                source_url = f"{listing_url}#{opp_number}"
            else:
                source_url = f"{listing_url}#{title[:80].replace(' ', '_')}"

            description_parts = []
            if posted_str:
                description_parts.append(f"Open: {posted_str}")
            if deadline_str:
                description_parts.append(f"Close: {deadline_str}")
            description = '; '.join(description_parts) if description_parts else None

            return {
                'title': title,
                'organization': org or 'State of Arkansas',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': categorize_opportunity(title, description or ''),
                'location': 'Arkansas',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number or None,
                'posted_date': posted_date,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as exc:
            logger.warning(f"Arkansas: row parse failed: {exc}")
            return None

    def parse_opportunity(self, element):
        return None


def get_arkansas_scrapers():
    return [ArkansasProcurementScraper()]
