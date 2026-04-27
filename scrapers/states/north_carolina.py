"""
NC eVP (Electronic Vendor Portal) scraper — evp.nc.gov

Scrapes North Carolina state solicitations (RFPs, IFBs, RFQs) from the
official eVP portal.  Uses Selenium for the JS-rendered listing table,
then visits each detail page to extract description, attachments, and
solicitation type.

Source:  https://evp.nc.gov
Listing: https://evp.nc.gov/solicitations/?status=0
Detail:  https://evp.nc.gov/solicitations/details/?id={guid}
"""

import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = config.NC_EVP_BASE_URL
LISTING_URL = f'{BASE_URL}/solicitations/?status=0'

MAX_PAGES = config.NC_EVP_MAX_PAGES
DELAY_BETWEEN_PAGES = (2, 4)
DELAY_BETWEEN_DETAILS = (1.5, 3.0)


class NCeVPScraper(BaseScraper):
    """Scrapes NC eVP solicitations with detail page enrichment."""

    def __init__(self):
        super().__init__('NC eVP Solicitations')

    def scrape(self):
        logger.info("Starting NC eVP scraper...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping NC eVP")
            return self.opportunities

        try:
            self._scrape_all_pages(driver)
        except Exception as exc:
            logger.error(f"NC eVP: fatal error: {exc}")

        self.log_summary()
        return self.opportunities

    def _scrape_all_pages(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        time.sleep(random.uniform(*SELENIUM_DELAY_RANGE))
        driver.get(LISTING_URL)

        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            logger.debug("NC eVP: readyState timeout on listing, continuing anyway")

        time.sleep(random.uniform(4, 7))

        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.entity-grid table tbody tr, table tbody tr'))
            )
        except Exception:
            logger.warning("NC eVP: timed out waiting for listing table")

        time.sleep(random.uniform(2, 4))

        page = 1
        seen_urls = set()

        while page <= MAX_PAGES:
            logger.info(f"NC eVP: parsing page {page}...")
            soup = self.parse_html(driver.page_source)
            rows = soup.select('.entity-grid table tbody tr, table.table tbody tr')

            if not rows:
                rows = soup.select('table tbody tr')

            if not rows:
                logger.info(f"NC eVP: no rows on page {page}, stopping.")
                break

            new_count = 0
            for row in rows:
                opp = self._parse_listing_row(row, seen_urls)
                if opp:
                    self._enrich_from_detail(driver, opp)
                    is_new = self.add_opportunity(opp)
                    if is_new:
                        new_count += 1
                    if self.reached_limit():
                        break

            logger.info(f"NC eVP: page {page} — {new_count} new solicitations")

            if self.reached_limit() or not self._go_to_next_page(driver, page):
                break
            page += 1
            time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

    def _parse_listing_row(self, row, seen_urls):
        """Extract opportunity data from a listing table row."""
        try:
            cells = row.find_all('td')
            if not cells:
                return None

            title = None
            detail_url = None
            opp_number = None
            description = None
            posted_date = None
            deadline = None
            organization = None

            for cell in cells:
                attr = (cell.get('data-attribute') or '').lower()
                value = clean_text(cell.get('data-value') or cell.get_text())

                if attr == 'evp_name' or attr == 'evp_solicitationname':
                    title = value
                elif attr == 'evp_solicitationnbr':
                    opp_number = value
                elif attr == 'evp_description':
                    description = value
                elif attr == 'evp_posteddate':
                    posted_date = parse_date(value)
                elif attr in ('evp_opendate', 'evp_closedate'):
                    if not deadline:
                        deadline = parse_date(value)
                elif attr in ('owningbusinessunit', 'evp_department'):
                    organization = value

                link = cell.find('a', class_='details-link') or cell.find('a', href=True)
                if link and not detail_url:
                    href = (link.get('href') or '').strip()
                    if href and 'details' in href.lower():
                        detail_url = urllib.parse.urljoin(BASE_URL, href)
                    if not title and link.get_text(strip=True):
                        title = clean_text(link.get_text())

            if not title:
                first_link = row.find('a', href=True)
                if first_link:
                    title = clean_text(first_link.get_text())
                    if not detail_url:
                        href = (first_link.get('href') or '').strip()
                        if href:
                            detail_url = urllib.parse.urljoin(BASE_URL, href)

            if not title or len(title) < 5:
                return None

            source_url = detail_url or f'{BASE_URL}/solicitations/'
            if source_url in seen_urls:
                return None
            seen_urls.add(source_url)

            category = categorize_opportunity(title, description or '')

            return {
                'title': title,
                'organization': organization or 'State of North Carolina',
                'description': description[:1000] if description else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'North Carolina',
                'source': 'NC eVP Solicitations',
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': posted_date,
                'document_urls': [],
                'opportunity_type': 'rfp',
            }

        except Exception as exc:
            logger.debug(f"NC eVP: error parsing row: {exc}")
            return None

    def _enrich_from_detail(self, driver, opp):
        """Visit detail page to extract richer data and attachment URLs."""
        detail_url = opp.get('source_url', '')
        if not detail_url or 'details' not in detail_url:
            return

        try:
            time.sleep(random.uniform(*DELAY_BETWEEN_DETAILS))
            driver.get(detail_url)

            try:
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            time.sleep(random.uniform(4, 7))

            soup = self.parse_html(driver.page_source)

            desc_field = soup.select_one('#evp_description, textarea[id*="description"]')
            if desc_field:
                desc = clean_text(desc_field.get_text())
                if desc and len(desc) > 20:
                    opp['description'] = desc[:1000]

            spec_field = soup.select_one('#evp_specinstr, textarea[id*="specinstr"]')
            if spec_field:
                spec = clean_text(spec_field.get_text())
                if spec and len(spec) > 10:
                    existing = opp.get('description') or ''
                    opp['description'] = f"{existing}\n\nSpecial Instructions: {spec}".strip()[:1000]

            sol_type = soup.select_one('#evp_solicitationtype option[selected], select[id*="solicitationtype"] option[selected]')
            if sol_type:
                stype = clean_text(sol_type.get_text())
                if stype:
                    opp['category'] = stype

            comm_code = soup.select_one('#evp_commcode_name, input[id*="commcode"]')
            if comm_code:
                code_val = comm_code.get('value') or clean_text(comm_code.get_text())
                if code_val and opp.get('category'):
                    opp['category'] = f"{opp['category']} - {code_val}"

            org_field = soup.select_one('#owningbusinessunit_name, input[id*="owningbusiness"]')
            if org_field:
                org_val = org_field.get('value') or clean_text(org_field.get_text())
                if org_val:
                    opp['organization'] = org_val

            if not opp.get('deadline'):
                for sel in ['#evp_opendate', '#evp_closedate', 'input[id*="closedate"]']:
                    field = soup.select_one(sel)
                    if field:
                        val = field.get('value') or clean_text(field.get_text())
                        if val:
                            d = parse_date(val)
                            if d:
                                opp['deadline'] = d
                                break

            if not opp.get('posted_date'):
                pd_input = soup.select_one('#evp_posteddate, input[id*="posteddate"]')
                if pd_input:
                    raw = pd_input.get('value', '').strip()
                    if raw:
                        opp['posted_date'] = parse_date(raw)

            if not opp.get('funding_amount'):
                for sel in ['#evp_estimatedvalue', 'input[id*="budget"]',
                            'input[id*="estimatedvalue"]', '#evp_budgetamount',
                            'input[id*="amount"]']:
                    field = soup.select_one(sel)
                    if field:
                        val = (field.get('value') or clean_text(field.get_text())).strip()
                        if val and val not in ('0', '0.00', ''):
                            opp['funding_amount'] = val
                            break

            if not opp.get('eligibility'):
                for sel in ['#evp_qualifications', 'textarea[id*="qualif"]',
                            '#evp_eligibility', 'textarea[id*="eligib"]',
                            '#evp_requirements', 'textarea[id*="require"]']:
                    field = soup.select_one(sel)
                    if field:
                        val = clean_text(field.get_text())
                        if val and len(val) > 10:
                            opp['eligibility'] = val[:1000]
                            break

            doc_urls = []
            for a in soup.select('.note .attachment a[href], a.attachment-link, a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"]'):
                href = (a.get('href') or '').strip()
                if href:
                    full_url = urllib.parse.urljoin(BASE_URL, href)
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]

            if opp.get('document_urls'):
                self.enrich_from_documents(opp)

        except Exception as exc:
            logger.debug(f"NC eVP: detail enrichment failed for {detail_url}: {exc}")

    def _go_to_next_page(self, driver, current_page):
        """Click the next page link. Returns True if navigation succeeded."""
        from selenium.webdriver.common.by import By
        try:
            next_page = current_page + 1
            next_links = driver.find_elements(
                By.CSS_SELECTOR,
                f'.pagination a[data-page="{next_page}"], '
                f'.jquery-bootstrap-pagination a[data-page="{next_page}"], '
                f'a[aria-label="Page {next_page}"]'
            )

            if not next_links:
                next_links = driver.find_elements(
                    By.CSS_SELECTOR,
                    'a.next, li.next a, .pagination .next a'
                )

            for link in next_links:
                if link.is_displayed():
                    link.click()
                    try:
                        from selenium.webdriver.support.ui import WebDriverWait
                        WebDriverWait(driver, 30).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        pass
                    time.sleep(random.uniform(3, 6))
                    return True

            return False
        except Exception as exc:
            logger.debug(f"NC eVP: pagination failed at page {current_page}: {exc}")
            return False

    def parse_opportunity(self, element):
        return None


def get_nc_evp_scrapers():
    """Return a list containing the NC eVP scraper instance."""
    return [NCeVPScraper()]
