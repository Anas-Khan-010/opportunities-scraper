"""
Michigan MI Funding Hub scraper — mifundinghub.org

Scrapes state and federal grant opportunities from Michigan's
MI Funding Hub portal. The page is a WordPress SPA that loads grant
data via JavaScript, so Selenium is required.

Source: https://mifundinghub.org/find-funding/
"""

import time
import random
import re

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity, extract_funding_amount


PORTAL_URL = "https://mifundinghub.org/find-funding/"
DELAY_BETWEEN_PAGES = (3, 6)


class MichiganFundingHubScraper(BaseScraper):
    """Scrapes MI Funding Hub grant listings via Selenium."""

    def __init__(self):
        super().__init__("Michigan Funding Hub")
        self.max_pages = getattr(config, "MI_FUNDING_HUB_MAX_PAGES", 20)

    def scrape(self):
        logger.info("Starting Michigan Funding Hub scraper (Selenium)...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping Michigan")
            return self.opportunities

        self._scrape_pages(driver)
        self.log_summary()
        return self.opportunities

    def _scrape_pages(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        page = 1
        while page <= self.max_pages:
            url = f"{PORTAL_URL}?_page={page}" if page > 1 else PORTAL_URL
            logger.info(f"Michigan Funding Hub: loading page {page}...")

            try:
                driver.get(url)
                time.sleep(random.uniform(*SELENIUM_DELAY_RANGE))

                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                time.sleep(random.uniform(5, 10))

                soup = self.parse_html(driver.page_source)

                grants = self._find_grant_elements(soup)
                if not grants:
                    logger.info(f"Michigan: no grant entries on page {page}, stopping.")
                    break

                page_new = 0
                for grant_el in grants:
                    opp = self.parse_opportunity(grant_el)
                    if opp:
                        self._enrich_from_detail(driver, opp)
                        if opp.get('document_urls'):
                            self.enrich_from_documents(opp)
                        is_new = self.add_opportunity(opp)
                        if is_new:
                            page_new += 1
                        if self.reached_limit():
                            break

                logger.info(f"Michigan: page {page} — {len(grants)} entries, {page_new} new")

                if self.reached_limit():
                    break

                page += 1
                time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

            except Exception as exc:
                logger.error(f"Michigan: error on page {page}: {exc}")
                break

    def _find_grant_elements(self, soup):
        """Try multiple selectors to locate grant cards/rows in the DOM."""
        selectors = [
            'article.grant', 'article.post', 'article',
            '.grant-card', '.grant-item', '.funding-item',
            '.jet-listing-grid__item', '.elementor-post',
            'tr.grant-row', '.wp-block-post',
            '.jet-smart-listing__post',
        ]
        for sel in selectors:
            elements = soup.select(sel)
            if elements and len(elements) >= 2:
                return elements

        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) >= 3:
                return rows[1:]

        divs = soup.find_all('div', class_=re.compile(r'grant|funding|opportunity', re.I))
        if len(divs) >= 2:
            return divs

        return []

    _GENERIC_TITLES = {'learn more', 'apply now', 'view details', 'read more',
                        'click here', 'more info', 'details', 'view'}

    def _enrich_from_detail(self, driver, opp):
        """Navigate to the grant detail page and extract richer fields."""
        detail_url = opp.get('source_url', '')
        if not detail_url or detail_url == PORTAL_URL:
            return

        try:
            time.sleep(random.uniform(2, 4))
            driver.get(detail_url)
            time.sleep(random.uniform(3, 6))

            from selenium.webdriver.support.ui import WebDriverWait
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

            time.sleep(random.uniform(2, 4))
            soup = self.parse_html(driver.page_source)
            full_text = soup.get_text(separator='\n', strip=True)

            if (opp.get('title') or '').lower().strip() in self._GENERIC_TITLES:
                real_title = None
                og = soup.find('meta', attrs={'property': 'og:title'})
                if og and og.get('content', '').strip():
                    real_title = clean_text(og['content'])
                if not real_title:
                    h1 = soup.find('h1')
                    if h1:
                        real_title = clean_text(h1.get_text())
                if not real_title:
                    title_tag = soup.find('title')
                    if title_tag:
                        raw = clean_text(title_tag.get_text())
                        if raw:
                            real_title = raw.split('|')[0].split(' - ')[0].strip()
                if real_title and len(real_title) > 5:
                    opp['title'] = real_title[:300]

            if not opp.get('description') or len(opp.get('description', '')) < 50:
                content = soup.select_one('.entry-content, .post-content, article .content, .elementor-widget-theme-post-content')
                if content:
                    desc = clean_text(content.get_text(separator='\n'))
                    if desc and len(desc) > 30:
                        opp['description'] = desc[:2000]

            if not opp.get('deadline'):
                deadline_match = re.search(
                    r'(?:deadline|due\s*date|close[sd]?\s*date|submission\s*date)\s*[:\-]?\s*'
                    r'(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})',
                    full_text, re.IGNORECASE,
                )
                if deadline_match:
                    opp['deadline'] = parse_date(deadline_match.group(1))

            if not opp.get('posted_date'):
                posted_match = re.search(
                    r'(?:posted|published|open\s*date|start\s*date)\s*[:\-]?\s*'
                    r'(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})',
                    full_text, re.IGNORECASE,
                )
                if posted_match:
                    opp['posted_date'] = parse_date(posted_match.group(1))

            if not opp.get('funding_amount'):
                amount = extract_funding_amount(full_text)
                if amount:
                    opp['funding_amount'] = amount

            if not opp.get('eligibility'):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if elig:
                    opp['eligibility'] = elig

            if not opp.get('opportunity_number'):
                from parsers.parser_utils import OpportunityEnricher
                opp_num = OpportunityEnricher._extract_opp_number(full_text)
                if opp_num:
                    opp['opportunity_number'] = opp_num

            doc_urls = list(opp.get('document_urls') or [])
            for a in soup.select('a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"]'):
                href = a.get('href', '').strip()
                if href:
                    full_url = href if href.startswith('http') else f"https://mifundinghub.org{href}"
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            for a in soup.select('a[href*="grants.gov"], a[href*="sam.gov"]'):
                href = a.get('href', '').strip()
                if href and href.startswith('http') and href not in doc_urls:
                    doc_urls.append(href)
            if doc_urls:
                opp['document_urls'] = doc_urls[:10]

            driver.back()
            time.sleep(random.uniform(2, 4))

        except Exception as exc:
            logger.debug(f"Michigan: detail enrichment failed for {detail_url}: {exc}")
            try:
                driver.get(PORTAL_URL)
                time.sleep(random.uniform(2, 4))
            except Exception:
                pass

    def parse_opportunity(self, element):
        try:
            title = None
            source_url = PORTAL_URL
            description = None
            organization = "State of Michigan"
            deadline = None
            posted_date = None
            funding_amount = None
            category = None
            doc_urls = []

            link = element.find('a')
            if element.name == 'tr':
                cells = element.find_all('td')
                if cells:
                    link = cells[0].find('a') if cells[0].find('a') else element.find('a')

            if link:
                title = clean_text(link.get_text())
                href = (link.get('href') or '').strip()
                if href and href.startswith('http'):
                    source_url = href
                elif href:
                    source_url = f"https://mifundinghub.org{href}"

            if not title:
                h_tag = element.find(re.compile(r'^h[1-6]$'))
                if h_tag:
                    title = clean_text(h_tag.get_text())
                    a_in_h = h_tag.find('a')
                    if a_in_h and a_in_h.get('href'):
                        source_url = a_in_h['href']
                        if not source_url.startswith('http'):
                            source_url = f"https://mifundinghub.org{source_url}"

            if not title:
                title = clean_text(element.get_text())
                if title and len(title) > 200:
                    title = title[:200]

            if not title or len(title) < 5:
                return None

            full_text = element.get_text(separator=' ', strip=True)

            date_patterns = [
                (r'(?:deadline|due|closes?)\s*[:\-]?\s*(\w+ \d{1,2},?\s*\d{4})', 'deadline'),
                (r'(?:posted|open|start)\s*[:\-]?\s*(\w+ \d{1,2},?\s*\d{4})', 'posted'),
            ]
            for pattern, dtype in date_patterns:
                m = re.search(pattern, full_text, re.IGNORECASE)
                if m:
                    parsed = parse_date(m.group(1))
                    if dtype == 'deadline' and not deadline:
                        deadline = parsed
                    elif dtype == 'posted' and not posted_date:
                        posted_date = parsed

            amount = extract_funding_amount(full_text)
            if amount:
                funding_amount = amount

            agency_match = re.search(
                r'(?:agency|department|organization)\s*[:\-]?\s*([^\n|,]{5,60})',
                full_text, re.IGNORECASE
            )
            if agency_match:
                organization = clean_text(agency_match.group(1))

            for a in element.find_all('a', href=True):
                href = a['href'].lower()
                if any(href.endswith(ext) for ext in ('.pdf', '.doc', '.docx')):
                    full_url = a['href'] if a['href'].startswith('http') else f"https://mifundinghub.org{a['href']}"
                    doc_urls.append(full_url)

            desc_el = element.find(class_=re.compile(r'excerpt|description|summary', re.I))
            if desc_el:
                description = clean_text(desc_el.get_text())
            elif len(full_text) > len(title) + 20:
                description = clean_text(full_text.replace(title, '', 1))[:500]

            category = categorize_opportunity(title, description or '')

            return {
                'title': title,
                'organization': organization,
                'description': description,
                'eligibility': None,
                'funding_amount': funding_amount,
                'deadline': deadline,
                'category': category,
                'location': 'Michigan',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': None,
                'posted_date': posted_date,
                'document_urls': doc_urls,
                'opportunity_type': 'grant',
            }

        except Exception as exc:
            logger.debug(f"Michigan: error parsing grant element: {exc}")
            return None


def get_michigan_scrapers():
    return [MichiganFundingHubScraper()]
