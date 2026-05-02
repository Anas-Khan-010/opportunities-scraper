"""
Nevada Procurement scraper — NevadaEPro (Periscope / BidSync)

Scrapes open bid opportunities from the NevadaEPro platform.
Uses Selenium to wait for Periscope's internal JS to load the table.

Source: https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class NevadaEProScraper(BaseScraper):
    """Scrapes bid opportunities from NevadaEPro (Periscope)."""

    SEARCH_URL = "https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true"
    BASE_URL = "https://nevadaepro.com"

    # Periscope/PrimeFaces 13 sometimes ships the listing under either
    # bidDetail.sdo (legacy) or bidDetail.xhtml (current). Both must match.
    _DETAIL_MARKERS = ('/bso/external/bidDetail.sdo', '/bso/external/bidDetail.xhtml')

    def __init__(self):
        super().__init__("NevadaEPro")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error(f"Selenium driver unavailable — skipping {self.source_name}")
            return self.opportunities

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            driver.get(self.SEARCH_URL)
            # Wait for the PrimeFaces datatable to materialize before parsing.
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'table.ui-datatable-data tr, table[id*="bidSearch"] tr')
                    )
                )
            except Exception:
                logger.debug("Nevada: data table didn't appear via WebDriverWait; continuing")
            time.sleep(random.uniform(3, 6))

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            table = (
                soup.find('table', id=lambda x: x and 'bidSearchResultsTable' in str(x))
                or soup.find('table', class_=lambda x: x and 'ui-datatable-data' in str(x))
                or soup.find('table', class_=lambda x: x and 'ui-datatable' in str(x))
            )
            if not table:
                # Fall back to whichever table has the most data rows.
                tables = soup.find_all('table')
                if tables:
                    table = max(
                        tables,
                        key=lambda t: len([r for r in t.find_all('tr') if r.find('td')]),
                    )
            if not table:
                logger.warning(f"No results table found on {self.source_name}")
                self.log_summary()
                return self.opportunities

            # Build a header-name → index map so we don't depend on column order.
            header_map = self._extract_header_map(table)

            rows = table.find_all('tr')
            data_rows = [r for r in rows if r.find('td')]

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self.parse_row(row, header_map)
                if opp:
                    self.add_opportunity(opp)

            logger.info(f"  Parsed {len(data_rows)} rows from {self.source_name}")

        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")

        self.log_summary()
        return self.opportunities

    def _extract_header_map(self, table):
        """Map normalized header label -> cell index."""
        head_row = table.find('tr')
        if not head_row:
            return {}
        cells = head_row.find_all(['th', 'td'])
        m = {}
        for idx, c in enumerate(cells):
            label = (clean_text(c.get_text(separator=' ', strip=True)) or '').lower()
            if not label:
                continue
            m[label] = idx
        return m

    @staticmethod
    def _idx_for(header_map, *keywords):
        """Pick the first column index whose label contains any of the keywords."""
        for label, idx in header_map.items():
            for kw in keywords:
                if kw in label:
                    return idx
        return None

    def parse_row(self, row, header_map):
        """Parse a Periscope row using header-aware column lookup."""
        cells = row.find_all('td')
        if len(cells) < 4:
            return None

        try:
            cell_texts = [clean_text(c.get_text(separator=' ', strip=True)) for c in cells]

            i_num = self._idx_for(header_map, 'solicitation', 'bid #', 'bid number')
            i_org = self._idx_for(header_map, 'organization', 'agency', 'department')
            i_buyer = self._idx_for(header_map, 'buyer', 'contact')
            i_desc = self._idx_for(header_map, 'description', 'title')
            i_deadline = self._idx_for(header_map, 'opening', 'closing', 'due', 'close date')
            i_status = self._idx_for(header_map, 'status')

            def at(i):
                if i is None or i >= len(cell_texts):
                    return ''
                return cell_texts[i]

            opp_number = at(i_num) or (cell_texts[0] if cell_texts else '')
            org = at(i_org)
            buyer = at(i_buyer)
            title = at(i_desc) or opp_number
            deadline_str = at(i_deadline)
            status = at(i_status)

            if not title or title.lower() in ('description', 'title'):
                title = opp_number
            if not title:
                return None

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
                source_url = f"{self.SEARCH_URL}#{opp_number}"
            else:
                source_url = f"{self.SEARCH_URL}#{title[:80].replace(' ', '_')}"

            category = categorize_opportunity(title, '')

            desc_parts = []
            if buyer:
                desc_parts.append(f"Buyer: {buyer}")
            if status:
                desc_parts.append(f"Status: {status}")
            description = '; '.join(desc_parts) if desc_parts else None

            return {
                'title': title,
                'organization': org or 'State of Nevada',
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Nevada',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing Nevada row: {e}")
            return None

    def parse_opportunity(self, element):
        # Required by BaseScraper. Use parse_row(row, header_map) inside scrape().
        return None


def get_nevada_scrapers():
    return [NevadaEProScraper()]


if __name__ == '__main__':
    scraper = NevadaEProScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
