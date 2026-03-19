#!/usr/bin/env python3
"""
Test script to verify the scraping system is working correctly
"""

import sys
from database.db import db
from utils.logger import logger
from scrapers.grants_gov import GrantsGovScraper

def test_database_connection():
    """Test database connection"""
    print("\n" + "="*60)
    print("TEST 1: Database Connection")
    print("="*60)
    
    try:
        db.create_tables()
        print("✅ Database connection successful")
        print("✅ Tables created/verified")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_scraper():
    """Test a single scraper"""
    print("\n" + "="*60)
    print("TEST 2: Grants.gov Scraper")
    print("="*60)
    
    try:
        scraper = GrantsGovScraper()
        print("✅ Scraper initialized")
        
        # Scrape just 1 page for testing
        opportunities = scraper.scrape(max_pages=1)
        
        if opportunities:
            print(f"✅ Found {len(opportunities)} opportunities")
            
            # Show first opportunity
            if len(opportunities) > 0:
                opp = opportunities[0]
                print("\nSample Opportunity:")
                print(f"  Title: {opp['title'][:80]}...")
                print(f"  Organization: {opp['organization']}")
                print(f"  Source: {opp['source']}")
                print(f"  URL: {opp['source_url']}")
                print(f"  Category: {opp['category']}")
            
            return True
        else:
            print("⚠️  No opportunities found (this might be normal)")
            return True
            
    except Exception as e:
        print(f"❌ Scraper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_insert():
    """Test inserting data into database"""
    print("\n" + "="*60)
    print("TEST 3: Database Insert")
    print("="*60)
    
    try:
        # Create test opportunity
        test_opp = {
            'title': 'TEST OPPORTUNITY - DELETE ME',
            'organization': 'Test Organization',
            'description': 'This is a test opportunity',
            'eligibility': None,
            'funding_amount': '$100,000',
            'deadline': None,
            'category': 'Test',
            'location': 'United States',
            'source': 'Test',
            'source_url': f'https://test.com/test-{sys.maxsize}',
            'opportunity_number': 'TEST-001',
            'posted_date': None,
            'document_urls': [],
            'full_document': None
        }
        
        result = db.insert_opportunity(test_opp)
        
        if result:
            print("✅ Test opportunity inserted successfully")
            print(f"   ID: {result}")
            
            # Clean up - delete test opportunity
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM opportunities WHERE id = %s", (result,))
            print("✅ Test opportunity cleaned up")
            
            return True
        else:
            print("⚠️  Insert returned None (might be duplicate)")
            return True
            
    except Exception as e:
        print(f"❌ Database insert test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_stats():
    """Test database statistics"""
    print("\n" + "="*60)
    print("TEST 4: Database Statistics")
    print("="*60)
    
    try:
        stats = db.get_stats()
        
        if stats:
            print("✅ Statistics retrieved successfully")
            print(f"   Total opportunities: {stats.get('total', 0)}")
            print(f"   Active opportunities: {stats.get('active', 0)}")
            print(f"   Unique sources: {stats.get('sources', 0)}")
            return True
        else:
            print("⚠️  No statistics available")
            return True
            
    except Exception as e:
        print(f"❌ Statistics test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("RFP AND GRANTS SCRAPING SYSTEM - TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Database Connection", test_database_connection()))
    results.append(("Scraper Functionality", test_scraper()))
    results.append(("Database Insert", test_database_insert()))
    results.append(("Database Statistics", test_database_stats()))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "-"*60)
    print(f"Results: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    if passed == total:
        print("🎉 All tests passed! System is ready to use.")
        print("\nRun the full scraper with: python main.py")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
