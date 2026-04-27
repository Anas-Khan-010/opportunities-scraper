"""
Georgia Procurement scraper — DOAS Team Georgia Marketplace / Bid Search

Scrapes open bid opportunities from Georgia's Department of Administrative
Services procurement portal.

Source: https://doas.ga.gov/state-purchasing/bids-and-solicitations
Fallback: https://ssl.doas.state.ga.us/PRSapp/PR/bid_search.jsp
"""

import time
import random
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class GeorgiaProcurementScraper(BaseScraper):
    """Scrapes bid opportunities from Georgia GPR (PeopleSoft Registry)."""

    SEARCH_URLS = [
        "https://ssl.doas.state.ga.us/gpr/", # Official Georgia Procurement Registry
        "https://doas.ga.gov/state-purchasing/bids-and-solicitations", # Main Landing
    ]

    def __init__(self):
        super().__init__("Georgia DOAS Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        # Georgia's official registry is behind an aggressive WAF. MUST use residential proxy.
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver:
            logger.error("Selenium driver unavailable — skipping Georgia")
            return self.opportunities

        for url in self.SEARCH_URLS:
            try:
                logger.info(f"  Accessing {url}...")
                driver.get(url)
                time.sleep(random.uniform(8, 12))

                # Handle GPR (PeopleSoft)
                if "ssl.doas.state.ga.us/gpr/" in url:
                    # GPR often requires a 'Search' button click to show all results
                    try:
                        search_btn = driver.find_element_by_css_selector('input[type="submit"][value*="Search"], button[id*="Search"]')
                        if search_btn:
                            search_btn.click()
                            time.sleep(5)
                    except:
                        pass # Might already be on results page or button named differently

                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')

                    # PeopleSoft Grid Selectors
                    # Rows are usually in the 4th table or have ps_grid classes
                    rows = soup.select('table.ps_grid-table tr:not(:first-child)') or \
                           soup.select('tr[id*="row"], .ps_grid-row') or \
                           soup.find_all('table')[-1].find_all('tr')[1:] # Final fallback

                    for row in rows:
                        if self.reached_limit(): break
                        cells = row.find_all('td')
                        if len(cells) < 4: continue

                        try:
                            # PeopleSoft Columns: Sol # (Link), Title, Agency, Date
                            link_el = cells[0].find('a')
                            opp_num = clean_text(cells[0].get_text(strip=True))
                            title = clean_text(cells[1].get_text(strip=True))
                            org = clean_text(cells[2].get_text(strip=True))
                            deadline_str = clean_text(cells[3].get_text(strip=True))

                            if not title or len(title) < 5: continue

                            source_url = url
                            if link_el and link_el.get('href'):
                                href = link_el['href']
                                source_url = f"https://ssl.doas.state.ga.us{href}" if href.startswith('/') else href

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
                        except: continue
                else:
                    # Handle main landing page (mostly PDF links)
                    html = driver.page_source
                    soup = BeautifulSoup(html, 'html.parser')
                    links = soup.find_all('a', href=True)
                    for link in links:
                        if self.reached_limit(): break
                        text = clean_text(link.get_text(strip=True))
                        href = link['href']
                        if not href.startswith('http'): href = f"https://doas.ga.gov{href}"
                        
                        if any(kw in text.lower() for kw in ['bid', 'rfp', 'itb']) or href.endswith('.pdf'):
                            self.add_opportunity({
                                'title': text, 'organization': 'State of Georgia',
                                'description': None, 'deadline': None,
                                'category': categorize_opportunity(text, ''),
                                'location': 'Georgia', 'source': self.source_name,
                                'source_url': href, 'opportunity_number': None,
                                'posted_date': None, 'document_urls': [href] if href.endswith('.pdf') else [],
                                'opportunity_type': 'bid',
                            })

                if self.opportunities:
                    break

            except Exception as e:
                logger.warning(f"Error accessing GA DOAS at {url}: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row, source_url):
        cells = row.find_all('td')
        if len(cells) < 2:
            return None

        try:
            cell_texts = [clean_text(c.get_text(strip=True)) for c in cells]
            links = row.find_all('a', href=True)
            detail_url = None
            doc_urls = []
            for link in links:
                href = link['href']
                if not href.startswith('http'):
                    href = f"https://doas.ga.gov{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            title = max(cell_texts, key=len) if cell_texts else None
            if not title or len(title) < 5:
                return None

            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of Georgia',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'Georgia',
                'source': self.source_name,
                'source_url': detail_url or source_url,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing GA row: {e}")
            return None


def get_georgia_scrapers():
    return [GeorgiaProcurementScraper()]
