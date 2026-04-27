#!/usr/bin/env python3
"""
Final Testing Orchestrator
Runs all 50+ scrapers with a limit of 20 opportunities per source.
"""

import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db import db
from scrapers.grants_gov import GrantsGovScraper
from scrapers.sam_gov import SAMGovScraper
from scrapers.states import get_all_state_scrapers
from scrapers.base_scraper import cleanup_selenium
from utils.logger import logger

class FinalTestOrchestrator:
    def __init__(self, limit=20):
        self.limit = limit
        self.scrapers = []
        self.results = {}

    def register_scrapers(self):
        logger.info("Registering all scrapers for final testing...")
        
        # Federal
        self.scrapers.append(GrantsGovScraper())
        self.scrapers.append(SAMGovScraper())
        
        # All 50 States
        self.scrapers.extend(get_all_state_scrapers())
        
        logger.info(f"Registered {len(self.scrapers)} scrapers.")

    def run(self):
        logger.info("=" * 80)
        logger.info(f"STARTING FINAL TEST SWEEP (LIMIT: {self.limit} PER SOURCE)")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        for scraper in self.scrapers:
            try:
                logger.info(f"\n--- Running: {scraper.source_name} ---")
                
                # Set the limit
                scraper._max_new = self.limit
                
                # Run scrape
                start_time = time.time()
                opportunities = scraper.scrape()
                duration = time.time() - start_time
                
                self.results[scraper.source_name] = {
                    'count': len(opportunities),
                    'new': scraper._new_count,
                    'dups': scraper._dup_count,
                    'duration': round(duration, 2),
                    'status': 'SUCCESS' if len(opportunities) > 0 else 'EMPTY'
                }
                
                logger.info(f"    Finished: {len(opportunities)} found | {scraper._new_count} new | {round(duration, 2)}s")

            except Exception as e:
                logger.error(f"    FAILED: {scraper.source_name} | Error: {e}")
                self.results[scraper.source_name] = {'status': 'FAILED', 'error': str(e)}

        self.print_report()

    def print_report(self):
        logger.info("\n" + "=" * 80)
        logger.info("FINAL TEST RESULTS SUMMARY")
        logger.info("=" * 80)
        
        success_count = sum(1 for r in self.results.values() if r.get('status') == 'SUCCESS')
        failed_count = sum(1 for r in self.results.values() if r.get('status') == 'FAILED')
        empty_count = sum(1 for r in self.results.values() if r.get('status') == 'EMPTY')
        
        logger.info(f"Total Scrapers Run: {len(self.results)}")
        logger.info(f"Success: {success_count}")
        logger.info(f"Empty:   {empty_count}")
        logger.info(f"Failed:  {failed_count}")
        
        logger.info("\nDetailed Report (Failures/Empty first):")
        for name, res in sorted(self.results.items(), key=lambda x: x[1].get('status')):
            status = res.get('status')
            if status != 'SUCCESS':
                logger.info(f"[{status}] {name}")
                if status == 'FAILED':
                    logger.info(f"    Error: {res.get('error')}")

if __name__ == "__main__":
    try:
        orchestrator = FinalTestOrchestrator(limit=20)
        orchestrator.register_scrapers()
        orchestrator.run()
    finally:
        cleanup_selenium()
