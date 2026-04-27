import sys
import logging
logging.basicConfig(level=logging.DEBUG)
from scrapers.states.arizona import ArizonaProcurementPortalScraper

scraper = ArizonaProcurementPortalScraper()
opps = scraper.scrape()
print(f"Found {len(opps)} opportunities.")
print(opps[:2])
