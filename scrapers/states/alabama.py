"""
Alabama Procurement scraper — AlabamaBuys (Ivalua platform)

Source: https://alabamabuys.gov/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class AlabamaBuysScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("AlabamaBuys", "https://alabamabuys.gov/page.aspx/en/rfp/request_browse_public", "Alabama")

def get_alabama_scrapers():
    return [AlabamaBuysScraper()]
