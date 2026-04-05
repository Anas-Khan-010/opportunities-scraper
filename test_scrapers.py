#!/usr/bin/env python3
"""
Quick test script to verify all scrapers are properly configured
"""

import sys
from utils.logger import logger

def test_scrapers():
    """Test that all scrapers can be imported and initialized"""
    
    logger.info("Testing scraper imports...")
    
    scrapers_tested = 0
    scrapers_failed = 0
    
    # Test Federal Scrapers
    logger.info("\n=== Testing Federal Scrapers ===")
    try:
        from scrapers.grants_gov import GrantsGovScraper
        GrantsGovScraper()
        logger.info("✅ GrantsGovScraper")
        scrapers_tested += 1
    except Exception as e:
        logger.error(f"❌ GrantsGovScraper: {e}")
        scrapers_failed += 1
    
    try:
        from scrapers.sam_gov import SAMGovScraper
        SAMGovScraper()
        logger.info("✅ SAMGovScraper")
        scrapers_tested += 1
    except Exception as e:
        logger.error(f"❌ SAMGovScraper: {e}")
        scrapers_failed += 1
    
    # Test Foundation Scrapers
    logger.info("\n=== Testing Foundation Scrapers ===")
    try:
        from scrapers.foundation_scrapers import DukeResearchFundingScraper
        DukeResearchFundingScraper()
        logger.info("✅ DukeResearchFundingScraper")
        scrapers_tested += 1
    except Exception as e:
        logger.error(f"❌ DukeResearchFundingScraper: {e}")
        scrapers_failed += 1
    
    # Test State Scrapers
    logger.info("\n=== Testing State Scrapers ===")
    state_scrapers = [
        'CaliforniaScraper',
        'TexasScraper',
        'FloridaScraper',
        'NewYorkScraper',
        'PennsylvaniaScraper',
        'IllinoisScraper',
        'OhioScraper',
        'GeorgiaScraper',
        'NorthCarolinaScraper',
        'MichiganScraper'
    ]
    
    for scraper_name in state_scrapers:
        try:
            from scrapers import state_scrapers as ss
            scraper_class = getattr(ss, scraper_name)
            scraper_class()
            logger.info(f"✅ {scraper_name}")
            scrapers_tested += 1
        except Exception as e:
            logger.error(f"❌ {scraper_name}: {e}")
            scrapers_failed += 1
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SCRAPER TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Scrapers Tested: {scrapers_tested + scrapers_failed}")
    logger.info(f"✅ Passed: {scrapers_tested}")
    logger.info(f"❌ Failed: {scrapers_failed}")
    logger.info("=" * 60)
    
    if scrapers_failed == 0:
        logger.info("🎉 All scrapers initialized successfully!")
        return 0
    else:
        logger.warning(f"⚠️  {scrapers_failed} scraper(s) failed to initialize")
        return 1

if __name__ == "__main__":
    sys.exit(test_scrapers())
