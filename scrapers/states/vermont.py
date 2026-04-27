"""
Vermont Procurement scraper — Business Registry (Ivalua platform)

Source: https://vermontbusinessregistry.com/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class VermontRegistryScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("Vermont Business Registry", "https://vermontbusinessregistry.com/page.aspx/en/rfp/request_browse_public", "Vermont")

def get_vermont_scrapers():
    return [VermontRegistryScraper()]
