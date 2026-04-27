"""
South Dakota Procurement scraper — BOA Procurement

Scrapes open bid/RFP opportunities from South Dakota's
Bureau of Administration Procurement division.

Source: https://boa.sd.gov/divisions/procurement/default.aspx
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class SouthDakotaProcurementScraper(BaseScraper):
    """Scrapes bid opportunities from SD BOA Procurement."""

    PROCUREMENT_URL = "https://boa.sd.gov/divisions/procurement/default.aspx"
    BIDS_URL = "https://boa.sd.gov/divisions/procurement/bids-and-proposals.aspx"

    def __init__(self):
        super().__init__("South Dakota BOA Procurement")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for SD scraper")
                return self.opportunities

            # Try bids page first, fall back to procurement main page
            for url in [self.BIDS_URL, self.PROCUREMENT_URL]:
                driver.get(url)
                time.sleep(6)

                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                # Look for tables or structured bid content
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    if len(rows) < 2:
                        continue

                    header_text = rows[0].get_text(strip=True).lower()
                    if not any(kw in header_text for kw in ['bid', 'rfp', 'solicitation', 'title', 'description', 'proposal']):
                        continue

                    data_rows = rows[1:]
                    for row in data_rows:
                        if self.reached_limit():
                            break
                        opp = self.parse_opportunity(row)
                        if opp:
                            self.add_opportunity(opp)

                    logger.info(f"  Parsed {len(data_rows)} rows from SD BOA ({url})")
                    break

                # Also check for link-based content
                if not self.opportunities:
                    content = soup.find('div', id='ctl00_ContentPlaceHolder1_pnlContent') or soup.find('main') or soup.find('div', class_='content')
                    if content:
                        links = content.find_all('a', href=True)
                        bid_links = [a for a in links if a['href'].endswith('.pdf') or 'bid' in a.get_text(strip=True).lower() or 'rfp' in a.get_text(strip=True).lower()]
                        for link in bid_links:
                            if self.reached_limit():
                                break
                            opp = self._parse_link(link)
                            if opp:
                                self.add_opportunity(opp)
                        if bid_links:
                            logger.info(f"  Found {len(bid_links)} bid links from SD BOA")

                if self.opportunities:
                    break  # Got results, no need to try alternate URL

        except Exception as e:
            logger.error(f"Error scraping South Dakota BOA: {e}")

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
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
                    href = f"https://boa.sd.gov{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            opp_number = cell_texts[0] if len(cell_texts) > 0 else None
            title = cell_texts[1] if len(cell_texts) > 1 else cell_texts[0]
            deadline_str = cell_texts[-1] if len(cell_texts) > 2 else None

            if not title or len(title) < 3:
                return None

            deadline = parse_date(deadline_str) if deadline_str else None
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of South Dakota',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'South Dakota',
                'source': self.source_name,
                'source_url': detail_url or self.BIDS_URL,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing SD row: {e}")
            return None

    def _parse_link(self, link):
        try:
            title = clean_text(link.get_text(strip=True))
            if not title or len(title) < 5:
                return None
            href = link['href']
            if not href.startswith('http'):
                href = f"https://boa.sd.gov{href}"

            doc_urls = [href] if href.endswith('.pdf') else []
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': 'State of South Dakota',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'South Dakota',
                'source': self.source_name,
                'source_url': href,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'bid',
            }
        except Exception as e:
            logger.warning(f"Error parsing SD link: {e}")
            return None


def get_south_dakota_scrapers():
    return [SouthDakotaProcurementScraper()]


if __name__ == '__main__':
    scraper = SouthDakotaProcurementScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
