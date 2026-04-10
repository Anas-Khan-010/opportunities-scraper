"""
The Grant Portal (TGP) scraper — scrapes grants from thegrantportal.com.

Replaces individual state grant scrapers with a single aggregated source
covering all 50 US states.  Works without login; optional login via env vars
for potential future paid-tier features.

Env vars (optional):
  TGP_EMAIL    — login email
  TGP_PASSWORD — login password
"""

import html as html_mod
import re
import time
import random
import urllib.parse

from scrapers.base_scraper import BaseScraper
from scrapers.state_scrapers import (
    _SeleniumDriverManager,
    SELENIUM_DELAY_RANGE,
)
from config.settings import config
from utils.logger import logger
from utils.helpers import (
    clean_text,
    parse_date,
    categorize_opportunity,
    extract_funding_amount,
)

TGP_STATE_IDS = {
     7: 'Alabama',        8: 'Alaska',        9: 'Arizona',      10: 'Arkansas',
     2: 'California',    11: 'Colorado',     12: 'Connecticut',  13: 'Delaware',
     1: 'Florida',       14: 'Georgia',      15: 'Hawaii',       16: 'Idaho',
    17: 'Illinois',      18: 'Indiana',      19: 'Iowa',         20: 'Kansas',
    21: 'Kentucky',      22: 'Louisiana',    23: 'Maine',        24: 'Maryland',
    25: 'Massachusetts', 26: 'Michigan',     27: 'Minnesota',    28: 'Mississippi',
    29: 'Missouri',      30: 'Montana',      31: 'Nebraska',     32: 'Nevada',
    33: 'New Hampshire',  4: 'New Jersey',   34: 'New Mexico',    3: 'New York',
    36: 'North Carolina',37: 'North Dakota', 38: 'Ohio',         39: 'Oklahoma',
    40: 'Oregon',         5: 'Pennsylvania', 41: 'Rhode Island', 42: 'South Carolina',
    43: 'South Dakota',  44: 'Tennessee',     6: 'Texas',        45: 'Utah',
    46: 'Vermont',       47: 'Virginia',     48: 'Washington',   50: 'West Virginia',
    51: 'Wisconsin',     52: 'Wyoming',
}

BASE_URL = config.TGP_BASE_URL
LOGIN_URL = f'{BASE_URL}/login'
LISTING_TPL = f'{BASE_URL}/?states={{state_id}}&countries=1&filter=1&page={{page}}'

MAX_PAGES_PER_STATE = config.TGP_MAX_PAGES_PER_STATE
DELAY_BETWEEN_PAGES = (1.5, 3)
DELAY_BETWEEN_STATES = (2, 5)

_GRANT_DETAIL_RE = re.compile(r'/grant-details/(\d+)/')


class TGPGrantScraper(BaseScraper):
    """
    Scrapes The Grant Portal — a US grant aggregator with 20,000+ listings.
    One instance covers all 50 states.
    """

    def __init__(self):
        super().__init__('The Grant Portal')
        self.email = config.TGP_EMAIL
        self.password = config.TGP_PASSWORD
        self._logged_in = False
        self._max_new_per_state = config.TGP_MAX_NEW_PER_STATE
        self._max_new = self._max_new_per_state * len(TGP_STATE_IDS)

    def scrape(self):
        logger.info("Starting TGP scraper (all 50 states)...")

        driver = _SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping TGP")
            return self.opportunities

        if self.email and self.password:
            self._login(driver)

        for state_id, state_name in sorted(
            TGP_STATE_IDS.items(), key=lambda x: x[1]
        ):
            if self.reached_limit():
                break
            try:
                self._scrape_state(driver, state_id, state_name)
            except Exception as exc:
                logger.error(f"TGP: error scraping {state_name}: {exc}")

        self.log_summary()
        return self.opportunities

    # ------------------------------------------------------------------
    # Login (optional)
    # ------------------------------------------------------------------

    def _login(self, driver):
        from selenium.webdriver.common.by import By
        try:
            logger.info("TGP: attempting login...")
            driver.get(LOGIN_URL)
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass
            time.sleep(random.uniform(3, 5))
            email_field = self._find_input(driver, By, 'email')
            password_field = self._find_input(driver, By, 'password')
            if not email_field or not password_field:
                logger.warning("TGP: login fields not found — continuing without login")
                return
            email_field.clear()
            email_field.send_keys(self.email)
            time.sleep(0.4)
            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(0.4)
            login_btn = self._find_login_button(driver, By)
            if not login_btn:
                logger.warning("TGP: login button not found — continuing without login")
                return
            login_btn.click()
            try:
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass
            time.sleep(random.uniform(4, 7))
            self._logged_in = True
            logger.info("TGP: login submitted")
        except Exception as exc:
            logger.warning(f"TGP: login failed ({exc}) — continuing without login")

    @staticmethod
    def _find_input(driver, By, field_type):
        if field_type == 'email':
            selectors = ['input[type="email"]', 'input[name="email"]']
        else:
            selectors = ['input[type="password"]', 'input[name="password"]']
        for sel in selectors:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                return elems[0]
        return None

    @staticmethod
    def _find_login_button(driver, By):
        for sel in ['button[type="submit"]', 'input[type="submit"]']:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                txt = (el.text or el.get_attribute('value') or '').lower()
                if any(w in txt for w in ('login', 'log in', 'sign in', 'submit')):
                    return el
        return None

    # ------------------------------------------------------------------
    # Per-state scraping
    # ------------------------------------------------------------------

    def _dismiss_popups(self, driver):
        from selenium.webdriver.common.by import By
        try:
            for sel in [
                'button.swal2-confirm',
                '.modal .close',
                '[data-dismiss="modal"]',
                'button[aria-label="Close"]',
                '.popup-close',
                '#cookieConsentButton',
            ]:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in btns:
                    try:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(0.3)
                    except Exception:
                        pass
            for btn in driver.find_elements(By.XPATH,
                    "//*[contains(text(),'I Consent')]"):
                try:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass

    def _scrape_state(self, driver, state_id, state_name):
        page = 1
        count_before = len(self.opportunities)
        new_before = self._new_count
        seen_ids = set()

        while page <= MAX_PAGES_PER_STATE:
            url = LISTING_TPL.format(state_id=state_id, page=page)
            time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))

            try:
                driver.set_page_load_timeout(60)
                logger.debug(f"TGP: loading {state_name} p{page}...")
                driver.get(url)
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    WebDriverWait(driver, 30).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    pass
                time.sleep(random.uniform(4, 7))
                self._dismiss_popups(driver)
            except Exception as exc:
                logger.warning(f"TGP: page load failed {state_name} p{page}: {exc}")
                break

            html = driver.page_source
            new_grants = self._extract_grants_fast(html, state_name, seen_ids)

            if not new_grants:
                break

            state_done = False
            for grant in new_grants:
                self._enrich_from_detail(driver, grant)
                self.add_opportunity(grant)
                if self._new_count - new_before >= self._max_new_per_state:
                    state_done = True
                    break
                if self.reached_limit():
                    break

            if state_done or self.reached_limit():
                break

            page += 1

            if not self._has_next_page_fast(driver.page_source):
                break

        added = len(self.opportunities) - count_before
        if added > 0:
            logger.info(f"TGP: {state_name} — {added} grants")
        else:
            logger.debug(f"TGP: {state_name} — 0 grants")

        time.sleep(random.uniform(*DELAY_BETWEEN_STATES))

    # ------------------------------------------------------------------
    # Detail page enrichment (eligibility + doc URLs)
    # ------------------------------------------------------------------

    def _enrich_from_detail(self, driver, grant):
        """Visit the grant detail page and extract eligibility + document URLs."""
        detail_url = grant.get('source_url', '')
        if not detail_url or '/grant-details/' not in detail_url:
            return

        try:
            time.sleep(random.uniform(2.0, 4.0))
            driver.get(detail_url)
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass
            time.sleep(random.uniform(4, 7))
            dhtml = driver.page_source or ''

            elig = self._extract_eligibility_from_detail(dhtml)
            if elig:
                grant['eligibility'] = elig

            docs = self._extract_doc_urls_from_detail(dhtml)
            if docs:
                grant['document_urls'] = docs

            desc = self._extract_full_description(dhtml)
            if desc and (not grant.get('description') or len(desc) > len(grant['description'])):
                grant['description'] = desc

        except Exception as exc:
            logger.debug(f"TGP: detail enrichment failed for {detail_url}: {exc}")

    @staticmethod
    def _extract_eligibility_from_detail(html):
        section = re.search(
            r'Eligible\s+Requirements.*?</div>\s*</div>\s*</div>',
            html, re.I | re.DOTALL,
        )
        if not section:
            return None
        labels = re.findall(
            r'<label[^>]*>\s*<input[^>]*checked[^>]*>\s*(.*?)\s*</label>',
            section.group(0), re.I | re.DOTALL,
        )
        if not labels:
            labels = re.findall(
                r'<label[^>]*>\s*<input[^>]*>\s*(.*?)\s*</label>',
                section.group(0), re.I | re.DOTALL,
            )
        items = [clean_text(html_mod.unescape(re.sub(r'<[^>]+>', '', l))) for l in labels]
        items = [i for i in items if i and len(i) > 2]
        return '; '.join(items) if items else None

    @staticmethod
    def _extract_doc_urls_from_detail(html):
        doc_pattern = re.compile(
            r'href="([^"]+\.(?:pdf|doc|docx|xls|xlsx|csv|zip)(?:\?[^"]*)?)"',
            re.I,
        )
        urls = []
        for m in doc_pattern.finditer(html):
            url = m.group(1)
            if url not in urls and 'swal2' not in url and 'cookie' not in url:
                full = urllib.parse.urljoin(BASE_URL, url)
                urls.append(full)
        return urls if urls else []

    @staticmethod
    def _extract_full_description(html):
        m = re.search(
            r'<div[^>]*class="[^"]*space-y-6[^"]*divide-y[^"]*"[^>]*>(.*?)(Eligible\s+Requirements|$)',
            html, re.I | re.DOTALL,
        )
        if not m:
            return None
        raw = m.group(1)
        raw = re.sub(r'<(script|style|svg)[^>]*>.*?</\1>', '', raw, flags=re.DOTALL | re.I)
        text = clean_text(html_mod.unescape(re.sub(r'<[^>]+>', ' ', raw)))
        text = re.sub(r'GrantID:\s*\d+', '', text)
        text = re.sub(r'Grant Funding Amount.*?(?=\.|$)', '', text, flags=re.I)
        text = clean_text(text)
        return text[:1000] if text and len(text) > 30 else None

    # ------------------------------------------------------------------
    # Fast extraction using regex on raw HTML (avoids full BS4 parse of 800KB)
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_heavy_tags(html):
        """Remove SVG, script, and style tags to shrink 800KB pages to ~200KB."""
        html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        return html

    def _extract_grants_fast(self, html, state_name, seen_ids):
        """
        Extract grant data using regex on cleaned HTML.
        SVG icons are stripped first to shrink cards from 15KB to ~2KB each.
        """
        html = self._strip_heavy_tags(html)
        grants = []

        grant_id_pattern = re.compile(
            r'TGP\s+Grant\s+ID\s*:?\s*</p>\s*<p[^>]*>\s*(\d+)',
            re.I,
        )
        detail_link_pattern = re.compile(
            r'href="([^"]*grant-details/(\d+)/[^"]*)"',
            re.I,
        )

        detail_links = {}
        for m in detail_link_pattern.finditer(html):
            detail_links[m.group(2)] = m.group(1)

        for m in grant_id_pattern.finditer(html):
            grant_id = m.group(1)
            if grant_id in seen_ids:
                continue

            card_start = max(0, m.start() - 5000)
            card_html = html[card_start:m.end() + 1000]

            title = self._extract_title_fast(card_html)
            if not title or len(title) < 10:
                continue

            seen_ids.add(grant_id)

            deadline_str = self._extract_deadline_fast(card_html)
            funding = self._extract_funding_fast(card_html)
            description = self._extract_description_fast(card_html, title)
            eligibility = self._extract_eligibility_fast(card_html)

            source_path = detail_links.get(grant_id)
            if source_path:
                raw_url = source_path.replace('&amp;', '&')
                source_url = urllib.parse.urljoin(BASE_URL, raw_url)
            else:
                source_url = f'{BASE_URL}/grant-details/{grant_id}/'

            category = categorize_opportunity(title, description or '')

            deadline = None
            if deadline_str and deadline_str.lower() not in (
                'ongoing', 'open', 'n/a', 'tbd', 'rolling',
            ):
                deadline = parse_date(deadline_str)

            doc_urls = self._extract_doc_urls_fast(card_html)

            grants.append({
                'title': title,
                'organization': 'The Grant Portal',
                'description': description,
                'eligibility': eligibility,
                'funding_amount': funding,
                'deadline': deadline,
                'category': category,
                'location': state_name,
                'source': f'TGP - {state_name} Grants',
                'source_url': source_url,
                'opportunity_number': f'TGP-{grant_id}',
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'grant',
            })

        return grants

    @staticmethod
    def _extract_title_fast(card_html):
        m = re.search(
            r'<p[^>]*class="[^"]*text-xl[^"]*"[^>]*>(.*?)</p>',
            card_html,
            re.I | re.DOTALL,
        )
        if m:
            title = html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())
            if title and len(title) > 10:
                return clean_text(title)

        m = re.search(
            r'<h[1-5][^>]*>(.*?)</h[1-5]>',
            card_html,
            re.I | re.DOTALL,
        )
        if m:
            title = html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())
            if title and len(title) > 10:
                return clean_text(title)
        return None

    @staticmethod
    def _extract_deadline_fast(card_html):
        m = re.search(
            r'Deadline\s*:?\s*</span>\s*<span[^>]*>\s*(.*?)\s*</span>',
            card_html,
            re.I | re.DOTALL,
        )
        if m:
            return clean_text(re.sub(r'<[^>]+>', '', m.group(1)))
        m = re.search(
            r'Deadline\s*:?\s*([A-Za-z0-9\s,/\-]+?)(?:\s*Funding|\s*<)',
            card_html,
            re.I,
        )
        if m:
            return clean_text(m.group(1))
        return None

    @staticmethod
    def _extract_funding_fast(card_html):
        m = re.search(
            r'Funding\s*Amount\s*:?\s*</span>\s*<span[^>]*>\s*(.*?)\s*</span>',
            card_html,
            re.I | re.DOTALL,
        )
        if m:
            raw = clean_text(re.sub(r'<[^>]+>', '', m.group(1)))
            if raw and raw.lower() not in ('open', 'n/a', 'tbd'):
                return raw
        m = re.search(
            r'Funding\s*Amount\s*:?\s*(\$[\d,]+(?:\.\d+)?)',
            card_html,
            re.I,
        )
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _extract_description_fast(card_html, title):
        m = re.search(
            r'<p[^>]*class="[^"]*text-gray-500[^"]*"[^>]*>(.*?)</p>',
            card_html,
            re.I | re.DOTALL,
        )
        if m:
            desc = clean_text(html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1))))
            if desc and len(desc) > 20 and desc != title:
                return desc[:500]
        return None

    @staticmethod
    def _extract_eligibility_fast(card_html):
        """Extract eligibility from 'Eligible Requirements' checkbox labels."""
        section = re.search(
            r'Eligible\s+Requirements.*?</div>\s*</div>',
            card_html,
            re.I | re.DOTALL,
        )
        if not section:
            return None
        labels = re.findall(
            r'<label[^>]*>\s*<input[^>]*>\s*(.*?)\s*</label>',
            section.group(0),
            re.I | re.DOTALL,
        )
        if not labels:
            return None
        items = [clean_text(html_mod.unescape(re.sub(r'<[^>]+>', '', l))) for l in labels]
        items = [i for i in items if i]
        return '; '.join(items) if items else None

    @staticmethod
    def _extract_doc_urls_fast(card_html):
        doc_exts = re.compile(
            r'href="([^"]+\.(?:pdf|doc|docx|xls|xlsx|csv|zip)(?:\?[^"]*)?)"',
            re.I,
        )
        urls = []
        for m in doc_exts.finditer(card_html):
            url = m.group(1)
            if url not in urls:
                urls.append(urllib.parse.urljoin(BASE_URL, url))
        return urls

    @staticmethod
    def _has_next_page_fast(html):
        return bool(re.search(
            r'>\s*Next\s*<',
            html,
            re.I,
        ))

    def parse_opportunity(self, element):
        return None


def get_tgp_grant_scrapers():
    """Return a list containing the single TGP scraper instance."""
    return [TGPGrantScraper()]
