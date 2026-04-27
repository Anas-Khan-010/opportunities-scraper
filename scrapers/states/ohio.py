"""
Ohio Procurement scraper — OhioBuys (Ivalua platform)

Source: https://ohiobuys.ohio.gov/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class OhioBuysScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("OhioBuys", "https://ohiobuys.ohio.gov/page.aspx/en/rfp/request_browse_public", "Ohio")

def get_ohio_scrapers():
    return [OhioBuysScraper()]
