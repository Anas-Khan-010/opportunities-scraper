"""
Connecticut Procurement scraper — CTsource Bid Board (WebProcure / Proactis)

Scrapes open solicitations from Connecticut's CTsource bid board, which
is hosted on WebProcure / Proactis Cloud as a single-page Angular app.
We deep-link to the State of CT instance (customerid=51) and wait for
the SPA to render its card-based bid grid before parsing.

Source: https://portal.ct.gov/das/ctsource/bidboard
        → https://webprocure.proactiscloud.com/wp-web-public/en/#/bidboard/search?customerid=51
"""

import re
import time
import random

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class ConnecticutBidBoardScraper(BaseScraper):
    """Scrapes bid opportunities from CT CTsource Bid Board (WebProcure)."""

    BID_BOARD_URL = (
        "https://webprocure.proactiscloud.com/wp-web-public/en/"
        "#/bidboard/search?customerid=51"
    )
    BASE_URL = "https://webprocure.proactiscloud.com/wp-web-public/en/"

    def __init__(self):
        super().__init__("Connecticut CTsource")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for Connecticut scraper")
                return self.opportunities

            driver.get(self.BID_BOARD_URL)
            # WebProcure is an Angular SPA and is slow to render the grid;
            # wait staged: initial JS bundle, then bid card materialization.
            time.sleep(random.uniform(10, 14))

            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR,
                         'a[href*="/bidboard/bid/"], .card a[href*="/bidboard/"]')
                    )
                )
            except Exception:
                logger.debug("CT: bid card link didn't appear via WebDriverWait")

            # Scroll a couple of times — Proactis lazy-loads more cards as
            # the user scrolls, so a single scroll only grabs the first batch.
            for offset in (500, 1500, 3000):
                try:
                    driver.execute_script(f"window.scrollTo(0, {offset});")
                except Exception:
                    pass
                time.sleep(random.uniform(2, 3.5))

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Each rendered bid is a <div class="card">; some Proactis tenants
            # ship "bid-card" / "solicitation-card" instead. Try them all.
            cards = (
                soup.select('.card')
                or soup.select('div[class*="bid-card"], div[class*="solicitation"]')
                or soup.select('div[class*="bid"]')
            )
            # Filter to cards that actually contain a bid-detail link — the
            # SPA also renders filter / nav cards that we don't want.
            cards = [c for c in cards if c.select_one('a[href*="/bidboard/bid/"]')]
            logger.info(f"  Found {len(cards)} bid cards on CT board")

            for card in cards:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(card)
                if opp:
                    self.add_opportunity(opp)

        except Exception as e:
            logger.error(f"Error scraping Connecticut CTsource: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, card):
        try:
            # Title link contains both number and title usually in format "NUMBER | TITLE"
            link_el = card.select_one('a[href*="/bidboard/bid/"]')
            if not link_el:
                return None

            full_text = clean_text(link_el.get_text(strip=True))
            if not full_text:
                return None

            # Split number and title if pipe exists
            if '|' in full_text:
                opp_number, title = [clean_text(x) for x in full_text.split('|', 1)]
            else:
                opp_number = None
                title = full_text

            if not title or len(title) < 4:
                return None

            href = (link_el.get('href') or '').strip()
            if href.startswith('#'):
                source_url = f"{self.BASE_URL}{href}"
            elif href.startswith('http'):
                source_url = href
            else:
                # Build a stable per-bid URL even when href is missing.
                anchor = opp_number or title[:80].replace(' ', '_')
                source_url = f"{self.BASE_URL}#/bidboard/search?customerid=51#{anchor}"

            # Agency: prefer the icon-prefixed span (building icon), then
            # fall back to any span/div carrying an "agency" label.
            org = None
            content = card.select_one('.card-content') or card
            icon_span = content.select_one('i.material-icons + span')
            if icon_span:
                cand = clean_text(icon_span.get_text(strip=True))
                if cand and len(cand) < 200:
                    org = cand
            if not org:
                for span in content.find_all('span'):
                    t = clean_text(span.get_text(strip=True))
                    if not t:
                        continue
                    if any(kw in t.lower() for kw in ('agency:', 'department:', 'organization:')):
                        org = re.sub(r'^[^:]+:\s*', '', t).strip() or None
                        if org:
                            break
            if not org:
                spans = [s for s in content.find_all('span') if clean_text(s.get_text(strip=True))]
                if spans:
                    cand = clean_text(spans[-1].get_text(strip=True))
                    if cand and len(cand) < 200:
                        org = cand

            # Deadline — span pairs of "End Date:" / value, or any span
            # containing a date that's labelled close/due/end.
            deadline = None
            date_spans = card.find_all('span')
            for i, span in enumerate(date_spans):
                text = span.get_text(separator=' ', strip=True).lower()
                if any(kw in text for kw in ('end date', 'close date', 'due date')):
                    if i + 1 < len(date_spans):
                        deadline_str = clean_text(date_spans[i + 1].get_text(strip=True))
                        deadline = parse_date(deadline_str)
                        if deadline:
                            break

            category = categorize_opportunity(title, "")

            return {
                'title': title,
                'organization': org or 'State of Connecticut',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'Connecticut',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'bid',
            }

        except Exception as e:
            logger.warning(f"Error parsing CT card: {e}")
            return None


def get_connecticut_scrapers():
    return [ConnecticutBidBoardScraper()]


if __name__ == '__main__':
    scraper = ConnecticutBidBoardScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
