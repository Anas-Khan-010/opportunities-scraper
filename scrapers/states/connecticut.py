"""
Connecticut Procurement scraper — CTsource Bid Board

Scrapes open solicitations from Connecticut's official CTsource
procurement portal bid board.

Source: https://portal.ct.gov/das/ctsource/bidboard
"""

import time
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class ConnecticutBidBoardScraper(BaseScraper):
    """Scrapes bid opportunities from CT CTsource Bid Board (WebProcure)."""

    # Direct URL to the State of Connecticut (customerid=51) portal to avoid iframe issues
    BID_BOARD_URL = "https://webprocure.proactiscloud.com/wp-web-public/en/#/bidboard/search?customerid=51"
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
            # WebProcure is an SPA and can be slow to initialize labels
            time.sleep(10)

            # Scroll to ensure items are rendered
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(3)

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # The platform uses a card-based layout
            cards = soup.select('.card')
            if not cards:
                # Fallback to internal divs if .card class missing
                cards = soup.select('div[class*="bid"], div[class*="solicitation"]')

            logger.info(f"  Found {len(cards)} possible bid cards on CT board")

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

            if not title:
                return None

            # Detail URL
            href = link_el['href']
            if href.startswith('#'):
                source_url = f"{self.BASE_URL}{href}"
            else:
                source_url = href

            # Organization - usually marked with a building icon and at the bottom
            # Look for the last span/div in the card content which is typically the agency
            content = card.select_one('.card-content')
            org = "State of Connecticut"
            if content:
                # Select the text that has an icon next to it or is at the end
                org_el = content.select_one('i.material-icons + span') or content.find_all('span')[-1]
                if org_el:
                    org = clean_text(org_el.get_text(strip=True))

            # Deadline - Look for "End Date:" text
            deadline = None
            date_spans = card.find_all('span')
            for i, span in enumerate(date_spans):
                text = span.get_text().lower()
                if 'end date' in text and i + 1 < len(date_spans):
                    deadline_str = clean_text(date_spans[i+1].get_text(strip=True))
                    deadline = parse_date(deadline_str)
                    break

            category = categorize_opportunity(title, "")

            return {
                'title': title,
                'organization': org if org else 'State of Connecticut',
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
