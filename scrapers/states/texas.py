"""
Texas ESBD (Electronic State Business Daily) scraper — txsmartbuy.gov

Scrapes three sections of the Texas Comptroller's procurement site:
  1. Grant Opportunities  — /esbd-grants         (~5 pages)
  2. Solicitations (RFPs) — /esbd                 (~2300 pages, limited)
  3. Pre-Solicitations    — /esbd-presolicitations (~15 pages)

Uses Selenium because the site is a SuiteCommerce single-page application.
Each section lists cards on listing pages, then we visit detail pages for
rich data (description, eligibility, funding, attachments/PDFs).

Source: https://www.txsmartbuy.gov
"""

import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = config.TX_ESBD_BASE_URL

ESBD_SECTIONS = [
    {
        'name': 'Texas ESBD Grants',
        'url': f'{BASE_URL}/esbd-grants?page=1&expired=no',
        'detail_prefix': '/esbd-grants/',
        'opportunity_type': 'grant',
        'max_pages': config.TX_ESBD_GRANTS_MAX_PAGES,
    },
    {
        'name': 'Texas ESBD Solicitations',
        'url': f'{BASE_URL}/esbd',
        'detail_prefix': '/esbd/',
        'opportunity_type': 'rfp',
        'max_pages': config.TX_ESBD_SOLICITATIONS_MAX_PAGES,
    },
    {
        'name': 'Texas ESBD Pre-Solicitations',
        'url': f'{BASE_URL}/esbd-presolicitations',
        'detail_prefix': '/esbd-presolicitations/',
        'opportunity_type': 'rfp',
        'max_pages': config.TX_ESBD_PRESOLICITATIONS_MAX_PAGES,
    },
]

DELAY_BETWEEN_PAGES = (2, 4)
DELAY_BETWEEN_DETAILS = (1.5, 3.0)
DELAY_BETWEEN_SECTIONS = (3, 6)


class TexasESBDScraper(BaseScraper):
    """Scrapes all three ESBD sections with detail page enrichment."""

    def __init__(self):
        super().__init__('Texas ESBD')

    def scrape(self):
        logger.info("Starting Texas ESBD scraper (grants + solicitations + pre-solicitations)...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping Texas ESBD")
            return self.opportunities

        for section in ESBD_SECTIONS:
            if self.reached_limit():
                break
            try:
                count_before = len(self.opportunities)
                self._scrape_section(driver, section)
                added = len(self.opportunities) - count_before
                logger.info(f"Texas ESBD: {section['name']} — {added} opportunities")
            except Exception as exc:
                logger.error(f"Texas ESBD: error in {section['name']}: {exc}")

            time.sleep(random.uniform(*DELAY_BETWEEN_SECTIONS))

        self.log_summary()
        return self.opportunities

    def _scrape_section(self, driver, section):
        """Scrape one ESBD section (grants, solicitations, or pre-solicitations)."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        time.sleep(random.uniform(*SELENIUM_DELAY_RANGE))
        driver.get(section['url'])

        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            logger.debug(f"Texas ESBD: readyState timeout for {section['name']}, continuing")

        time.sleep(random.uniform(4, 8))

        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.esbd-result-row'))
            )
        except Exception:
            logger.warning(f"Texas ESBD: timed out waiting for {section['name']} listing")

        time.sleep(random.uniform(2, 4))

        page = 1
        seen_urls = set()

        while page <= section['max_pages']:
            logger.info(f"Texas ESBD: {section['name']} page {page}...")
            soup = self.parse_html(driver.page_source)
            cards = soup.select('.esbd-result-row')

            if not cards:
                logger.info(f"Texas ESBD: no cards on page {page}, stopping.")
                break

            new_count = 0
            for card in cards:
                opp = self._parse_listing_card(card, section, seen_urls)
                if opp:
                    self._enrich_from_detail(driver, opp, section)
                    if opp.get('document_urls'):
                        self.enrich_from_documents(opp)
                    is_new = self.add_opportunity(opp)
                    if is_new:
                        new_count += 1
                    if self.reached_limit():
                        break

            logger.info(f"Texas ESBD: {section['name']} page {page} — {new_count} new")

            if self.reached_limit() or not self._go_to_next_page(driver, page):
                break
            page += 1
            time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

    def _parse_listing_card(self, card, section, seen_urls):
        """Extract basic opportunity data from an ESBD listing card."""
        try:
            title_link = card.select_one('.esbd-result-title a')
            if not title_link:
                return None

            title = clean_text(title_link.get_text())
            href = (title_link.get('href') or '').strip()

            if not title or len(title) < 5:
                return None
            if not href:
                return None

            source_url = urllib.parse.urljoin(BASE_URL, href)
            if source_url in seen_urls:
                return None
            seen_urls.add(source_url)

            fields = {}
            for p in card.select('.esbd-result-column p, .esbd-result-body-columns p'):
                text = p.get_text(separator=' ', strip=True)
                for label in (
                    'Solicitation ID:', 'Pre-Solicitation ID:', 'Grant Number:',
                    'Status:', 'Agency:', 'Agency Name:',
                    'Agency/Texas SmartBuy Member Number:',
                    'Post Date:', 'Posting Date:', 'Notice Posting Date:',
                    'Due Date:', 'Application Deadline:', 'Expiration Date:',
                    'Due Time:', 'Application Deadline Time:',
                ):
                    if label in text:
                        value = text.split(label, 1)[1].strip()
                        fields[label.rstrip(':')] = value
                        break

            opp_number = (
                fields.get('Solicitation ID')
                or fields.get('Pre-Solicitation ID')
                or fields.get('Grant Number')
            )
            organization = fields.get('Agency') or fields.get('Agency Name') or 'State of Texas'
            agency_num = fields.get('Agency/Texas SmartBuy Member Number')
            if agency_num and organization == 'State of Texas':
                organization = f'Texas Agency {agency_num}'

            posted_raw = (
                fields.get('Post Date')
                or fields.get('Posting Date')
                or fields.get('Notice Posting Date')
            )
            deadline_raw = (
                fields.get('Application Deadline')
                or fields.get('Due Date')
                or fields.get('Expiration Date')
            )

            posted_date = parse_date(posted_raw) if posted_raw else None
            deadline = parse_date(deadline_raw) if deadline_raw else None

            status = fields.get('Status', '')
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': organization,
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Texas',
                'source': section['name'],
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': posted_date,
                'document_urls': [],
                'opportunity_type': section['opportunity_type'],
            }

        except Exception as exc:
            logger.debug(f"Texas ESBD: error parsing card: {exc}")
            return None

    def _enrich_from_detail(self, driver, opp, section):
        """Visit the detail page and extract rich data."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        detail_url = opp.get('source_url', '')
        if not detail_url:
            return

        try:
            time.sleep(random.uniform(*DELAY_BETWEEN_DETAILS))
            driver.get(detail_url)

            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.esbd-result-cell'))
                )
            except Exception:
                pass
            time.sleep(random.uniform(4, 7))

            soup = self.parse_html(driver.page_source)

            self._extract_detail_fields(soup, opp, section)
            self._extract_attachments(soup, opp)

        except Exception as exc:
            logger.debug(f"Texas ESBD: detail enrichment failed for {detail_url}: {exc}")

    def _extract_detail_fields(self, soup, opp, section):
        """Parse all .esbd-result-cell fields on the detail page."""
        cells = soup.select('.esbd-result-cell')
        for cell in cells:
            strong = cell.find('strong')
            if not strong:
                continue

            label = clean_text(strong.get_text()).rstrip(':').strip()
            value_parts = []
            for sibling in strong.next_siblings:
                if hasattr(sibling, 'get_text'):
                    value_parts.append(sibling.get_text(separator=' ', strip=True))
                elif isinstance(sibling, str):
                    value_parts.append(sibling.strip())
            value = clean_text(' '.join(value_parts))

            if not value:
                ul = cell.find('ul')
                if ul:
                    items = [clean_text(li.get_text()) for li in ul.find_all('li')]
                    value = '; '.join(i for i in items if i)

            if not value:
                continue

            label_lower = label.lower()

            if 'agency name' in label_lower:
                opp['organization'] = value
            elif label_lower in ('solicitation id', 'pre-solicitation id', 'grant number'):
                opp['opportunity_number'] = value
            elif 'eligibility category' in label_lower:
                opp['eligibility'] = value
            elif 'matching requirement' in label_lower:
                existing = opp.get('eligibility') or ''
                if existing:
                    opp['eligibility'] = f"{existing}; Matching: {value}"
                else:
                    opp['eligibility'] = f"Matching: {value}"
            elif 'estimated grant amount' in label_lower:
                opp['funding_amount'] = value
            elif 'grant opportunity type' in label_lower or 'grant activity category' in label_lower:
                if opp.get('category'):
                    opp['category'] = f"{opp['category']} - {value}"
                else:
                    opp['category'] = value
            elif label_lower in ('application deadline', 'response due date', 'due date', 'expiration date'):
                if not opp.get('deadline'):
                    opp['deadline'] = parse_date(value)
            elif label_lower in ('post date', 'posting date', 'solicitation posting date', 'notice posting date'):
                if not opp.get('posted_date'):
                    opp['posted_date'] = parse_date(value)
            elif 'class/item code' in label_lower:
                if opp.get('category'):
                    opp['category'] = f"{opp['category']} | {value[:100]}"
                else:
                    opp['category'] = value[:100]
            elif 'keyword' in label_lower:
                existing_desc = opp.get('description') or ''
                opp['description'] = f"{existing_desc}\nKeywords: {value}".strip()[:1000]
            elif 'grant opportunity complete posting' in label_lower:
                pass
            elif 'contact name' in label_lower:
                existing_desc = opp.get('description') or ''
                contact_email = ''
                for c2 in soup.select('.esbd-result-cell'):
                    s2 = c2.find('strong')
                    if s2 and 'contact email' in clean_text(s2.get_text()).lower():
                        email_parts = []
                        for sib in s2.next_siblings:
                            if hasattr(sib, 'get_text'):
                                email_parts.append(sib.get_text(strip=True))
                            elif isinstance(sib, str):
                                email_parts.append(sib.strip())
                        contact_email = clean_text(' '.join(email_parts))
                        break
                contact_info = f"Contact: {value}"
                if contact_email:
                    contact_info += f" ({contact_email})"
                opp['description'] = f"{existing_desc}\n{contact_info}".strip()[:1000]

        all_rich = soup.select('.rich-text-editor-content')
        for rich_div in all_rich:
            desc_text = clean_text(rich_div.get_text(separator=' '))
            if desc_text and len(desc_text) > 20:
                existing = opp.get('description') or ''
                if desc_text not in existing:
                    opp['description'] = f"{desc_text}\n{existing}".strip()[:1000]
                break

        if not all_rich:
            for cell in soup.select('.esbd-result-cell'):
                strong = cell.find('strong')
                if strong and 'description' in (strong.get_text() or '').lower():
                    cell_text = clean_text(cell.get_text(separator=' '))
                    label_text = clean_text(strong.get_text())
                    desc_text = cell_text.replace(label_text, '', 1).strip()
                    if desc_text and len(desc_text) > 20:
                        opp['description'] = desc_text[:1000]
                    break

        if opp.get('description'):
            opp['category'] = opp.get('category') or categorize_opportunity(
                opp['title'], opp['description']
            )

    def _extract_attachments(self, soup, opp):
        """Extract PDF/document attachment URLs from the detail page."""
        doc_urls = []

        for a in soup.select('a[data-action="downloadURL"]'):
            data_href = a.get('data-href', '').strip()
            if data_href:
                full_url = urllib.parse.urljoin(BASE_URL, data_href)
                if full_url not in doc_urls:
                    doc_urls.append(full_url)

        for a in soup.select('a[href]'):
            href = (a.get('href') or '').strip()
            if any(href.lower().endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                full_url = urllib.parse.urljoin(BASE_URL, href)
                if full_url not in doc_urls:
                    doc_urls.append(full_url)

        if doc_urls:
            opp['document_urls'] = doc_urls[:15]

    def _go_to_next_page(self, driver, current_page):
        """Click the next page link in ESBD pagination."""
        from selenium.webdriver.common.by import By
        try:
            next_page = current_page + 1
            next_links = driver.find_elements(
                By.CSS_SELECTOR,
                f'.global-views-pagination-links-number a[aria-label="Page {next_page}"]'
            )

            if not next_links:
                next_links = driver.find_elements(
                    By.CSS_SELECTOR,
                    '.global-views-pagination-next a'
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
            logger.debug(f"Texas ESBD: pagination failed at page {current_page}: {exc}")
            return False

    def parse_opportunity(self, element):
        return None


def get_texas_esbd_scrapers():
    """Return a list containing the Texas ESBD scraper instance."""
    return [TexasESBDScraper()]
