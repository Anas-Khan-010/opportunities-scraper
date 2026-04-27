"""
Florida Procurement scraper — Florida Vendor Information Portal (VIP)

Target: https://vendor.myfloridahome.com/
Official state portal for all bidding opportunities managed by MyFloridaMarketPlace (MFMP).
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

class FloridaVIPScraper(BaseScraper):
    """Scrapes bid opportunities from the Florida Vendor Information Portal (VIP)."""

    SEARCH_URL = "https://vendor.myfloridahome.com/search/bids"

    def __init__(self):
        super().__init__("Florida VIP Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        
        # Florida VIP uses MFMP which can be protected by Cloudflare.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Florida VIP")
            return self.opportunities

        try:
            logger.info(f"  Accessing {self.SEARCH_URL}...")
            driver.get(self.SEARCH_URL)
            time.sleep(random.uniform(10, 15))

            # Florida VIP search usually lists results immediately or requires a 'Search' click.
            # Handle potential Cloudflare "Just a moment"
            if "Just a moment" in driver.page_source:
                time.sleep(15)

            # If the page requires clicking search to show all
            try:
                search_btn = driver.find_element_by_css_selector('button[type="submit"], .btn-primary')
                if search_btn:
                    search_btn.click()
                    time.sleep(8)
            except:
                pass

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # VIP Grid Selectors (Kendo UI or standard table)
            rows = soup.select('tr[role="row"], .k-grid-table tr, .bid-results-table tr')
            if not rows:
                rows = soup.find_all('tr')[1:] # Generic fallback

            for row in rows:
                if self.reached_limit(): break
                cells = row.find_all('td')
                if len(cells) < 4: continue

                try:
                    # VIP Columns: ID/Number, Title, Agency, Date
                    opp_num = clean_text(cells[0].get_text(strip=True))
                    title = clean_text(cells[1].get_text(strip=True))
                    org = clean_text(cells[2].get_text(strip=True))
                    deadline_str = clean_text(cells[3].get_text(strip=True))

                    if not title or len(title) < 5: continue

                    link = row.find('a', href=True)
                    source_url = self.SEARCH_URL
                    if link:
                        href = link['href']
                        source_url = f"https://vendor.myfloridahome.com{href}" if not href.startswith('http') else href

                    self.add_opportunity({
                        'title': title,
                        'organization': org or 'State of Florida',
                        'description': None,
                        'deadline': parse_date(deadline_str) if deadline_str else None,
                        'category': categorize_opportunity(title, ''),
                        'location': 'Florida',
                        'source': self.source_name,
                        'source_url': source_url,
                        'opportunity_number': opp_num,
                        'posted_date': None,
                        'document_urls': [],
                        'opportunity_type': 'bid',
                    })
                except: continue

        except Exception as e:
            logger.error(f"Error scraping Florida VIP: {e}")

        self.log_summary()
        return self.opportunities

def get_florida_procurement_scrapers():
    return [FloridaVIPScraper()]
