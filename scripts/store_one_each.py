"""
Run every scraper source, store exactly 1 record from each into Supabase.
Uses minimal page/state limits so each source finishes quickly.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import Database
from utils.logger import logger

db = Database()
try:
    db.create_tables()
except Exception:
    pass

results = []


def insert_one(opp, label):
    data = dict(opp)
    data.setdefault('opportunity_type', None)
    try:
        result = db.insert_opportunity(data)
        ok = result is not None
    except Exception as e:
        logger.debug(f"Insert error: {e}")
        ok = False
    status = 'STORED' if ok else 'DUPLICATE'
    title = opp.get('title', '?')[:55]
    otype = opp.get('opportunity_type', '?')
    print(f'  {status} — "{title}" [{otype}]')
    results.append((label, status, title))


def run_source(label, fn):
    print(f'\n{"─"*60}')
    print(f'  {label}')
    print(f'{"─"*60}')
    try:
        opps = fn()
    except KeyboardInterrupt:
        print('  SKIPPED (Ctrl+C)')
        results.append((label, 'SKIPPED', ''))
        return
    except Exception as e:
        print(f'  ERROR: {e}')
        results.append((label, 'ERROR', str(e)[:80]))
        return
    if not opps:
        print('  EMPTY — 0 results')
        results.append((label, 'EMPTY', ''))
        return
    insert_one(opps[0], label)


def main():
    print('=' * 60)
    print('  Storing 1 record per source into Supabase')
    print('=' * 60)

    # ── 1. Grants.gov (1 page) ──────────────────────────────────
    from scrapers.grants_gov import GrantsGovScraper
    run_source('Grants.gov', lambda: GrantsGovScraper().scrape(max_pages=1))

    # ── 2. SAM.gov (1 page, override delay to 0 for quick test) ─
    import scrapers.sam_gov as sam_mod
    from scrapers.sam_gov import SAMGovScraper
    from config.settings import config
    orig_delay = config.SAM_GOV_OPP_DELAY
    orig_max_req = config.SAM_GOV_MAX_REQUESTS
    config.SAM_GOV_OPP_DELAY = 2
    config.SAM_GOV_MAX_REQUESTS = 1
    run_source('SAM.gov', lambda: SAMGovScraper().scrape(max_pages=1))
    config.SAM_GOV_OPP_DELAY = orig_delay
    config.SAM_GOV_MAX_REQUESTS = orig_max_req

    # ── 3. Duke Research ────────────────────────────────────────
    from scrapers.foundation_scrapers import DukeResearchFundingScraper
    run_source('Duke Research', lambda: DukeResearchFundingScraper().scrape(max_pages=1, max_opportunities=1))

    # ── 4. State grant scrapers (CA API) ────────────────────────
    from scrapers.state_grant_scrapers import get_all_state_grant_scrapers
    from scrapers.state_scrapers import cleanup_state_scrapers
    for scraper in get_all_state_grant_scrapers():
        run_source(scraper.source_name, scraper.scrape)

    # ── 5. TGP Grants (1 state, 1 page) ────────────────────────
    import scrapers.tgp_grant_scraper as tgp_mod
    from scrapers.tgp_grant_scraper import TGPGrantScraper
    orig_ids = dict(tgp_mod.TGP_STATE_IDS)
    orig_pages = tgp_mod.MAX_PAGES_PER_STATE
    tgp_mod.TGP_STATE_IDS = {7: 'Alabama'}
    tgp_mod.MAX_PAGES_PER_STATE = 1
    run_source('TGP Grants (Alabama)', lambda: TGPGrantScraper().scrape())
    tgp_mod.TGP_STATE_IDS = orig_ids
    tgp_mod.MAX_PAGES_PER_STATE = orig_pages
    cleanup_state_scrapers()

    # ── 6. Texas ESBD (1 page per section) ──────────────────────
    import scrapers.texas_esbd_scraper as tx_mod
    from scrapers.texas_esbd_scraper import TexasESBDScraper
    orig_sections = list(tx_mod.ESBD_SECTIONS)
    tx_mod.ESBD_SECTIONS = [dict(s, max_pages=1) for s in orig_sections]
    run_source('Texas ESBD (1pg each)', lambda: TexasESBDScraper().scrape())
    tx_mod.ESBD_SECTIONS = orig_sections
    cleanup_state_scrapers()

    # ── 7. NC eVP (1 page) ─────────────────────────────────────
    import scrapers.nc_evp_scraper as nc_mod
    from scrapers.nc_evp_scraper import NCeVPScraper
    orig_max = nc_mod.MAX_PAGES
    nc_mod.MAX_PAGES = 1
    run_source('NC eVP (1 page)', lambda: NCeVPScraper().scrape())
    nc_mod.MAX_PAGES = orig_max
    cleanup_state_scrapers()

    # ── 8. GovContracts RFP (1 state, 1 page) ──────────────────
    import scrapers.govcontracts_rfp_scraper as gc_mod
    from scrapers.govcontracts_rfp_scraper import GovContractsRFPScraper
    orig_st = dict(gc_mod.STATES)
    orig_gcp = gc_mod.MAX_PAGES_PER_STATE
    gc_mod.STATES = {'NY': 'New York'}
    gc_mod.MAX_PAGES_PER_STATE = 1
    run_source('GovContracts RFP (NY)', lambda: GovContractsRFPScraper().scrape())
    gc_mod.STATES = orig_st
    gc_mod.MAX_PAGES_PER_STATE = orig_gcp

    # ── 9. RFPMart (1 page only) ─────────────────────────────
    import scrapers.rfpmart_scraper as rfp_mod
    from scrapers.rfpmart_scraper import RFPMartScraper
    orig_rfp_pages = rfp_mod.MAX_PAGES
    rfp_mod.MAX_PAGES = 1
    run_source('RFPMart (1 page)', lambda: RFPMartScraper().scrape())
    rfp_mod.MAX_PAGES = orig_rfp_pages

    # ── Summary ─────────────────────────────────────────────────
    print('\n' + '=' * 60)
    print('  SUMMARY')
    print('=' * 60)
    for label, status, title in results:
        print(f'  {status:18s}  {label}')
    stored = sum(1 for _, s, _ in results if s == 'STORED')
    dupes = sum(1 for _, s, _ in results if s == 'DUPLICATE')
    total = len(results)
    print(f'\n  New: {stored} | Duplicate: {dupes} | Total sources: {total}')
    print('  Check Supabase for the new rows.')
    print('=' * 60)


if __name__ == '__main__':
    main()
