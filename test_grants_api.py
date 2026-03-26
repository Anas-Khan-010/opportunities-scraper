#!/usr/bin/env python3
import sys
import logging
from utils.logger import setup_logger

setup_logger()

from scrapers.grants_gov import GrantsGovScraper

if __name__ == "__main__":
    print("Testing Grants.gov scraper...")
    scraper = GrantsGovScraper()
    opps = scraper.scrape(keyword="health", max_pages=1)
    
    print(f"\nExtracted {len(opps)} opportunities.")
    if opps:
        print("\n--- Example Opportunity ---")
        for k, v in opps[0].items():
            print(f"{k}: {v}")
