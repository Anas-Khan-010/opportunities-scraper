#!/usr/bin/env python3
"""
Scrape 5 opportunities from every state and store them in the database.

This is the production counterpart of test_state_scrapers.py — it uses
the real database (Supabase/PostgreSQL configured via .env) instead of
a fake one, ensures the table exists, and prints a per-state summary
at the end.

Usage:
    python store_state_opps.py                        # all states, 5 each
    python store_state_opps.py --max 20               # all states, 20 each
    python store_state_opps.py --max 0                # unlimited
    python store_state_opps.py illinois minnesota     # specific states only
    python store_state_opps.py --max 10 alaska texas  # 10 from selected states
"""

import sys
import os
import time
from datetime import datetime

# ── Parse --max N from argv ──────────────────────────────────────────
_max_opps = 5
_filtered_argv = []
_skip_next = False
for i, arg in enumerate(sys.argv[1:], 1):
    if _skip_next:
        _skip_next = False
        continue
    if arg == "--max" and i < len(sys.argv) - 1:
        _max_opps = int(sys.argv[i + 1])
        _skip_next = True
    elif arg.startswith("--max="):
        _max_opps = int(arg.split("=", 1)[1])
    else:
        _filtered_argv.append(arg)

os.environ.setdefault("MAX_NEW_PER_SCRAPER", str(_max_opps or 9999))
os.environ.setdefault("LOG_LEVEL", "INFO")

from config.settings import config
config.MAX_NEW_PER_SCRAPER = _max_opps if _max_opps > 0 else 9999

from database.db import db
from scrapers.base_scraper import cleanup_selenium
from utils.logger import logger

from scrapers.states.alabama import get_alabama_scrapers
from scrapers.states.alaska import get_alaska_scrapers
from scrapers.states.arizona import get_arizona_scrapers
from scrapers.states.arkansas import get_arkansas_scrapers
from scrapers.states.california import get_california_scrapers
from scrapers.states.colorado import get_colorado_scrapers
from scrapers.states.connecticut import get_connecticut_scrapers
from scrapers.states.delaware import get_delaware_scrapers
from scrapers.states.florida import get_florida_scrapers
from scrapers.states.georgia import get_georgia_scrapers
from scrapers.states.hawaii import get_hawaii_scrapers
from scrapers.states.idaho import get_idaho_scrapers
from scrapers.states.illinois import get_illinois_scrapers
from scrapers.states.indiana import get_indiana_scrapers
from scrapers.states.iowa import get_iowa_scrapers
from scrapers.states.kansas import get_kansas_scrapers
from scrapers.states.kentucky import get_kentucky_scrapers
from scrapers.states.louisiana import get_louisiana_scrapers
from scrapers.states.maine import get_maine_scrapers
from scrapers.states.maryland import get_maryland_scrapers
from scrapers.states.massachusetts import get_massachusetts_scrapers
from scrapers.states.michigan import get_michigan_scrapers
from scrapers.states.minnesota import get_minnesota_scrapers
from scrapers.states.mississippi import get_mississippi_scrapers
from scrapers.states.missouri import get_missouri_scrapers
from scrapers.states.montana import get_montana_scrapers
from scrapers.states.nebraska import get_nebraska_scrapers
from scrapers.states.nevada import get_nevada_scrapers
from scrapers.states.new_hampshire import get_new_hampshire_scrapers
from scrapers.states.new_jersey import get_new_jersey_scrapers
from scrapers.states.new_mexico import get_new_mexico_scrapers
from scrapers.states.new_york import get_ny_grants_scrapers
from scrapers.states.north_carolina import get_nc_evp_scrapers
from scrapers.states.north_dakota import get_north_dakota_scrapers
from scrapers.states.ohio import get_ohio_scrapers
from scrapers.states.oklahoma import get_oklahoma_scrapers
from scrapers.states.oregon import get_oregon_scrapers
from scrapers.states.pennsylvania import get_pennsylvania_scrapers
from scrapers.states.rhode_island import get_rhode_island_scrapers
from scrapers.states.south_carolina import get_south_carolina_scrapers
from scrapers.states.south_dakota import get_south_dakota_scrapers
from scrapers.states.tennessee import get_tennessee_scrapers
from scrapers.states.texas import get_texas_esbd_scrapers
from scrapers.states.utah import get_utah_scrapers
from scrapers.states.vermont import get_vermont_scrapers
from scrapers.states.virginia import get_virginia_scrapers
from scrapers.states.washington import get_washington_scrapers
from scrapers.states.west_virginia import get_west_virginia_scrapers
from scrapers.states.wisconsin import get_wisconsin_scrapers
from scrapers.states.wyoming import get_wyoming_scrapers

ALL_STATES = {
    "alabama":        get_alabama_scrapers,
    "alaska":         get_alaska_scrapers,
    "arizona":        get_arizona_scrapers,
    "arkansas":       get_arkansas_scrapers,
    "california":     get_california_scrapers,
    "colorado":       get_colorado_scrapers,
    "connecticut":    get_connecticut_scrapers,
    "delaware":       get_delaware_scrapers,
    "florida":        get_florida_scrapers,
    "georgia":        get_georgia_scrapers,
    "hawaii":         get_hawaii_scrapers,
    "idaho":          get_idaho_scrapers,
    "illinois":       get_illinois_scrapers,
    "indiana":        get_indiana_scrapers,
    "iowa":           get_iowa_scrapers,
    "kansas":         get_kansas_scrapers,
    "kentucky":       get_kentucky_scrapers,
    "louisiana":      get_louisiana_scrapers,
    "maine":          get_maine_scrapers,
    "maryland":       get_maryland_scrapers,
    "massachusetts":  get_massachusetts_scrapers,
    "michigan":       get_michigan_scrapers,
    "minnesota":      get_minnesota_scrapers,
    "mississippi":    get_mississippi_scrapers,
    "missouri":       get_missouri_scrapers,
    "montana":        get_montana_scrapers,
    "nebraska":       get_nebraska_scrapers,
    "nevada":         get_nevada_scrapers,
    "new_hampshire":  get_new_hampshire_scrapers,
    "new_jersey":     get_new_jersey_scrapers,
    "new_mexico":     get_new_mexico_scrapers,
    "new_york":       get_ny_grants_scrapers,
    "north_carolina": get_nc_evp_scrapers,
    "north_dakota":   get_north_dakota_scrapers,
    "ohio":           get_ohio_scrapers,
    "oklahoma":       get_oklahoma_scrapers,
    "oregon":         get_oregon_scrapers,
    "pennsylvania":   get_pennsylvania_scrapers,
    "rhode_island":   get_rhode_island_scrapers,
    "south_carolina": get_south_carolina_scrapers,
    "south_dakota":   get_south_dakota_scrapers,
    "tennessee":      get_tennessee_scrapers,
    "texas":          get_texas_esbd_scrapers,
    "utah":           get_utah_scrapers,
    "vermont":        get_vermont_scrapers,
    "virginia":       get_virginia_scrapers,
    "washington":     get_washington_scrapers,
    "west_virginia":  get_west_virginia_scrapers,
    "wisconsin":      get_wisconsin_scrapers,
    "wyoming":        get_wyoming_scrapers,
}

SEP  = "=" * 80
THIN = "-" * 80


def run_state(name, factory_fn, max_n):
    """Run all scrapers for one state and return (new_count, dup_count, errors)."""
    scrapers = factory_fn()
    new_total = 0
    dup_total = 0
    errors = []

    for scraper in scrapers:
        scraper._max_new = max_n if max_n > 0 else 9999
        try:
            scraper.scrape()
            new_total += scraper._new_count
            dup_total += scraper._dup_count
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            errors.append(str(exc))
            logger.error(f"{name}: {exc}")

    return new_total, dup_total, errors


def main():
    requested = [a.lower().replace("-", "_").replace(" ", "_") for a in _filtered_argv]

    if requested:
        states_to_run = {}
        for name in requested:
            if name in ALL_STATES:
                states_to_run[name] = ALL_STATES[name]
            else:
                print(f"Unknown state: '{name}'")
                print(f"Available: {', '.join(sorted(ALL_STATES))}")
                return 1
    else:
        states_to_run = ALL_STATES

    limit_label = str(_max_opps) if _max_opps > 0 else "unlimited"
    print(SEP)
    print(f"  STORE STATE OPPORTUNITIES  —  {len(states_to_run)} states, max {limit_label} per state")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)

    db.create_tables()

    results = {}
    grand_new = 0
    grand_dup = 0
    start_all = time.time()

    for name, factory in states_to_run.items():
        print(f"\n  [{name.upper()}] scraping ...", end="", flush=True)
        t0 = time.time()
        try:
            new_c, dup_c, errs = run_state(name, factory, _max_opps)
            elapsed = time.time() - t0
            results[name] = {"new": new_c, "dup": dup_c, "err": len(errs), "time": elapsed}
            grand_new += new_c
            grand_dup += dup_c
            status = "OK" if new_c + dup_c > 0 else ("ERROR" if errs else "EMPTY")
            print(f" {new_c} new, {dup_c} updated  ({elapsed:.0f}s) [{status}]")
        except KeyboardInterrupt:
            print(f"\n\n  Interrupted during {name}. Showing results so far.\n")
            break
        except Exception as exc:
            elapsed = time.time() - t0
            results[name] = {"new": 0, "dup": 0, "err": 1, "time": elapsed}
            print(f" FATAL: {exc}  ({elapsed:.0f}s)")

    cleanup_selenium()

    total_time = time.time() - start_all

    print(f"\n{SEP}")
    print(f"  SUMMARY")
    print(SEP)
    print(f"  {'State':<20} {'New':>5} {'Updated':>8} {'Errors':>7} {'Time':>7}")
    print(f"  {THIN[:47]}")
    for name, r in results.items():
        tag = "OK" if r["new"] + r["dup"] > 0 else "EMPTY"
        if r["err"]:
            tag = "ERR"
        print(f"  {name:<20} {r['new']:>5} {r['dup']:>8} {r['err']:>7} {r['time']:>6.0f}s  [{tag}]")
    print(f"  {THIN[:47]}")
    print(f"  {'TOTAL':<20} {grand_new:>5} {grand_dup:>8} {'':>7} {total_time:>6.0f}s")

    try:
        stats = db.get_stats()
        print(f"\n  Database: {stats.get('total', '?')} total rows, "
              f"{stats.get('sources', '?')} sources, "
              f"{stats.get('active', '?')} with future deadlines")
    except Exception:
        pass

    # --- PHASE 4: FIELD ENRICHMENT ENGINE ---
    try:
        from scrapers.enricher import OpportunityEnricher
        logger.info(SEP)
        logger.info("Initializing Field Enrichment Engine...")
        enricher = OpportunityEnricher(limit=200)
        enricher.enrich()
    except Exception as e:
        logger.error(f"Field Enrichment Engine failed: {e}")

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
