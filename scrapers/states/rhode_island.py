"""
Rhode Island Procurement scraper — Ocean State Procures (Ivalua platform)

Source: https://ridop.ri.gov/page.aspx/en/rfp/request_browse_public
"""
from scrapers.base_scraper import BaseIvaluaScraper

class RhodeIslandScraper(BaseIvaluaScraper):
    def __init__(self):
        super().__init__("Rhode Island OSP", "https://ridop.ri.gov/page.aspx/en/rfp/request_browse_public", "Rhode Island")

def get_rhode_island_scrapers():
    return [RhodeIslandScraper()]
