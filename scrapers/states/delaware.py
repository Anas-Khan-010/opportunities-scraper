"""
Delaware MarketPlace (MMP) Bids scraper — mmp.delaware.gov

Scrapes bid solicitations (RFP, RFQ, RFI, ITB) from the State of
Delaware's central procurement portal. The site is a hash-routed
single-page application requiring Selenium.

Each listing provides title, bid number, agency, type, deadline, and
status. Detail pages link to PDF attachments for full solicitation
documents. PDF enrichment extracts description, eligibility, and
funding_amount.

Source: https://mmp.delaware.gov/Bids/#
"""

import time
import random
import re
import urllib.parse

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


PORTAL_URL = "https://mmp.delaware.gov/Bids/"
DETAIL_BASE = "https://mmp.delaware.gov"
DELAY_LOAD = (6, 12)
DELAY_BETWEEN_PAGES = (3, 6)
DELAY_BETWEEN_DETAILS = (2, 4)


class DelawareBidsScraper(BaseScraper):
    """Scrapes Delaware MMP bid solicitations via Selenium + PDF enrichment."""

    def __init__(self):
        super().__init__("Delaware Bids")
        self.max_pages = getattr(config, "DE_BIDS_MAX_PAGES", 10)

    def scrape(self):
        logger.info("Starting Delaware Bids scraper (Selenium SPA + PDF enrichment)...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping Delaware")
            return self.opportunities

        self._scrape_listings(driver)
        self.log_summary()
        return self.opportunities

    def _scrape_listings(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            logger.info("Delaware: loading MMP Bids portal...")
            driver.get(PORTAL_URL)
            time.sleep(random.uniform(*DELAY_LOAD))

            WebDriverWait(driver, 45).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(random.uniform(5, 10))

            self._wait_for_content(driver)

        except Exception as exc:
            logger.error(f"Delaware: failed to load portal: {exc}")
            return

        page = 1
        while page <= self.max_pages and not self.reached_limit():
            logger.info(f"Delaware Bids: parsing page {page}...")

            try:
                soup = self.parse_html(driver.page_source)
                rows = self._extract_bid_rows(soup)

                if not rows:
                    logger.info(f"Delaware: no bid rows on page {page}, stopping.")
                    break

                page_new = 0
                for row_data in rows:
                    opp = self._build_opportunity(row_data)
                    if opp:
                        self._enrich_from_detail_page(driver, opp)
                        if opp.get('document_urls'):
                            self.enrich_from_documents(opp)
                        is_new = self.add_opportunity(opp)
                        if is_new:
                            page_new += 1
                        if self.reached_limit():
                            break

                logger.info(f"Delaware: page {page} — {len(rows)} rows, {page_new} new")

                if self.reached_limit():
                    break
                if not self._go_to_next_page(driver):
                    break
                page += 1
                time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

            except Exception as exc:
                logger.error(f"Delaware: error on page {page}: {exc}")
                break

    def _wait_for_content(self, driver):
        """Wait for dynamic bid content to appear in the SPA."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        selectors = [
            'table tbody tr', '.bid-row', '.bid-item',
            'tr[data-bid]', '.card', '.list-group-item',
            'table tr td',
        ]
        for sel in selectors:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                logger.debug(f"Delaware: content found with selector '{sel}'")
                return
            except Exception:
                continue

        logger.warning("Delaware: timed out waiting for bid content to load")

    def _extract_bid_rows(self, soup):
        """Parse bid entries from the rendered DOM."""
        rows = []

        # Delaware uses a jqGrid table with ID 'jqGridBids'
        table = soup.find('table', id='jqGridBids') or soup.find('table')
        if table:
            for tr in table.find_all('tr'):
                cells = tr.find_all('td')
                if len(cells) < 2:
                    continue
                row_data = self._parse_table_row(cells, tr)
                if row_data:
                    rows.append(row_data)
            if rows:
                return rows

        card_selectors = [
            '.bid-item', '.bid-row', '.card', '.list-group-item',
            'div[class*="bid"]', 'div[class*="solicitation"]',
        ]
        for sel in card_selectors:
            cards = soup.select(sel)
            if cards:
                for card in cards:
                    row_data = self._parse_card(card)
                    if row_data:
                        rows.append(row_data)
                if rows:
                    return rows

        return rows

    def _parse_table_row(self, cells, tr):
        """Parse a standard table row into structured data."""
        full_text = tr.get_text(separator=' ', strip=True)
        if len(full_text) < 10:
            return None

        link = tr.find('a', href=True)
        title = clean_text(link.get_text()) if link else clean_text(cells[0].get_text())
        detail_url = link['href'] if link else None

        if not title or len(title) < 3:
            return None

        data = {
            'title': title,
            'detail_url': detail_url,
            'bid_number': None,
            'agency': None,
            'bid_type': None,
            'deadline': None,
            'status': None,
        }

        for cell in cells:
            text = clean_text(cell.get_text())
            if not text:
                continue
            text_lower = text.lower()

            if re.match(r'^[A-Z]{2,5}[-_]\d', text):
                data['bid_number'] = text
            elif text_lower in ('open', 'closed', 'awarded', 'pending', 'active'):
                data['status'] = text
            elif text_lower in ('rfp', 'rfq', 'rfi', 'itb', 'ifb'):
                data['bid_type'] = text
            elif re.match(r'\d{1,2}/\d{1,2}/\d{2,4}', text):
                if not data['deadline']:
                    data['deadline'] = text

        return data

    def _parse_card(self, card):
        """Parse a card-style DOM element."""
        link = card.find('a', href=True)
        title = None
        detail_url = None

        if link:
            title = clean_text(link.get_text())
            detail_url = link['href']

        if not title:
            h_tag = card.find(re.compile(r'^h[1-6]$'))
            if h_tag:
                title = clean_text(h_tag.get_text())

        if not title:
            title = clean_text(card.get_text())[:200]

        if not title or len(title) < 5:
            return None

        return {
            'title': title,
            'detail_url': detail_url,
            'bid_number': None,
            'agency': None,
            'bid_type': None,
            'deadline': None,
            'status': None,
        }

    def _build_opportunity(self, data):
        title = data['title']
        if not title:
            return None

        # Prefer bookmarkable Detail URLs if reachable
        source_url = data.get('detail_url') or PORTAL_URL
        if source_url and not source_url.startswith('http'):
            # Delaware detail links often look like /Bids/Details/123
            source_url = urllib.parse.urljoin(DETAIL_BASE, source_url)

        deadline = parse_date(data['deadline']) if data.get('deadline') else None

        desc_parts = []
        if data.get('bid_type'):
            desc_parts.append(f"Type: {data['bid_type']}")
        if data.get('status'):
            desc_parts.append(f"Status: {data['status']}")
        if data.get('bid_number'):
            desc_parts.append(f"Bid #: {data['bid_number']}")
        description = '; '.join(desc_parts) if desc_parts else None

        opp_type = 'rfp'
        if data.get('bid_type'):
            bt = data['bid_type'].upper()
            if any(k in bt for k in ('RFI', 'REQUEST FOR INFORMATION')):
                opp_type = 'rfi'

        category = categorize_opportunity(title, description or '')

        return {
            'title': title,
            'organization': data.get('agency') or 'State of Delaware',
            'description': description,
            'eligibility': None,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': 'Delaware',
            'source': self.source_name,
            'source_url': source_url,
            'opportunity_number': data.get('bid_number'),
            'posted_date': None,
            'document_urls': [],
            'opportunity_type': opp_type,
        }

    def _enrich_from_detail_page(self, driver, opp):
        """Navigate to a bid detail page and extract all PDF/DOC links."""
        detail_url = opp.get('source_url', '')
        if not detail_url or 'Details/' not in detail_url:
            return

        try:
            time.sleep(random.uniform(*DELAY_BETWEEN_DETAILS))
            driver.get(detail_url)
            time.sleep(random.uniform(5, 9))

            soup = self.parse_html(driver.page_source)

            # Capture all links in the main content area that look like documents
            doc_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                # Match common document extensions or Delaware's internal document viewer links
                if (any(href.lower().endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip')) 
                    or 'DownloadFile' in href or 'ViewFile' in href):
                    full_url = href if href.startswith('http') else urllib.parse.urljoin(DETAIL_BASE, href)
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            
            if doc_urls:
                opp['document_urls'] = doc_urls[:15]

            full_text = soup.get_text(separator='\n', strip=True)
            
            # Look for contact email
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', full_text)
            if email_match and opp.get('description'):
                email = email_match.group(0)
                if email not in opp['description']:
                    opp['description'] = f"{opp['description']}; Contact: {email}"[:2000]

            if not opp.get('description') or len(opp.get('description', '')) < 100:
                desc_block = self._extract_section(full_text, [
                    'Description', 'Scope of Work', 'Summary', 'Purpose', 'Introduction',
                ])
                if desc_block:
                    existing = opp.get('description') or ''
                    opp['description'] = f"{desc_block}\n{existing}".strip()[:2000]

            driver.back()
            time.sleep(random.uniform(2, 4))

        except Exception as exc:
            logger.debug(f"Delaware: detail page failed for {detail_url}: {exc}")

    def _extract_section(self, full_text, header_keywords):
        for keyword in header_keywords:
            pattern = re.compile(
                rf'{re.escape(keyword)}\s*[:\-—]?\s*\n?(.*?)(?:\n[A-Z][A-Za-z ]+[:\-—]|\Z)',
                re.IGNORECASE | re.DOTALL,
            )
            m = pattern.search(full_text)
            if m:
                text = m.group(1).strip()
                if text and len(text) > 10:
                    return text[:1500]
        return None

    def _go_to_next_page(self, driver):
        from selenium.webdriver.common.by import By
        try:
            next_btns = driver.find_elements(
                By.XPATH,
                "//a[contains(text(), 'Next') or contains(@aria-label, 'Next')]"
            )
            if not next_btns:
                next_btns = driver.find_elements(
                    By.CSS_SELECTOR, '.pagination .next a, button.next-page'
                )

            for btn in next_btns:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    time.sleep(random.uniform(*DELAY_LOAD))
                    return True

            return False
        except Exception as exc:
            logger.debug(f"Delaware: pagination failed: {exc}")
            return False

    def parse_opportunity(self, element):
        return None


def get_delaware_scrapers():
    return [DelawareBidsScraper()]
