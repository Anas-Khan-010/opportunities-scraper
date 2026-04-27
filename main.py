#!/usr/bin/env python3
"""
US Government Opportunities Scraping System

Main orchestrator — runs all scrapers and stores data in Supabase.
Scrapes grants, contracts, and RFPs from official government sources
across federal agencies and US states.

Scraper pipeline:
  - Grants.gov              Federal grants (API + Selenium detail pages)
  - SAM.gov                 Federal contracts (API, rate-limited)
  - Alaska DCRA Grants      AK grants (ArcGIS Feature Service API)
  - California Grants       State grants (CKAN open-data API)
  - Delaware MMP Bids       DE bids/RFPs (Selenium SPA + PDF enrichment)
  - Illinois CSFA           IL grant programs (HTML + detail pages)
  - Michigan Funding Hub    MI grants (Selenium SPA)
  - Minnesota Grants        MN grant programs (JSON search API)
  - Montana eMACS           MT bids/RFPs (Selenium Jaggaer + PDF enrichment)
  - New Hampshire Proc.     NH bids (Selenium + PDF enrichment)
  - New Jersey DHS          NJ RFPs/RFAs/RFIs (Selenium + PDF enrichment)
  - NY Grants Gateway       New York grants (PeopleSoft / Selenium)
  - North Dakota Grants     ND grants (WebGrants HTML)
  - Texas ESBD              TX grants, solicitations, pre-solicitations (Selenium)
  - NC eVP                  North Carolina solicitations (Selenium)

Each opportunity is written to the database in real-time as it is scraped,
so no data is lost if the process is interrupted.
"""

import sys
from datetime import datetime
from database.db import db
from utils.logger import logger
from scrapers.grants_gov import GrantsGovScraper
from scrapers.sam_gov import SAMGovScraper
from scrapers.states import get_all_state_scrapers
from scrapers.base_scraper import cleanup_selenium


class ScraperOrchestrator:
    """Orchestrates all scrapers and manages data pipeline"""

    def __init__(self):
        self.scrapers = []
        self.stats = {
            'total_scraped': 0,
            'total_inserted': 0,
            'total_duplicates': 0,
            'total_errors': 0,
        }

    def register_scrapers(self):
        """Register all scrapers in the defined run order."""
        logger.info("Registering scrapers...")

        # 1 ── Grants.gov (federal grants) ─────────────────────────────
        self.scrapers.append(GrantsGovScraper())

        # 2 ── SAM.gov (federal contracts) ─────────────────────────────
        self.scrapers.append(SAMGovScraper())

        # 3 ── State scrapers (AK, CA, DE, IL, MI, MN, MT, NH, NJ, NY, ND, TX, NC)
        self.scrapers.extend(get_all_state_scrapers())

        logger.info(f"Registered {len(self.scrapers)} scrapers")

    def run_scrapers(self):
        """Run all registered scrapers"""
        logger.info("=" * 80)
        logger.info("Starting scraping session")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        for scraper in self.scrapers:
            try:
                logger.info(f"\n{'=' * 60}")
                logger.info(f"Running scraper: {scraper.source_name}")
                logger.info(f"{'=' * 60}")

                opportunities = scraper.scrape()
                self.stats['total_scraped'] += len(opportunities)
                self.stats['total_inserted'] += scraper._new_count
                self.stats['total_duplicates'] += scraper._dup_count

            except KeyboardInterrupt:
                logger.warning(
                    f"\nUser interruption during {scraper.source_name}. "
                    "Data scraped so far is already saved to the database."
                )
                self.stats['total_scraped'] += len(getattr(scraper, 'opportunities', []))
                self.stats['total_inserted'] += getattr(scraper, '_new_count', 0)
                self.stats['total_duplicates'] += getattr(scraper, '_dup_count', 0)
                raise

            except Exception as e:
                logger.error(f"Error running scraper {scraper.source_name}: {e}")
                self.stats['total_scraped'] += len(getattr(scraper, 'opportunities', []))
                self.stats['total_inserted'] += getattr(scraper, '_new_count', 0)
                self.stats['total_duplicates'] += getattr(scraper, '_dup_count', 0)
                self.stats['total_errors'] += 1
                continue

    def print_summary(self):
        """Print scraping session summary"""
        logger.info("\n" + "=" * 80)
        logger.info("SCRAPING SESSION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total opportunities scraped: {self.stats['total_scraped']}")
        logger.info(f"New opportunities inserted:  {self.stats['total_inserted']}")
        logger.info(f"Duplicates skipped:          {self.stats['total_duplicates']}")
        logger.info(f"Errors encountered:          {self.stats['total_errors']}")

        db_stats = db.get_stats()
        if db_stats:
            logger.info("\nDATABASE STATISTICS")
            logger.info("-" * 80)
            logger.info(f"Total opportunities in database: {db_stats.get('total', 0)}")
            logger.info(f"Active opportunities (future deadline): {db_stats.get('active', 0)}")
            logger.info(f"Unique sources: {db_stats.get('sources', 0)}")

        logger.info("=" * 80)
        logger.info(f"Session completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80 + "\n")


def main():
    """Main entry point"""
    try:
        logger.info("Initializing RFP and Grants Scraping System...")

        logger.info("Setting up database...")
        db.create_tables()

        orchestrator = ScraperOrchestrator()
        orchestrator.register_scrapers()
        orchestrator.run_scrapers()
        orchestrator.print_summary()

        cleanup_selenium()

        logger.info("System shutdown complete")
        return 0

    except KeyboardInterrupt:
        logger.warning("\nScraping interrupted by user")
        cleanup_selenium()
        return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        cleanup_selenium()
        return 1


if __name__ == "__main__":
    sys.exit(main())
