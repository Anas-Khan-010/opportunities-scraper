"""
Oklahoma Procurement scraper — OMES Central Purchasing Solicitations

Scrapes open solicitations from Oklahoma's Office of Management
and Enterprise Services (OMES) Central Purchasing Division.

Source: https://oklahoma.gov/omes/services/purchasing/solicitations.html
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class OklahomaSolicitationsScraper(BaseScraper):
    """
    Oklahoma Procurement scraper — OMES Public Search Utility & CMS listings.
    
    Target 1: https://apps.ok.gov/dcs/solicit/app/index.php (Official Search Utility)
    Target 1: https://oklahoma.gov/omes/services/purchasing/solicitations.html (CMS Landing)
    """

    SEARCH_URLS = [
        "https://apps.ok.gov/dcs/solicit/app/index.php",
        "https://oklahoma.gov/omes/services/purchasing/solicitations.html",
    ]

    def __init__(self):
        super().__init__("Oklahoma OMES Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        # Oklahoma has aggressive Geo-blocking (CloudFront). MUST use residential proxy.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Oklahoma")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                if "apps.ok.gov" in url:
                    self._scrape_utility(driver)
                else:
                    self._scrape_cms(driver)

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error scraping Oklahoma at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def _scrape_utility(self, driver):
        """Parse the custom OMES Solicitations utility grid."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        # The utility usually renders a table with results
        rows = soup.find_all('tr')
        if not rows: return

        for row in rows:
            if self.reached_limit(): break
            cells = row.find_all('td')
            if len(cells) < 3: continue

            try:
                # Utility columns: Sol #, Title, Closing Date
                opp_num = clean_text(cells[0].get_text(strip=True))
                title = clean_text(cells[1].get_text(strip=True))
                deadline_str = clean_text(cells[2].get_text(strip=True)) if len(cells) > 2 else None

                if not title or len(title) < 5: continue

                link = row.find('a', href=True)
                source_url = self.SEARCH_URLS[0]
                if link:
                    href = link['href']
                    source_url = f"https://apps.ok.gov/dcs/solicit/app/{href}" if not href.startswith('http') else href

                self.add_opportunity({
                    'title': title,
                    'organization': 'State of Oklahoma',
                    'description': None,
                    'deadline': parse_date(deadline_str) if deadline_str else None,
                    'category': categorize_opportunity(title, ''),
                    'location': 'Oklahoma',
                    'source': self.source_name,
                    'source_url': source_url,
                    'opportunity_number': opp_num,
                    'posted_date': None,
                    'document_urls': [],
                    'opportunity_type': 'rfp',
                })
            except: continue

    def _scrape_cms(self, driver):
        """Parse standard link-based CMS list."""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            if self.reached_limit(): break
            text = clean_text(link.get_text(strip=True))
            href = link['href']
            if not href.startswith('http'): href = f"https://oklahoma.gov{href}"
            
            if len(text) > 10 and (href.endswith('.pdf') or 'solicitation' in href.lower()):
                self.add_opportunity({
                    'title': text,
                    'organization': 'State of Oklahoma',
                    'description': None,
                    'deadline': None,
                    'category': categorize_opportunity(text, ""),
                    'location': 'Oklahoma',
                    'source': self.source_name,
                    'source_url': href,
                    'opportunity_number': None,
                    'posted_date': None,
                    'document_urls': [href] if href.endswith('.pdf') else [],
                    'opportunity_type': 'rfp',
                })

def get_oklahoma_scrapers():
    return [OklahomaSolicitationsScraper()]


def get_oklahoma_scrapers():
    return [OklahomaSolicitationsScraper()]


if __name__ == '__main__':
    scraper = OklahomaSolicitationsScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
