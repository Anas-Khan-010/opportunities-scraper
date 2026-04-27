"""
Oregon Procurement scraper — OregonBuys (Ivalua platform)

Source: https://oregonbuys.gov/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class OregonBuysScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("OregonBuys", "https://oregonbuys.gov/page.aspx/en/rfp/request_browse_public", "Oregon")

def get_oregon_scrapers():
    return [OregonBuysScraper()]
