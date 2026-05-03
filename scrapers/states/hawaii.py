"""
Hawaii Procurement scraper — HANDS (Hawaii Awards & Notices Data System)

Scrapes open solicitation opportunities from the HANDS portal,
which aggregates procurement data from multiple Hawaii government
agencies onto a single SPA.

Source: https://hands.ehawaii.gov/hands/opportunities
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class HawaiiHANDSScraper(BaseScraper):
    """Scrapes solicitation opportunities from Hawaii HANDS."""

    SEARCH_URL = "https://hands.ehawaii.gov/hands/opportunities"

    def __init__(self):
        super().__init__("Hawaii HANDS")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver()
        if not driver:
            logger.error("Selenium driver unavailable — skipping Hawaii")
            return self.opportunities

        try:
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(8, 12))  # SPA needs time to render

            page = 1
            seen_keys = set()
            while page <= 10 and not self.reached_limit():
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                # HANDS renders multiple tables; pick the one with the most data rows
                tables = soup.find_all('table')
                if not tables:
                    logger.warning("No table found on Hawaii HANDS page")
                    break

                table = max(
                    tables,
                    key=lambda t: len([r for r in t.find_all('tr') if r.find('td')]),
                )
                rows = table.find_all('tr')
                data_rows = [r for r in rows if r.find('td')]
                if not data_rows:
                    logger.info(f"Hawaii HANDS: no data rows on page {page}, stopping.")
                    break

                page_new = 0
                for row in data_rows:
                    if self.reached_limit():
                        break
                    opp = self.parse_opportunity(row)
                    if not opp:
                        continue
                    key = opp.get('source_url')
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    if self.add_opportunity(opp):
                        page_new += 1

                logger.info(
                    f"Hawaii HANDS: page {page} — {len(data_rows)} rows, {page_new} new"
                )

                if self.reached_limit() or not self._go_to_next_page(driver):
                    break
                page += 1
                time.sleep(random.uniform(3, 6))

        except Exception as e:
            logger.error(f"Error scraping Hawaii HANDS: {e}")

        self.log_summary()
        return self.opportunities

    def _go_to_next_page(self, driver):
        """Click HANDS' 'Next' pager link if present."""
        from selenium.webdriver.common.by import By
        try:
            candidates = driver.find_elements(
                By.CSS_SELECTOR,
                'a.next, a[aria-label="Next"], li.next a, a.paginate_button.next',
            )
            for el in candidates:
                cls = (el.get_attribute('class') or '').lower()
                if 'disabled' in cls:
                    continue
                if not el.is_displayed() or not el.is_enabled():
                    continue
                el.click()
                time.sleep(random.uniform(4, 7))
                return True
        except Exception as exc:
            logger.debug(f"Hawaii HANDS: pagination failed: {exc}")
        return False

    def parse_opportunity(self, row):
        """
        Parse a table row from the HANDS table.
        Columns: (checkbox), Solicitation #, Title, Category, Jurisdiction,
                 Department, Island, Published Date, Offer Due Date & Time (HST)
        """
        cells = row.find_all('td')
        if len(cells) < 5:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]

            # Skip empty rows
            if not any(t for t in cell_texts if t):
                return None

            # Column indices: 0=checkbox, 1=Solicitation#, 2=Title, 3=Category,
            # 4=Jurisdiction, 5=Department, 6=Island, 7=Published Date, 8=Offer Due Date
            opp_number = cell_texts[1] if len(cell_texts) > 1 else ''
            title = cell_texts[2] if len(cell_texts) > 2 else ''
            category_raw = cell_texts[3] if len(cell_texts) > 3 else ''
            jurisdiction = cell_texts[4] if len(cell_texts) > 4 else ''
            department = cell_texts[5] if len(cell_texts) > 5 else ''
            island = cell_texts[6] if len(cell_texts) > 6 else ''
            posted_str = cell_texts[7] if len(cell_texts) > 7 else ''
            deadline_str = cell_texts[8] if len(cell_texts) > 8 else ''

            if not title and not opp_number:
                return None
            if not title:
                title = opp_number

            deadline = parse_date(deadline_str) if deadline_str else None
            posted_date = parse_date(posted_str) if posted_str else None

            # Build organization from jurisdiction + department
            org_parts = [p for p in [jurisdiction, department] if p]
            org = ' - '.join(org_parts) if org_parts else 'State of Hawaii'

            # Links — reject javascript:/#/mailto: hrefs BEFORE prepending host
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
                    href = f"https://hands.ehawaii.gov{href}"
                if hl.endswith('.pdf'):
                    doc_urls.append(href)
                elif '/hands/opportunities/' in hl:
                    detail_url = href
                elif not detail_url:
                    detail_url = href

            # Build a stable per-row fallback so dedup doesn't collapse every
            # row to SEARCH_URL on listing-only views.
            if detail_url:
                source_url = detail_url
            else:
                anchor = opp_number or title[:80].replace(' ', '_')
                source_url = f"{self.SEARCH_URL}#{anchor}"

            # Map raw category
            category = categorize_opportunity(title, category_raw)

            # Determine type from category
            opp_type = 'bid'
            if category_raw.lower() in ('goods', 'services', 'construction'):
                opp_type = 'bid'
            elif 'grant' in category_raw.lower():
                opp_type = 'grant'

            location = f"Hawaii - {island}" if island else 'Hawaii'

            description = f"Category: {category_raw}" if category_raw else None

            return {
                'title': title,
                'organization': org,
                'description': description,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': posted_date,
                'document_urls': doc_urls,
                'opportunity_type': opp_type,
            }

        except Exception as e:
            logger.warning(f"Error parsing Hawaii row: {e}")
            return None


def get_hawaii_scrapers():
    return [HawaiiHANDSScraper()]


if __name__ == '__main__':
    scraper = HawaiiHANDSScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
