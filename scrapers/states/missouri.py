"""
Missouri Procurement scraper — MissouriBUYS / OA Purchasing

Source: https://oa.mo.gov/purchasing/vendor-information/current-bid-opportunities
"""
import time, random
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
# parse_date was being called below but not imported, so every row went
# through the bare `except: continue` and silently dropped — the scraper
# always returned 0 rows. Importing it makes the parser actually work.
from utils.helpers import clean_text, parse_date, categorize_opportunity

class MissouriProcurementScraper(BaseScraper):
    """
    Missouri Procurement scraper — MissouriBUYS (Ivalua) & Official Bid Locator.
    
    Target 1: https://missouribuys.mo.gov/bidboard (Official Ivalua Portal)
    Target 2: https://www.instantmarkets.com/q/missouri_state (Official Referral)
    """
    
    SEARCH_URLS = [
        "https://missouribuys.mo.gov/bidboard",
        "https://www.instantmarkets.com/q/missouri_state",
    ]

    def __init__(self):
        super().__init__("Missouri Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Missouri has a strict WAF (Imperva). We MUST route via proxy for the .gov site.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Missouri")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                # Handle Ivalua Grid (MissouriBUYS)
                if "missouribuys.mo.gov" in url:
                    self._scrape_ivalua(driver)
                else:
                    # Handle InstantMarkets (Official Referral)
                    self._scrape_simple_table(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Missouri at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_ivalua(self, driver):
        """Parse MissouriBUYS Ivalua grid blocks."""
        page_src = driver.page_source or ''
        if 'Incapsula' in page_src or 'incident ID' in page_src:
            logger.warning(
                "Missouri MissouriBUYS: Imperva block detected — "
                "falling back to InstantMarkets"
            )
            return

        soup = BeautifulSoup(page_src, 'html.parser')

        # Find a table that actually contains a header so we can map column
        # labels to indices instead of guessing. Avoids the previous bug
        # where Org/Deadline cells got swapped on layout changes.
        target_table = None
        header_map = {}
        for table in soup.find_all('table'):
            head = table.find('thead') or table.find('tr')
            if not head:
                continue
            cells = head.find_all(['th', 'td'])
            if len(cells) < 3:
                continue
            for i, c in enumerate(cells):
                label = (clean_text(c.get_text(' ', strip=True)) or '').lower()
                if label and label not in header_map:
                    header_map[label] = i
            if header_map:
                target_table = table
                break

        if target_table is not None:
            tbody = target_table.find('tbody')
            rows = tbody.find_all('tr') if tbody else target_table.find_all('tr')[1:]
        else:
            rows = soup.select('tr[class*="grid-row"], .iv-grid-row') or soup.find_all('tr')

        def _idx(*needles):
            for needle in needles:
                for label, idx in header_map.items():
                    if needle in label:
                        return idx
            return None

        i_id = _idx('reference', 'bid #', 'bid number', 'opportunity #', 'id')
        i_title = _idx('title', 'description', 'name')
        i_org = _idx('agency', 'organization', 'department', 'buyer')
        i_deadline = _idx('close', 'due', 'end', 'opening')

        seen = 0
        for row in rows:
            if self.reached_limit():
                break
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            seen += 1

            try:
                def _cell(i, default=''):
                    if i is not None and i < len(cells):
                        return clean_text(cells[i].get_text(' ', strip=True))
                    return default

                opp_id = _cell(i_id) or clean_text(cells[0].get_text(' ', strip=True))
                title = _cell(i_title) or clean_text(cells[1].get_text(' ', strip=True))
                org = _cell(i_org) or (clean_text(cells[2].get_text(' ', strip=True)) if len(cells) > 2 else '')
                deadline_str = _cell(i_deadline) or (clean_text(cells[-1].get_text(' ', strip=True)) if len(cells) > 3 else '')

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
                    detail_url = href if href.startswith('http') else urljoin(self.SEARCH_URLS[0], href)
                    break

                anchor = opp_id or title[:80].replace(' ', '_')
                source_url = detail_url or f"{self.SEARCH_URLS[0]}#{anchor}"

                self.add_opportunity({
                    'title': title,
                    'organization': org or 'State of Missouri',
                    'description': None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, ''),
                    'location': 'Missouri',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_id,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except Exception as exc:
                logger.debug(f"Missouri Ivalua row parse failed: {exc}")
                continue

        logger.info(f"Missouri Ivalua: parsed {seen} candidate rows")

    def _scrape_simple_table(self, driver):
        """Parse InstantMarkets — anchor-driven discovery.

        InstantMarkets renders bids as ``<a href="/view/<id>">...</a>``
        anchors inside various containers; the previous class-name heuristic
        only matched ~1 in 10 because most cards aren't tagged with "bid"
        or "item" in their classes. We pivot to anchor discovery and walk
        up to the parent block for the surrounding metadata.
        """
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        seen = set()
        anchors = [
            a for a in soup.find_all('a', href=True)
            if (a.get('href') or '').startswith('/view/')
        ]
        logger.info(f"Missouri InstantMarkets: found {len(anchors)} /view anchors")

        for link in anchors:
            if self.reached_limit():
                break
            try:
                href = link['href']
                if href in seen:
                    continue
                seen.add(href)

                # Use ' ' separator so span-level chunks don't run together
                # (the old code used strip=True without a sep, producing
                # titles like "HVAC System UpgradesMissouriStateHighway").
                title = clean_text(link.get_text(' ', strip=True))
                container = link.find_parent(['tr', 'div', 'li', 'article']) or link
                ctx_text = clean_text(container.get_text(' ', strip=True))
                if not title:
                    title = (ctx_text.split('\n')[0] if ctx_text else '')[:200]
                if not title or len(title) < 5:
                    continue

                full_url = href if href.startswith('http') else f"https://www.instantmarkets.com{href}"

                self.add_opportunity({
                    'title': title[:300],
                    'organization': 'State of Missouri',
                    'description': ctx_text[:500] if ctx_text else None,
                    'eligibility': None,
                    'funding_amount': None,
                    'deadline': None,
                    'category': categorize_opportunity(title, ctx_text or ''),
                    'location': 'Missouri',
                    'source': self.source_name,
                    'source_url': full_url,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'bid',
                })
            except Exception as e:
                logger.debug(f"  Missouri InstantMarkets row failed: {e}")
                continue

    def parse_opportunity(self, element):
        """Required by BaseScraper. Row parsing is inlined in scrape()."""
        return None


def get_missouri_scrapers():
    return [MissouriProcurementScraper()]
