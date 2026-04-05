"""
Fast per-scraper runner — relies on Selenium built-in timeouts, no SIGALRM.

Execution order:
  1. TGP Grant Scraper        (primary grants — all 50 states via thegrantportal.com)
  2. Supplementary Grants     (CA API, NC/VA/PA/IN HTML — verified extra sources)
  3. GovContracts RFP Scraper (primary RFPs  — all 50 states via governmentcontracts.us)
  4. Supplementary RFPs       (individual state procurement portals — Selenium)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.tgp_grant_scraper import get_tgp_grant_scrapers
from scrapers.state_grant_scrapers import get_all_state_grant_scrapers
from scrapers.govcontracts_rfp_scraper import get_govcontracts_rfp_scrapers
from scrapers.state_rfp_scrapers import get_all_state_rfp_scrapers
from scrapers.state_scrapers import cleanup_state_scrapers, StateSeleniumScraper
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
                    data.pop('full_document', None)
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
        print(f' ERROR: {str(e)[:50]}')
        return (name, 'ERROR', 0, 0, 0)


def main():
    db = Database()
    try:
        db.create_tables()
    except Exception:
        pass

    report_path = os.path.join(os.path.dirname(__file__), 'fast_report.txt')

    print('=' * 70)
    print('FAST RUN — Grants (TGP + supp) & RFPs (GovContracts + supp)')
    print('=' * 70)

    # ── Phase 1: TGP Grant Scraper (primary — all 50 states) ──────────
    tgp_scrapers = get_tgp_grant_scrapers()
    tgp_results = []
    if tgp_scrapers:
        print(f'\n{"─"*70}')
        print(f'Phase 1: TGP Grant Scraper (primary — all 50 states)')
        print(f'{"─"*70}')
        for i, s in enumerate(tgp_scrapers, 1):
            tgp_results.append(run_single(s, db, 'TGP', i, len(tgp_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 2: Supplementary state grant scrapers ────────────────────
    grant_scrapers = get_all_state_grant_scrapers()
    grant_results = []
    if grant_scrapers:
        print(f'\n{"─"*70}')
        print(f'Phase 2: Supplementary Grant Scrapers ({len(grant_scrapers)} verified sources)')
        print(f'{"─"*70}')
        for i, s in enumerate(grant_scrapers, 1):
            grant_results.append(run_single(s, db, 'GRANT', i, len(grant_scrapers)))
        cleanup_state_scrapers()

    # ── Phase 3: GovContracts RFP Scraper (primary — all 50 states) ───
    gc_scrapers = get_govcontracts_rfp_scrapers()
    gc_results = []
    if gc_scrapers:
        print(f'\n{"─"*70}')
        print(f'Phase 3: GovContracts RFP Scraper (primary — all 50 states)')
        print(f'{"─"*70}')
        for i, s in enumerate(gc_scrapers, 1):
            gc_results.append(run_single(s, db, 'GC-RFP', i, len(gc_scrapers)))

    # ── Phase 4: Supplementary state RFP / procurement scrapers ───────
    rfp_scrapers = get_all_state_rfp_scrapers()
    rfp_results = []
    selenium_count = 0
    if rfp_scrapers:
        print(f'\n{"─"*70}')
        print(f'Phase 4: Supplementary State RFP Scrapers ({len(rfp_scrapers)} states)')
        print(f'{"─"*70}')
        for i, s in enumerate(rfp_scrapers, 1):
            if isinstance(s, StateSeleniumScraper):
                selenium_count += 1
                if selenium_count > 0 and selenium_count % 12 == 0:
                    cleanup_state_scrapers()
            rfp_results.append(run_single(s, db, 'RFP', i, len(rfp_scrapers)))
        cleanup_state_scrapers()

    # ── Summary ────────────────────────────────────────────────────────
    all_results = tgp_results + grant_results + gc_results + rfp_results
    ok = sum(1 for r in all_results if r[1] == 'OK')
    empty = sum(1 for r in all_results if r[1] == 'EMPTY')
    errs = sum(1 for r in all_results if r[1] == 'ERROR')
    total_opps = sum(r[2] for r in all_results)
    total_ins = sum(r[3] for r in all_results)
    total_docs = sum(r[4] for r in all_results)

    tgp_ok = sum(1 for r in tgp_results if r[1] == 'OK')
    tgp_opps = sum(r[2] for r in tgp_results)
    g_ok = sum(1 for r in grant_results if r[1] == 'OK')
    g_total = len(grant_results)
    gc_ok = sum(1 for r in gc_results if r[1] == 'OK')
    gc_opps = sum(r[2] for r in gc_results)
    r_ok = sum(1 for r in rfp_results if r[1] == 'OK')
    r_total = len(rfp_results)

    print(f'\n{"="*70}')
    print('FINAL SUMMARY')
    print(f'{"="*70}')
    print(f'  OK:             {ok}/{len(all_results)}')
    print(f'  EMPTY:          {empty}')
    print(f'  ERROR:          {errs}')
    print(f'  Opportunities:  {total_opps}')
    print(f'  DB upserts:     {total_ins}')
    print(f'  With doc URLs:  {total_docs}')
    print(f'  TGP grants:     {tgp_opps} ({"OK" if tgp_ok else "FAIL"})')
    print(f'  Supplementary:  {g_ok}/{g_total} OK')
    print(f'  GovContracts:   {gc_opps} RFPs ({"OK" if gc_ok else "FAIL"})')
    print(f'  Supp RFPs:      {r_ok}/{r_total} OK')

    with open(report_path, 'w') as f:
        f.write(f'{"="*80}\nFAST RUN REPORT\n{"="*80}\n\n')
        f.write(f'OK: {ok}/{len(all_results)} | EMPTY: {empty} | ERROR: {errs}\n')
        f.write(f'Opportunities: {total_opps} | DB upserts: {total_ins} | With docs: {total_docs}\n')
        f.write(f'TGP: {tgp_opps} grants | Supp grants: {g_ok}/{g_total}\n')
        f.write(f'GovContracts: {gc_opps} RFPs | Supp RFPs: {r_ok}/{r_total}\n\n')

        if tgp_results:
            f.write(f'{"-"*80}\nTGP RESULTS (primary grants — all 50 states)\n{"-"*80}\n')
            for name, status, count, ins, docs in tgp_results:
                f.write(f'  [{status:7s}] {name:45s} | {count:4d} found | {ins:4d} new | {docs:3d} docs\n')
            f.write('\n')

        if grant_results:
            f.write(f'{"-"*80}\nSUPPLEMENTARY GRANT RESULTS\n{"-"*80}\n')
            for name, status, count, ins, docs in grant_results:
                f.write(f'  [{status:7s}] {name:45s} | {count:4d} found | {ins:4d} new | {docs:3d} docs\n')
            f.write('\n')

        if gc_results:
            f.write(f'{"-"*80}\nGOVCONTRACTS RESULTS (primary RFPs — all 50 states)\n{"-"*80}\n')
            for name, status, count, ins, docs in gc_results:
                f.write(f'  [{status:7s}] {name:45s} | {count:4d} found | {ins:4d} new | {docs:3d} docs\n')
            f.write('\n')

        if rfp_results:
            f.write(f'{"-"*80}\nSUPPLEMENTARY RFP RESULTS\n{"-"*80}\n')
            for name, status, count, ins, docs in rfp_results:
                f.write(f'  [{status:7s}] {name:45s} | {count:4d} found | {ins:4d} new | {docs:3d} docs\n')

        f.write('\nDone.\n')

    print(f'\nReport: {report_path}')


if __name__ == '__main__':
    main()
