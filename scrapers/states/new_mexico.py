"""
New Mexico Procurement scraper — GSD State Purchasing Active ITBs & RFPs

Scrapes open solicitations from New Mexico's General Services
Department State Purchasing page.

Source: https://generalservices.state.nm.us/state-purchasing/active-itbs-and-rfps/
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class NewMexicoPurchasingScraper(BaseScraper):
    """Scrapes active ITBs and RFPs from NM GSD."""

    ACTIVE_URL = "https://generalservices.state.nm.us/state-purchasing/active-itbs-and-rfps/"

    def __init__(self):
        super().__init__("New Mexico GSD Purchasing")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")

        try:
            driver = SeleniumDriverManager.get_driver()
            if not driver:
                logger.error("Could not get Selenium driver for New Mexico scraper")
                return self.opportunities

            driver.get(self.ACTIVE_URL)
            time.sleep(6)

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # WordPress-based page — look for tables or structured content
            tables = soup.find_all('table')
            if tables:
                for table in tables:
                    rows = table.find_all('tr')
                    if len(rows) < 2:
                        continue

                    data_rows = rows[1:]
                    for row in data_rows:
                        if self.reached_limit():
                            break
                        opp = self.parse_opportunity(row)
                        if opp:
                            self.add_opportunity(opp)

                    logger.info(f"  Parsed {len(data_rows)} rows from NM GSD")
            else:
                # Try structured content (WordPress pages sometimes use lists)
                content = soup.find('div', class_=lambda x: x and ('entry-content' in str(x) or 'page-content' in str(x)))
                if content:
                    items = content.find_all(['li', 'p'])
                    for item in items:
                        if self.reached_limit():
                            break
                        opp = self._parse_content_item(item)
                        if opp:
                            self.add_opportunity(opp)
                    logger.info(f"  Parsed {len(items)} content items from NM GSD")

        except Exception as e:
            logger.error(f"Error scraping New Mexico GSD: {e}")

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
                    href = f"https://generalservices.state.nm.us{href}"
                if href.endswith('.pdf'):
                    doc_urls.append(href)
                elif not detail_url:
                    detail_url = href

            # NM table: RFP#/ITB#, Title, Agency, Due Date
            opp_number = cell_texts[0] if len(cell_texts) > 0 else None
            title = cell_texts[1] if len(cell_texts) > 1 else cell_texts[0]
            org = cell_texts[2] if len(cell_texts) > 2 else 'State of New Mexico'
            deadline_str = cell_texts[3] if len(cell_texts) > 3 else None

            if not title or len(title) < 3:
                return None

            # Determine type from the number
            opp_type = 'rfp'
            if opp_number and 'itb' in opp_number.lower():
                opp_type = 'bid'

            deadline = parse_date(deadline_str) if deadline_str else None
            source_url = detail_url or self.ACTIVE_URL
            category = categorize_opportunity(title, '')

            return {
                'title': title,
                'organization': org if org else 'State of New Mexico',
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': deadline,
                'category': category,
                'location': 'New Mexico',
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': opp_type,
            }
        except Exception as e:
            logger.warning(f"Error parsing NM row: {e}")
            return None

    def _parse_content_item(self, item):
        """Parse from a WordPress content list item or paragraph."""
        try:
            link = item.find('a', href=True)
            if not link:
                return None

            title = clean_text(link.get_text(strip=True))
            if not title or len(title) < 5:
                return None

            href = link['href']
            if not href.startswith('http'):
                href = f"https://generalservices.state.nm.us{href}"

            doc_urls = [href] if href.endswith('.pdf') else []
            full_text = clean_text(item.get_text(strip=True))
            category = categorize_opportunity(title, full_text)

            return {
                'title': title,
                'organization': 'State of New Mexico',
                'description': full_text[:500] if full_text != title else None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': None,
                'category': category,
                'location': 'New Mexico',
                'source': self.source_name,
                'source_url': href,
                'opportunity_number': None,
                'posted_date': None,
                'document_urls': doc_urls,
                'opportunity_type': 'rfp',
            }
        except Exception as e:
            logger.warning(f"Error parsing NM content item: {e}")
            return None


def get_new_mexico_scrapers():
    return [NewMexicoPurchasingScraper()]


if __name__ == '__main__':
    scraper = NewMexicoPurchasingScraper()
    opps = scraper.scrape()
    print(f"Found {len(opps)} opportunities.")
    import pprint
    for o in opps[:3]:
        pprint.pprint(o)
