"""
Fast per-scraper runner with DB upserts and summary report.

Run sequence (matches main.py):
  1. Grants.gov              (federal grants)
  2. SAM.gov                 (federal contracts)
  3. Duke Research Funding    (foundation grants)
  4. State grant scrapers    — supplementary (CA API)
  5. TGP grant scraper        (thegrantportal.com — all 50 states)
  6. Texas ESBD               (grants + solicitations + pre-solicitations)
  7. NC eVP                   (North Carolina solicitations)
  8. GovContracts RFP         (governmentcontracts.us — all 50 states)
  9. RFPMart                  (rfpmart.com — massive US RFP aggregator)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from database.db import Database
from utils.logger import logger

_INSERT_SQL = """
INSERT INTO opportunities (
    title, organization, description, eligibility, funding_amount,
    deadline, category, location, source, source_url, opportunity_number,
    posted_date, document_urls, opportunity_type
) VALUES (
    %(title)s, %(organization)s, %(description)s, %(eligibility)s, %(funding_amount)s,
    %(deadline)s, %(category)s, %(location)s, %(source)s, %(source_url)s, %(opportunity_number)s,
    %(posted_date)s, %(document_urls)s, %(opportunity_type)s
)
ON CONFLICT (source_url) DO UPDATE SET
    title = EXCLUDED.title,
    description = COALESCE(EXCLUDED.description, opportunities.description),
    deadline = COALESCE(EXCLUDED.deadline, opportunities.deadline),
    document_urls = CASE WHEN EXCLUDED.document_urls IS NOT NULL AND array_length(EXCLUDED.document_urls, 1) > 0
                         THEN EXCLUDED.document_urls ELSE opportunities.document_urls END,
    scraped_at = NOW()
"""


def batch_insert(db, opportunities):
    if not opportunities:
        return 0
    inserted = 0
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for opp in opportunities:
                try:
                    data = dict(opp)
                    data.setdefault('opportunity_type', None)
                    cursor.execute(_INSERT_SQL, data)
                    if cursor.rowcount and cursor.rowcount > 0:
                        inserted += 1
                except Exception as e:
                    logger.debug(f"Insert error: {e}")
    except Exception as e:
        logger.error(f"Batch insert error: {e}")
    return inserted


def run_single(scraper, db, label, idx, total):
    name = getattr(scraper, 'source_name', str(scraper))
    print(f'[{label} {idx}/{total}] {name}...', end='', flush=True)

    try:
        t0 = time.time()
        opps = scraper.scrape()
        elapsed = time.time() - t0

        count = len(opps) if opps else 0
        inserted = 0
        doc_count = 0
        if opps:
            inserted = batch_insert(db, opps)
            doc_count = sum(1 for o in opps if o.get('document_urls'))

        status = 'OK' if count > 0 else 'EMPTY'
        print(f' {status} ({count} found, {inserted} new, {doc_count} docs) [{elapsed:.0f}s]')
        return (name, status, count, inserted, doc_count)

    except Exception as e:
        print(f' ERROR: {str(e)[:60]}')
        return (name, 'ERROR', 0, 0, 0)


def main():
    db = Database()
    try:
        db.create_tables()
    except Exception:
        pass

    report_path = os.path.join(os.path.dirname(__file__), 'fast_report.txt')

    print('=' * 70)
    print('FAST RUN — Full Scraping Pipeline')
    print('=' * 70)

    all_results = []

    # ── Phase 1: Grants.gov (federal grants) ──────────────────────────
    print(f'\n{"─"*70}')
    print('Phase 1: Grants.gov (federal grants)')
    print(f'{"─"*70}')
    all_results.append(run_single(GrantsGovScraper(), db, 'FED', 1, 1))

    # ── Phase 2: SAM.gov (federal contracts) ──────────────────────────
    print(f'\n{"─"*70}')
    print('Phase 2: SAM.gov (federal contracts)')
    print(f'{"─"*70}')
    all_results.append(run_single(SAMGovScraper(), db, 'FED', 1, 1))

    # ── Phase 3: Foundation / research grants ─────────────────────────
    print(f'\n{"─"*70}')
    print('Phase 3: Duke Research Funding (foundation grants)')
    print(f'{"─"*70}')
    all_results.append(run_single(DukeResearchFundingScraper(), db, 'FOUND', 1, 1))

    # ── Phase 4: State grant scrapers — supplementary ─────────────────
    grant_scrapers = get_all_state_grant_scrapers()
    if grant_scrapers:
        print(f'\n{"─"*70}')
        print(f'Phase 4: Supplementary State Grant Scrapers ({len(grant_scrapers)})')
        print(f'{"─"*70}')
        for i, s in enumerate(grant_scrapers, 1):
            all_results.append(run_single(s, db, 'GRANT', i, len(grant_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 5: TGP Grant Scraper (all 50 states) ────────────────────
    tgp_scrapers = get_tgp_grant_scrapers()
    if tgp_scrapers:
        print(f'\n{"─"*70}')
        print('Phase 5: TGP Grant Scraper (thegrantportal.com — all 50 states)')
        print(f'{"─"*70}')
        for i, s in enumerate(tgp_scrapers, 1):
            all_results.append(run_single(s, db, 'TGP', i, len(tgp_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 6: Texas ESBD (grants + solicitations + pre-solicitations) ─
    tx_scrapers = get_texas_esbd_scrapers()
    if tx_scrapers:
        print(f'\n{"─"*70}')
        print('Phase 6: Texas ESBD (grants + solicitations + pre-solicitations)')
        print(f'{"─"*70}')
        for i, s in enumerate(tx_scrapers, 1):
            all_results.append(run_single(s, db, 'TX-ESBD', i, len(tx_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 7: NC eVP (North Carolina solicitations) ────────────────
    nc_scrapers = get_nc_evp_scrapers()
    if nc_scrapers:
        print(f'\n{"─"*70}')
        print('Phase 7: NC eVP (North Carolina solicitations)')
        print(f'{"─"*70}')
        for i, s in enumerate(nc_scrapers, 1):
            all_results.append(run_single(s, db, 'NC-eVP', i, len(nc_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 8: GovContracts RFP Scraper (all 50 states) ────────────
    gc_scrapers = get_govcontracts_rfp_scrapers()
    if gc_scrapers:
        print(f'\n{"─"*70}')
        print('Phase 8: GovContracts RFP Scraper (governmentcontracts.us — all 50 states)')
        print(f'{"─"*70}')
        for i, s in enumerate(gc_scrapers, 1):
            all_results.append(run_single(s, db, 'GC-RFP', i, len(gc_scrapers)))

    # ── Phase 9: RFPMart (massive US RFP aggregator) ────────────────
    rfp_scrapers = get_rfpmart_scrapers()
    if rfp_scrapers:
        print(f'\n{"─"*70}')
        print('Phase 9: RFPMart (rfpmart.com — massive US RFP aggregator)')
        print(f'{"─"*70}')
        for i, s in enumerate(rfp_scrapers, 1):
            all_results.append(run_single(s, db, 'RFPMART', i, len(rfp_scrapers)))

    # ── Summary ────────────────────────────────────────────────────────
    ok = sum(1 for r in all_results if r[1] == 'OK')
    empty = sum(1 for r in all_results if r[1] == 'EMPTY')
    errs = sum(1 for r in all_results if r[1] == 'ERROR')
    total_opps = sum(r[2] for r in all_results)
    total_ins = sum(r[3] for r in all_results)
    total_docs = sum(r[4] for r in all_results)

    print(f'\n{"="*70}')
    print('FINAL SUMMARY')
    print(f'{"="*70}')
    print(f'  Scrapers:       {ok} OK / {empty} EMPTY / {errs} ERROR  (total {len(all_results)})')
    print(f'  Opportunities:  {total_opps}')
    print(f'  DB upserts:     {total_ins}')
    print(f'  With doc URLs:  {total_docs}')

    with open(report_path, 'w') as f:
        f.write(f'{"="*80}\nFAST RUN REPORT\n{"="*80}\n\n')
        f.write(f'OK: {ok} | EMPTY: {empty} | ERROR: {errs} | Total: {len(all_results)}\n')
        f.write(f'Opportunities: {total_opps} | DB upserts: {total_ins} | With docs: {total_docs}\n\n')
        for name, status, count, ins, docs in all_results:
            f.write(f'  [{status:7s}] {name:50s} | {count:5d} found | {ins:5d} new | {docs:4d} docs\n')
        f.write('\nDone.\n')

    print(f'\nReport: {report_path}')


if __name__ == '__main__':
    main()
