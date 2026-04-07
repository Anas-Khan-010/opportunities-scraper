#!/usr/bin/env python3
"""
US Government Opportunities Scraping System

Main orchestrator — runs all scrapers and stores data in Supabase.
Targets 1,000,000+ grants, contracts, and RFPs across all 50 US states,
federal agencies, and research foundations.

Scraper pipeline:
  - Grants.gov              Federal grants (API + Selenium detail pages)
  - SAM.gov                 Federal contracts (API, rate-limited)
  - Duke Research Funding   Foundation / research grants (Selenium)
  - California Grants       State grants (CKAN open-data API)
  - The Grant Portal        State grants across all 50 states (Selenium)
  - Texas ESBD              TX grants, solicitations, pre-solicitations (Selenium)
  - NC eVP                  North Carolina solicitations (Selenium)
  - GovernmentContracts.us  State & local RFPs across all 50 states (HTML)
  - RFPMart                 Federal + state RFPs — largest source (HTML)

Each opportunity is written to the database in real-time as it is scraped,
so no data is lost if the process is interrupted.
"""

import sys
from datetime import datetime
from database.db import db
from utils.logger import logger
from scrapers.grants_gov import GrantsGovScraper
from scrapers.sam_gov import SAMGovScraper
from scrapers.foundation_scrapers import DukeResearchFundingScraper
from scrapers.state_grant_scrapers import get_all_state_grant_scrapers
from scrapers.tgp_grant_scraper import get_tgp_grant_scrapers
from scrapers.texas_esbd_scraper import get_texas_esbd_scrapers
from scrapers.nc_evp_scraper import get_nc_evp_scrapers
from scrapers.govcontracts_rfp_scraper import get_govcontracts_rfp_scrapers
from scrapers.rfpmart_scraper import get_rfpmart_scrapers
from scrapers.state_scrapers import cleanup_state_scrapers


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

        # 3 ── Foundation / research grants ────────────────────────────
        self.scrapers.append(DukeResearchFundingScraper())

        # 4 ── State grants — supplementary (CA API) ──────────────────
        self.scrapers.extend(get_all_state_grant_scrapers())

        # 5 ── TGP grants (thegrantportal.com — all 50 states) ────────
        self.scrapers.extend(get_tgp_grant_scrapers())

        # 6 ── Texas ESBD (grants + solicitations + pre-solicitations) ─
        self.scrapers.extend(get_texas_esbd_scrapers())

        # 7 ── NC eVP (North Carolina solicitations) ──────────────────
        self.scrapers.extend(get_nc_evp_scrapers())

        # 8 ── GovContracts RFPs (governmentcontracts.us — all 50) ────
        self.scrapers.extend(get_govcontracts_rfp_scrapers())

        # 9 ── RFPMart (rfpmart.com — massive US RFP aggregator) ────
        self.scrapers.extend(get_rfpmart_scrapers())

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

        cleanup_state_scrapers()

        logger.info("System shutdown complete")
        return 0

    except KeyboardInterrupt:
        logger.warning("\nScraping interrupted by user")
        cleanup_state_scrapers()
        return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        cleanup_state_scrapers()
        return 1


if __name__ == "__main__":
    sys.exit(main())
