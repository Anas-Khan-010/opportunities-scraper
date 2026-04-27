#!/usr/bin/env python3
import sys
import json
import re
from scrapers.states import get_all_state_scrapers
from utils.logger import logger

def evaluate_opportunity(opp):
    """
    Evaluates the quality of a single opportunity object.
    Returns a dictionary of scores and flags.
    """
    results = {
        'title_quality': 'OK',
        'fields_present': 0,
        'total_fields': 11,
        'missing': [],
        'has_docs': False,
        'has_funding': False
    }
    
    fields = [
        'title', 'organization', 'description', 'eligibility', 
        'funding_amount', 'deadline', 'category', 'location', 
        'source', 'source_url', 'opportunity_number'
    ]
    
    for f in fields:
        val = opp.get(f)
        if val and str(val).strip() and str(val).lower() not in ['not specified', 'n/a', 'none', '[]']:
            results['fields_present'] += 1
        else:
            results['missing'].append(f)
            
    # Title quality check
    title = opp.get('title', '')
    if not title or len(title) < 10:
        results['title_quality'] = 'TOO_SHORT'
    elif any(word in title.lower() for word in ['click here', 'contact us', 'navigat', 'menu', 'search']):
        results['title_quality'] = 'LOW_QUALITY'
        
    results['has_docs'] = bool(opp.get('document_urls'))
    results['has_funding'] = bool(opp.get('funding_amount'))
    
    return results

def run_diagnostic(state_name=None, enrich=False):
    all_scrapers = get_all_state_scrapers()
    
    if state_name:
        target_scrapers = [s for s in all_scrapers if state_name.lower() in s.source_name.lower()]
        if not target_scrapers:
            print(f"No scrapers found for state: {state_name}")
            return
    else:
        target_scrapers = all_scrapers

    # Import enricher if needed
    enricher = None
    from scrapers.base_scraper import SeleniumDriverManager
    if enrich:
        from scrapers.enricher import OpportunityEnricher
        enricher = OpportunityEnricher(limit=0) # Limit 0 means it won't pull from DB, we'll call _enrich_single manually

    report = {}

    for scraper in target_scrapers:
        print(f"\n>>> Testing Scraper: {scraper.source_name}")
        try:
            # Set a low limit for diagnostic
            scraper._max_new = 3
            opps = scraper.scrape()
            
            # --- Network Evasion Retry ---
            if not opps:
                print(f"  [!] No opportunities found. Attempting proxy fallback...")
                # Force proxy in the driver manager
                from scrapers.base_scraper import SeleniumDriverManager
                SeleniumDriverManager.get_driver(use_proxy=True, force_new=True)
                opps = scraper.scrape()
            
            if not opps:
                print(f"  [!] No opportunities returned even with proxy.")
                report[scraper.source_name] = {'status': 'EMPTY', 'count': 0}
                continue
            
            if enrich:
                print(f"  [+] Enriching data (fetching detail pages/PDFs)...")
                # Use Selenium if needed for SPAs
                driver = SeleniumDriverManager.get_driver()
                
                for opp in opps:
                    url = opp['source_url']
                    text = ""
                    new_docs = []
                    
                    if url and url.lower().endswith('.pdf'):
                        from utils.pdf_parser import download_and_extract_pdf_text
                        text = download_and_extract_pdf_text(url)
                        new_docs = [url]
                    elif url:
                        try:
                            # Use requests first for speed, then selenium if it looks like SPA
                            import requests
                            from bs4 import BeautifulSoup
                            resp = requests.get(url, timeout=5)
                            if resp.status_code == 200 and len(resp.text) > 2000:
                                s = BeautifulSoup(resp.text, 'html.parser')
                                # If it looks like a SPA loader, use selenium
                                if 'app-root' in resp.text or 'loading...' in resp.text.lower():
                                    raise Exception("SPA detected")
                                
                                text = s.get_text(separator=' ')
                                for a in s.find_all('a', href=True):
                                    if a['href'].lower().endswith('.pdf'):
                                        new_docs.append(urljoin(url, a['href']))
                            else:
                                raise Exception("Empty or SPA")
                        except:
                            if driver:
                                try:
                                    driver.get(url)
                                    time.sleep(5)
                                    text = driver.page_source
                                    s = BeautifulSoup(text, 'html.parser')
                                    text = s.get_text(separator=' ')
                                    for a in s.find_all('a', href=True):
                                        if a['href'].lower().endswith('.pdf'):
                                            new_docs.append(urljoin(url, a['href']))
                                except: pass
                    
                    if text:
                        from utils.pdf_parser import heuristically_extract_fields
                        ext = heuristically_extract_fields(text)
                        for k in ['funding_amount', 'eligibility', 'description']:
                            if not opp.get(k) and ext.get(k):
                                opp[k] = ext[k]
                        opp['document_urls'] = list(set((opp.get('document_urls') or []) + new_docs))

            print(f"  [+] Results ready for evaluation.")
            
            scores = []
            for opp in opps:
                scores.append(evaluate_opportunity(opp))
                
            avg_coverage = sum(s['fields_present'] for s in scores) / (len(scores) * scores[0]['total_fields']) * 100
            doc_rate = sum(1 for s in scores if s['has_docs']) / len(scores) * 100
            funding_rate = sum(1 for s in scores if s['has_funding']) / len(scores) * 100
            hq_titles = sum(1 for s in scores if s['title_quality'] == 'OK') / len(scores) * 100
            
            print(f"  [REPORT] Data Coverage: {avg_coverage:.1f}%")
            print(f"  [REPORT] Doc URL Presence: {doc_rate:.1f}%")
            print(f"  [REPORT] Funding Amount Presence: {funding_rate:.1f}%")
            print(f"  [REPORT] High Quality Titles: {hq_titles:.1f}%")
            
            missing_stats = {}
            for s in scores:
                for m in s['missing']:
                    missing_stats[m] = missing_stats.get(m, 0) + 1
            
            if missing_stats:
                print(f"  [REPORT] Frequently Missing: {dict(sorted(missing_stats.items(), key=lambda x: x[1], reverse=True))}")

            report[scraper.source_name] = {
                'status': 'SUCCESS',
                'count': len(opps),
                'coverage': avg_coverage,
                'doc_rate': doc_rate,
                'funding_rate': funding_rate,
                'hq_titles': hq_titles
            }
            
        except Exception as e:
            print(f"  [ERROR] Scraper failed: {e}")
            report[scraper.source_name] = {'status': 'FAILED', 'error': str(e)}

    return report

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('state', nargs='?', default=None)
    parser.add_argument('--enrich', action='store_true')
    args = parser.parse_args()
    
    run_diagnostic(args.state, args.enrich)
