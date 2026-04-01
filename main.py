#!/usr/bin/env python3
"""
RFP and Grants Scraping System
Main orchestrator script that runs all scrapers and stores data in Supabase
"""

import sys
from datetime import datetime
from database.db import db
from utils.logger import logger
from parsers.parser_utils import OpportunityEnricher

# Import federal scrapers
from scrapers.grants_gov import GrantsGovScraper
from scrapers.sam_gov import SAMGovScraper
from scrapers.foundation_scrapers import (
    GrantWatchScraper, 
    NIHGrantsScraper, 
    NSFGrantsScraper,
    GatesFoundationScraper,
    FordFoundationScraper,
    RWJFScraper,
    KelloggFoundationScraper,
    MacArthurFoundationScraper
)
from scrapers.state_scrapers import (
    CaliforniaScraper,
    TexasScraper,
    FloridaScraper,
    NewYorkScraper,
    PennsylvaniaScraper,
    IllinoisScraper,
    OhioScraper,
    GeorgiaScraper,
    NorthCarolinaScraper,
    MichiganScraper
)

class ScraperOrchestrator:
    """Orchestrates all scrapers and manages data pipeline"""
    
    def __init__(self):
        self.scrapers = []
        self.stats = {
            'total_scraped': 0,
            'total_inserted': 0,
            'total_duplicates': 0,
            'total_errors': 0
        }
    
    def register_scrapers(self):
        """Register all available scrapers"""
        logger.info("Registering scrapers...")
        
        # Federal sources (highest priority)
        self.scrapers.append(GrantsGovScraper())
        self.scrapers.append(SAMGovScraper())
        
        # Research grants
        self.scrapers.append(NIHGrantsScraper())
        self.scrapers.append(NSFGrantsScraper())
        
        # Foundation grants
        self.scrapers.append(GrantWatchScraper())
        self.scrapers.append(GatesFoundationScraper())
        self.scrapers.append(FordFoundationScraper())
        self.scrapers.append(RWJFScraper())
        self.scrapers.append(KelloggFoundationScraper())
        self.scrapers.append(MacArthurFoundationScraper())
        
        # Top 10 state sources
        self.scrapers.append(CaliforniaScraper())
        self.scrapers.append(TexasScraper())
        self.scrapers.append(FloridaScraper())
        self.scrapers.append(NewYorkScraper())
        self.scrapers.append(PennsylvaniaScraper())
        self.scrapers.append(IllinoisScraper())
        self.scrapers.append(OhioScraper())
        self.scrapers.append(GeorgiaScraper())
        self.scrapers.append(NorthCarolinaScraper())
        self.scrapers.append(MichiganScraper())
        
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
                
                # Run scraper
                opportunities = scraper.scrape()
                self.stats['total_scraped'] += len(opportunities)
                
                # Process and store opportunities
                self.process_opportunities(opportunities)
                
            except KeyboardInterrupt:
                logger.warning(f"\n⚠️ User interruption detected during {scraper.source_name} execution. Rescuing scraped data before shutdown...")
                if getattr(scraper, 'opportunities', None):
                    logger.info(f"Rescuing {len(scraper.opportunities)} pending opportunities...")
                    self.process_opportunities(scraper.opportunities)
                raise  # Re-raise to shutdown the overarching main() loop safely
                
            except Exception as e:
                logger.error(f"Error running scraper {scraper.source_name}: {e}")
                self.stats['total_errors'] += 1
                continue
    
    def process_opportunities(self, opportunities):
        """Process and store opportunities in database"""
        for opp in opportunities:
            try:
                # Validate opportunity
                if not OpportunityEnricher.validate_opportunity(opp):
                    logger.warning(f"Invalid opportunity: {opp.get('title', 'Unknown')}")
                    self.stats['total_errors'] += 1
                    continue
                
                # Check if already exists
                if db.opportunity_exists(opp['source_url']):
                    logger.debug(f"Duplicate: {opp['title']}")
                    self.stats['total_duplicates'] += 1
                    continue
                
                # Enrich with documents if available
                if opp.get('document_urls'):
                    opp = OpportunityEnricher.enrich_with_documents(
                        opp, 
                        opp['document_urls']
                    )
                
                # Insert into database
                result = db.insert_opportunity(opp)
                
                if result:
                    self.stats['total_inserted'] += 1
                else:
                    self.stats['total_duplicates'] += 1
                
            except Exception as e:
                logger.error(f"Error processing opportunity: {e}")
                self.stats['total_errors'] += 1
                continue
    
    def print_summary(self):
        """Print scraping session summary"""
        logger.info("\n" + "=" * 80)
        logger.info("SCRAPING SESSION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total opportunities scraped: {self.stats['total_scraped']}")
        logger.info(f"New opportunities inserted: {self.stats['total_inserted']}")
        logger.info(f"Duplicates skipped: {self.stats['total_duplicates']}")
        logger.info(f"Errors encountered: {self.stats['total_errors']}")
        
        # Get database stats
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
        
        # Initialize database
        logger.info("Setting up database...")
        db.create_tables()
        
        # Create orchestrator
        orchestrator = ScraperOrchestrator()
        
        # Register scrapers
        orchestrator.register_scrapers()
        
        # Run scrapers
        orchestrator.run_scrapers()
        
        # Print summary
        orchestrator.print_summary()
        
        logger.info("System shutdown complete")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\nScraping interrupted by user")
        return 1
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
