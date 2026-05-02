"""
Georgia Procurement scraper — DOAS / Georgia Procurement Registry (PeopleSoft).

Sources:
  1. https://ssl.doas.state.ga.us/gpr/  — Official Georgia Procurement Registry
  2. https://doas.ga.gov/state-purchasing/bids-and-solicitations  — landing page

Notes:
  - GPR is a PeopleSoft grid; we map labelled headers to indices instead
    of guessing column positions.
  - Selenium 4 API is used (find_element_by_* was removed).
  - Bare except blocks were upgraded to logged debug warnings so silent
    parsing failures stop hiding regressions.
"""

import time
import random
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class GeorgiaProcurementScraper(BaseScraper):
    """Scrapes bid opportunities from Georgia GPR (PeopleSoft Registry)."""

    # The previous fallback URL "/state-purchasing/bids-and-solicitations" is
    # a permanent 404 (canonical = /404-page-not-found). Replaced with the
    # current live route. The GPR portal is the primary source; the landing
    # page is parsed for any inline bid-link or PDF references.
    SEARCH_URLS = [
        "https://ssl.doas.state.ga.us/gpr/",
        "https://doas.ga.gov/state-purchasing/supplier-registration-bid-notices",
    ]
    GPR_BASE = "https://ssl.doas.state.ga.us"

    def __init__(self):
        super().__init__("Georgia DOAS Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Georgia")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "ssl.doas.state.ga.us" in url:
                    self._scrape_gpr(driver, url)
                else:
                    self._scrape_landing(driver, url)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error accessing GA DOAS at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_gpr(self, driver, url):
        """Parse the PeopleSoft grid on the Georgia Procurement Registry."""
        try:
            try:
                btn = driver.find_element(
                    By.CSS_SELECTOR,
                    'input[type="submit"][value*="Search"], button[id*="Search"]',
                )
                btn.click()
                time.sleep(5)
            except Exception:
                pass

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            target_table = None
            header_map = {}
            for table in soup.find_all('table'):
                head = table.find('thead') or table.find('tr')
                if not head:
                    continue
                cells = head.find_all(['th', 'td'])
                labels = [(clean_text(c.get_text(' ', strip=True)) or '').lower() for c in cells]
                if not any(
                    kw in ' '.join(labels)
                    for kw in ('solicitation', 'title', 'description', 'agency', 'date')
                ):
                    continue
                for i, label in enumerate(labels):
                    if label and label not in header_map:
                        header_map[label] = i
                target_table = table
                break

            if target_table is not None:
                tbody = target_table.find('tbody')
                rows = tbody.find_all('tr') if tbody else target_table.find_all('tr')[1:]
            else:
                rows = (
                    soup.select('table.ps_grid-table tr:not(:first-child)')
                    or soup.select('tr[id*="row"], .ps_grid-row')
                )
                if not rows and soup.find_all('table'):
                    rows = soup.find_all('table')[-1].find_all('tr')[1:]

            def _idx(*needles):
                for needle in needles:
                    for label, idx in header_map.items():
                        if needle in label:
                            return idx
                return None

            i_num = _idx('solicitation', 'event', 'bid', '#')
            i_title = _idx('title', 'description', 'name')
            i_org = _idx('agency', 'organization', 'department')
            i_deadline = _idx('close', 'due', 'date', 'opening', 'end')

            for row in rows:
                if self.reached_limit():
                    break
                cells = row.find_all('td')
                if len(cells) < 4:
                    continue
                try:
                    def _cell(i):
                        if i is not None and i < len(cells):
                            return clean_text(cells[i].get_text(' ', strip=True))
                        return ''

                    opp_num = _cell(i_num) or clean_text(cells[0].get_text(' ', strip=True))
                    title = _cell(i_title) or clean_text(cells[1].get_text(' ', strip=True))
                    org = _cell(i_org) or clean_text(cells[2].get_text(' ', strip=True))
                    deadline_str = _cell(i_deadline) or clean_text(cells[-1].get_text(' ', strip=True))

                    if not title or len(title) < 5:
                        continue

                    detail_url = None
                    for link in row.find_all('a', href=True):
                        href = link.get('href', '').strip()
                        if not href:
                            continue
                        hl = href.lower()
                        if hl.startswith(('javascript:', 'mailto:', '#')):
                            continue
                        detail_url = href if href.startswith('http') else urljoin(self.GPR_BASE, href)
                        break

                    anchor = opp_num or title[:80].replace(' ', '_')
                    source_url = detail_url or f"{url}#{anchor}"

                    self.add_opportunity({
                        'title': title,
                        'organization': org or 'State of Georgia',
                        'description': None,
                        'eligibility': None,
                        'funding_amount': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'Georgia',
                        'source': self.source_name,
                        'source_url': source_url,
                        'opportunity_number': opp_num,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except Exception as e:
                    logger.debug(f"  GA GPR row failed: {e}")
                    continue
        except Exception as e:
            logger.warning(f"GA GPR parse failure: {e}")

    def _scrape_landing(self, driver, url):
        """Parse the doas.ga.gov landing page (mostly PDF + bid links)."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        seen = set()
        for link in soup.find_all('a', href=True):
            if self.reached_limit():
                break
            href = link.get('href', '').strip()
            text = clean_text(link.get_text(' ', strip=True))
            if not href or not text:
                continue
            hl = href.lower()
            if hl.startswith(('javascript:', 'mailto:', '#')):
                continue

            full = href if href.startswith('http') else urljoin('https://doas.ga.gov', href)
            if full in seen:
                continue

            tl = text.lower()
            is_doc = full.lower().endswith(('.pdf', '.doc', '.docx'))
            is_bid_keyword = any(kw in tl for kw in ('bid', 'rfp', 'itb', 'rfq', 'solicitation'))
            if not (is_doc or is_bid_keyword):
                continue
            seen.add(full)

            self.add_opportunity({
                'title': text[:300],
                'organization': 'State of Georgia',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': categorize_opportunity(text, ''),
                'location': 'Georgia',
                'source': self.source_name,
                'source_url': full,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': [full] if is_doc else [],
                'opportunity_type': 'bid',
            })

    def parse_opportunity(self, element):
        """Required by BaseScraper. Row parsing is inlined in scrape()."""
        return None


def get_georgia_scrapers():
    return [GeorgiaProcurementScraper()]
