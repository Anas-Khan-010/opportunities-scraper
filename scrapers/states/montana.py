"""
Montana eMACS (Jaggaer) scraper — bids.sciquest.com

Scrapes RFP/RFQ bid opportunities from Montana's Acquisition & Contracting
System hosted on the Jaggaer (SciQuest) platform. The platform is a
JavaScript SPA requiring Selenium.

Each listing row contains: Status, Title (link), Open/Close dates,
Type (RFP/RFQ), Number, Contact name + email, and a "View as PDF" link
on S3.  PDF enrichment is used to backfill description, eligibility,
and funding_amount.

Source: https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=StateOfMontana
"""

import time
import random
import re
import urllib.parse

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


PORTAL_URL = (
    "https://bids.sciquest.com/apps/Router/PublicEvent"
    "?CustomerOrg=StateOfMontana"
    "&tab=PHX_NAV_SourcingAllOpps"
)
DELAY_BETWEEN_PAGES = (3, 6)
DELAY_LOAD = (6, 12)


class MontanaEMACSscraper(BaseScraper):
    """Scrapes Montana eMACS bid opportunities via Selenium + PDF enrichment."""

    def __init__(self):
        super().__init__("Montana eMACS")
        self.max_pages = getattr(config, "MT_EMACS_MAX_PAGES", 15)

    def scrape(self):
        logger.info("Starting Montana eMACS scraper (Selenium + PDF enrichment)...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping Montana")
            return self.opportunities

        self._scrape_listings(driver)
        self.log_summary()
        return self.opportunities

    def _scrape_listings(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            logger.info("Montana: loading Jaggaer portal...")
            driver.get(PORTAL_URL)
            time.sleep(random.uniform(*DELAY_LOAD))

            WebDriverWait(driver, 45).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(random.uniform(5, 8))

        except Exception as exc:
            logger.error(f"Montana: failed to load portal: {exc}")
            return

        page = 1
        while page <= self.max_pages and not self.reached_limit():
            logger.info(f"Montana eMACS: parsing page {page}...")

            try:
                soup = self.parse_html(driver.page_source)
                rows = self._extract_rows(soup)

                if not rows:
                    logger.info(f"Montana: no rows found on page {page}, stopping.")
                    break

                page_new = 0
                for row_data in rows:
                    opp = self._build_opportunity(row_data)
                    if opp:
                        self._enrich_from_detail(driver, opp)
                        if opp.get('document_urls'):
                            self.enrich_from_documents(opp)
                        is_new = self.add_opportunity(opp)
                        if is_new:
                            page_new += 1
                        if self.reached_limit():
                            break

                logger.info(f"Montana: page {page} — {len(rows)} rows, {page_new} new")

                if self.reached_limit():
                    break

                if not self._go_to_next_page(driver, page):
                    break
                page += 1
                time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

            except Exception as exc:
                logger.error(f"Montana: error on page {page}: {exc}")
                break

    def _extract_rows(self, soup):
        """Parse listing rows from the Jaggaer table HTML."""
        rows = []
        table = soup.find('table')
        if not table:
            table_rows = soup.select('tr')
        else:
            table_rows = table.find_all('tr')

        for tr in table_rows:
            cells = tr.find_all('td')
            if len(cells) < 2:
                continue

            row_text = tr.get_text(separator=' ', strip=True)
            if not row_text or len(row_text) < 10:
                continue

            title_link = tr.find('a', href=True)
            title = clean_text(title_link.get_text()) if title_link else None
            detail_url = title_link['href'] if title_link else None

            if not title or len(title) < 3:
                continue

            status = None
            first_cell_text = clean_text(cells[0].get_text())
            if first_cell_text and first_cell_text.lower() in (
                'open', 'released', 'closed', 'canceled', 'awarded',
            ):
                status = first_cell_text

            data = {
                'title': title,
                'detail_url': detail_url,
                'status': status,
                'open_date': None,
                'close_date': None,
                'opp_type': None,
                'number': None,
                'contact_name': None,
                'contact_email': None,
                'pdf_url': None,
            }

            full_text = row_text

            open_match = re.search(
                r'Open\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s*\w+)',
                full_text
            )
            if open_match:
                data['open_date'] = open_match.group(1).strip()

            close_match = re.search(
                r'Close\s*(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s*\w+)',
                full_text
            )
            if close_match:
                data['close_date'] = close_match.group(1).strip()

            type_match = re.search(r'Type\s*(RFP[/\w]*|RFQ[/\w]*|IFB|ITB|RFI)', full_text, re.I)
            if type_match:
                data['opp_type'] = type_match.group(1).strip()

            num_match = re.search(r'Number\s*([A-Za-z0-9\-/]+)', full_text)
            if num_match:
                data['number'] = num_match.group(1).strip()

            contact_match = re.search(r'Contact\s+([A-Z][a-z]+ [A-Z][a-z]+)', full_text)
            if contact_match:
                data['contact_name'] = contact_match.group(1).strip()

            email_link = tr.find('a', href=re.compile(r'^mailto:', re.I))
            if email_link:
                email = email_link['href'].replace('mailto:', '').split('?')[0]
                data['contact_email'] = email

            pdf_link = tr.find('a', href=re.compile(r'\.pdf', re.I))
            if not pdf_link:
                pdf_link = tr.find('a', string=re.compile(r'PDF', re.I))
            if pdf_link and pdf_link.get('href'):
                data['pdf_url'] = pdf_link['href']

            rows.append(data)

        return rows

    def _enrich_from_detail(self, driver, opp):
        """Navigate to the Jaggaer detail page and extract richer fields."""
        detail_url = opp.get('source_url', '')
        if not detail_url or detail_url == PORTAL_URL:
            return

        try:
            time.sleep(random.uniform(2, 4))
            driver.get(detail_url)

            from selenium.webdriver.support.ui import WebDriverWait
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            time.sleep(random.uniform(4, 7))
            soup = self.parse_html(driver.page_source)
            full_text = soup.get_text(separator='\n', strip=True)

            if not opp.get('description') or len(opp.get('description', '')) < 50:
                desc_el = soup.find(string=re.compile(r'Description', re.I))
                if desc_el:
                    parent = desc_el.find_parent()
                    if parent:
                        next_sib = parent.find_next_sibling()
                        if next_sib:
                            desc = clean_text(next_sib.get_text(separator='\n'))
                            if desc and len(desc) > 20:
                                opp['description'] = desc[:2000]

                if not opp.get('description') or len(opp.get('description', '')) < 50:
                    desc_match = re.search(
                        r'(?:Description|Summary|Scope\s+of\s+Work)\s*[:\n]?\s*(.+?)(?:\n\s*\n|\n[A-Z][a-z])',
                        full_text, re.IGNORECASE | re.DOTALL,
                    )
                    if desc_match:
                        desc = desc_match.group(1).strip()
                        if len(desc) > 30:
                            opp['description'] = desc[:2000]

            if not opp.get('eligibility'):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if elig:
                    opp['eligibility'] = elig

            if not opp.get('funding_amount'):
                from utils.helpers import extract_funding_amount
                amount = extract_funding_amount(full_text)
                if amount:
                    opp['funding_amount'] = amount

            doc_urls = list(opp.get('document_urls') or [])
            for a in soup.select('a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"], a[href$=".xlsx"]'):
                href = a.get('href', '').strip()
                if href:
                    full_url = href if href.startswith('http') else urllib.parse.urljoin('https://bids.sciquest.com', href)
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            for a in soup.select('a[href*="attachment"], a[href*="download"]'):
                href = a.get('href', '').strip()
                if href:
                    full_url = href if href.startswith('http') else urllib.parse.urljoin('https://bids.sciquest.com', href)
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]

            driver.back()
            time.sleep(random.uniform(3, 5))

        except Exception as exc:
            logger.debug(f"Montana: detail enrichment failed for {detail_url}: {exc}")
            try:
                driver.get(PORTAL_URL)
                time.sleep(random.uniform(4, 7))
            except Exception:
                pass

    def _build_opportunity(self, data):
        """Convert parsed row data into an opportunity dict."""
        title = data['title']
        if not title:
            return None

        source_url = data.get('detail_url') or PORTAL_URL
        if source_url and not source_url.startswith('http'):
            source_url = urllib.parse.urljoin('https://bids.sciquest.com', source_url)

        deadline = parse_date(data['close_date']) if data.get('close_date') else None
        posted_date = parse_date(data['open_date']) if data.get('open_date') else None

        opp_type_raw = (data.get('opp_type') or '').upper()
        if 'RFP' in opp_type_raw or 'RFQ' in opp_type_raw:
            opportunity_type = 'rfp'
        elif 'IFB' in opp_type_raw or 'ITB' in opp_type_raw:
            opportunity_type = 'rfp'
        else:
            opportunity_type = 'rfp'

        desc_parts = []
        if data.get('opp_type'):
            desc_parts.append(f"Type: {data['opp_type']}")
        if data.get('status'):
            desc_parts.append(f"Status: {data['status']}")
        if data.get('contact_name'):
            contact = f"Contact: {data['contact_name']}"
            if data.get('contact_email'):
                contact += f" ({data['contact_email']})"
            desc_parts.append(contact)
        description = "; ".join(desc_parts) if desc_parts else None

        doc_urls = []
        if data.get('pdf_url'):
            pdf = data['pdf_url']
            if not pdf.startswith('http'):
                pdf = urllib.parse.urljoin('https://bids.sciquest.com', pdf)
            doc_urls.append(pdf)

        category = categorize_opportunity(title, description or '')

        return {
            'title': title,
            'organization': 'State of Montana',
            'description': description,
            'eligibility': None,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': 'Montana',
            'source': self.source_name,
            'source_url': source_url,
            'opportunity_number': data.get('number'),
            'posted_date': posted_date,
            'document_urls': doc_urls,
            'opportunity_type': opportunity_type,
        }

    def _go_to_next_page(self, driver, current_page):
        """Navigate to the next page in the Jaggaer pagination."""
        from selenium.webdriver.common.by import By
        try:
            next_btn = driver.find_elements(By.CSS_SELECTOR, 'a[aria-label="Next Page"]')
            if not next_btn:
                next_btn = driver.find_elements(
                    By.XPATH, "//a[contains(text(), '›') or contains(text(), 'Next')]"
                )

            for btn in next_btn:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    time.sleep(random.uniform(*DELAY_LOAD))
                    return True

            try:
                page_input = driver.find_element(By.CSS_SELECTOR, 'input[type="text"][aria-label*="Page"]')
                if page_input:
                    page_input.clear()
                    page_input.send_keys(str(current_page + 1))
                    page_input.send_keys('\n')
                    time.sleep(random.uniform(*DELAY_LOAD))
                    return True
            except Exception:
                pass

            return False
        except Exception as exc:
            logger.debug(f"Montana: pagination failed at page {current_page}: {exc}")
            return False

    def parse_opportunity(self, element):
        return None


def get_montana_scrapers():
    return [MontanaEMACSscraper()]
