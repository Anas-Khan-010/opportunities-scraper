"""
Maryland Procurement scraper — eMaryland Marketplace Advantage (eMMA)

Source: https://emma.maryland.gov/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class MarylandEMMAScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("Maryland eMMA", "https://emma.maryland.gov/page.aspx/en/rfp/request_browse_public", "Maryland")

def get_maryland_scrapers():
    return [MarylandEMMAScraper()]
