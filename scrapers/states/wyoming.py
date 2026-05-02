"""
Wyoming Procurement scraper — A&I General Services Purchasing Bids

Scrapes open bid opportunities from Wyoming's A&I General Services
Purchasing Division. The state migrated active bids to the Public
Purchase / GEMS portal, which the A&I page links to. We follow that
link first and parse the GEMS bid grid; if the GEMS portal is
unreachable we fall back to PDF/doc attachments referenced directly
on the A&I page.

Sources:
  Landing page:   https://ai.wyo.gov/divisions/general-services/purchasing/bid-opportunities
  GEMS portal:    https://www.publicpurchase.com/gems/wyo,state/buyer/public/publicInfo
"""

import re
import time
import random
import urllib.parse

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


# Anchor texts that aren't actual bids but are easy to mistake for one
# (header/footer/nav/breadcrumb links).
_NON_BID_TEXTS = {
    'home', 'about', 'contact', 'home page', 'wyoming.gov', 'state of wyoming',
    'main menu', 'login', 'sign in', 'search', 'register', 'state agencies',
    'site map', 'feedback', 'a&i', 'a & i', 'general services',
    'purchasing', 'bid opportunities', 'previous bids', 'closed bids',
    'view all', 'more', 'back to top', 'subscribe',
}


class WyomingPurchasingScraper(BaseScraper):
    """Scrapes bid opportunities from Wyoming A&I Purchasing + GEMS."""

    BID_URL = "https://ai.wyo.gov/divisions/general-services/purchasing/bid-opportunities"
    BASE_URL = "https://ai.wyo.gov"
    GEMS_URL = (
        "https://www.publicpurchase.com/gems/wyo,state/buyer/public/publicInfo"
    )

    def __init__(self):
        super().__init__("Wyoming A&I Purchasing")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping Wyoming")
            return self.opportunities

        try:
            # 1) Try the GEMS / Public Purchase portal that hosts the actual
            #    open-bid grid. This is what humans actually browse.
            collected = self._scrape_gems_portal(driver)

            # 2) If GEMS yielded nothing (e.g. session-cookie wall), fall back
            #    to the A&I landing page and extract real PDF/HTML bid links.
            if not collected:
                self._scrape_landing_page(driver)

        except Exception as exc:
            logger.error(f"Error scraping Wyoming A&I: {exc}")

        self.log_summary()
        return self.opportunities

    def _scrape_gems_portal(self, driver):
        """Navigate to GEMS Public Purchase and parse the open-bids grid."""
        before = len(self.opportunities)
        try:
            driver.get(self.GEMS_URL)
            time.sleep(random.uniform(8, 12))
        except Exception as exc:
            logger.warning(f"Wyoming GEMS: navigation failed: {exc}")
            return False

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # GEMS uses a standard table for open bids; pick the largest one.
        tables = soup.find_all('table')
        if not tables:
            logger.info("Wyoming GEMS: no tables found")
            return False
        table = max(
            tables,
            key=lambda t: len([r for r in t.find_all('tr') if r.find('td')]),
        )
        rows = [r for r in table.find_all('tr') if r.find('td')]
        if not rows:
            logger.info("Wyoming GEMS: largest table had no data rows")
            return False

        for row in rows:
            if self.reached_limit():
                break
            opp = self._parse_gems_row(row)
            if opp:
                self.add_opportunity(opp)

        added = len(self.opportunities) - before
        logger.info(f"Wyoming GEMS: parsed {len(rows)} rows, {added} captured")
        return added > 0

    def _parse_gems_row(self, row):
        cells = row.find_all('td')
        if len(cells) < 2:
            return None
        try:
            cell_texts = [
                clean_text(c.get_text(separator=' ', strip=True)) for c in cells
            ]
            link = row.find('a', href=True)
            title = None
            detail_url = None
            if link:
                title = clean_text(link.get_text())
                href = (link.get('href') or '').strip()
                if href and not href.lower().startswith(('javascript:', '#', 'mailto:')):
                    detail_url = (
                        href if href.startswith('http')
                        else urllib.parse.urljoin(self.GEMS_URL, href)
                    )
            if not title:
                title = max(cell_texts, key=len) if cell_texts else None
            if not title or len(title) < 5:
                return None

            # Look for a deadline-shaped cell.
            deadline = None
            for txt in cell_texts:
                if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', txt):
                    parsed = parse_date(txt)
                    if parsed:
                        deadline = parsed
                        break

            opp_number = None
            for txt in cell_texts:
                m = re.match(r'^[A-Z0-9][A-Z0-9\-_]{2,30}$', txt)
                if m:
                    opp_number = txt
                    break

            anchor = opp_number or title[:80].replace(' ', '_')
            source_url = detail_url or f"{self.GEMS_URL}#{anchor}"

            return {
                'title': title,
                'organization': 'State of Wyoming',
                'description': '; '.join(t for t in cell_texts if t)[:1000] or None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': categorize_opportunity(title, ''),
                'location': 'Wyoming',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': [detail_url] if detail_url and detail_url.lower().endswith('.pdf') else [],
                'opportunity_type': 'bid',
            }
        except Exception as exc:
            logger.warning(f"Wyoming GEMS row parse failed: {exc}")
            return None

    def _scrape_landing_page(self, driver):
        try:
            driver.get(self.BID_URL)
            time.sleep(random.uniform(6, 10))
        except Exception as exc:
            logger.warning(f"Wyoming landing: navigation failed: {exc}")
            return

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # Drupal/WordPress CMS — restrict to the article body so nav links
        # in the header/footer don't get harvested.
        content = (
            soup.find('article')
            or soup.find('main')
            or soup.find('div', class_=lambda x: x and 'field-items' in str(x))
            or soup.find('div', class_=lambda x: x and 'page-content' in str(x))
            or soup
        )

        # Tables first (Wyoming sometimes posts a small bid table in-page).
        table = content.find('table')
        if table:
            rows = [r for r in table.find_all('tr') if r.find('td')]
            for row in rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    self.add_opportunity(opp)
            logger.info(f"  Parsed {len(rows)} rows from WY A&I in-page table")
            if rows:
                return

        # Otherwise pick only links that point to actual bid documents
        # (PDF/DOC) OR to off-site bid hosts. Generic nav anchors and
        # breadcrumbs are filtered out by text + URL heuristics.
        links = content.find_all('a', href=True)
        for link in links:
            if self.reached_limit():
                break
            href = (link.get('href') or '').strip()
            text = clean_text(link.get_text(strip=True))
            if not text or len(text) < 5:
                continue
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            tl = text.lower()
            if tl in _NON_BID_TEXTS:
                continue

            full_href = (
                href if href.startswith('http')
                else urllib.parse.urljoin(self.BASE_URL + '/', href.lstrip('/'))
            )
            host = urllib.parse.urlparse(full_href).netloc.lower()

            is_doc = full_href.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx'))
            is_external_bid_host = any(h in host for h in (
                'publicpurchase.com', 'bonfirehub.com', 'bidnet.com',
                'periscopeholdings.com', 'bidsync.com', 'opengov.com',
            ))
            mentions_bid = any(kw in tl for kw in ('rfp', 'rfq', 'ifb', 'itb', 'solicitation'))

            if not (is_doc or is_external_bid_host or mentions_bid):
                continue
            # If we matched only by keyword, also require the URL to look
            # bid-shaped — avoids harvesting "Closed Bids" nav pages.
            if mentions_bid and not (is_doc or is_external_bid_host):
                if not re.search(r'(rfp|rfq|ifb|itb|solicitation|bid)', host + full_href, re.IGNORECASE):
                    continue

            opp = self._build_link_opportunity(text, full_href)
            if opp:
                self.add_opportunity(opp)

        logger.info(f"  Parsed bid links from WY A&I landing page")

    def parse_opportunity(self, row):
        cells = row.find_all('td')
        if len(cells) < 2:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]

            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"{self.BASE_URL}{href}"
                if href.lower().endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            title = max(cell_texts, key=len) if cell_texts else None
            if not title or len(title) < 5:
                return None

            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of Wyoming',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'Wyoming',
                'source': self.source_name,
                'source_url': detail_url or self.BID_URL,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing WY row: {e}")
            return None

    def _build_link_opportunity(self, title, url):
        if not title or len(title) < 5:
            return None

        doc_urls = [url] if url.lower().endswith('.pdf') else []
        category = categorize_opportunity(title, '')

        return {
            'title': title,
            'organization': 'State of Wyoming',
            'description': None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': None,
            'category': category,
            'location': 'Wyoming',
            'source': self.source_name,
            'source_url': url,
            'opportunity_number': None,
            'posted_date': None,
            'document_urls': doc_urls,
            'opportunity_type': 'bid',
        }


def get_wyoming_scrapers():
    return [WyomingPurchasingScraper()]


if __name__ == '__main__':
    scraper = WyomingPurchasingScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
