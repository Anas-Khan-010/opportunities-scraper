"""
Supplementary state grant scrapers — verified working sources that complement TGP.

The Grant Portal (tgp_grant_scraper.py) is the PRIMARY grant source covering
all 50 US states.  The scrapers below are additional verified sources that
provide richer, state-specific data (API fields, official grant numbers, etc.)
that TGP listing cards don't always include.

Only configs that were tested and confirmed to return real data are kept here.
"""

from scrapers.state_scrapers import create_state_scrapers
from utils.logger import logger


# ============================================================================
# SUPPLEMENTARY GRANT CONFIGS — verified working sources
# ============================================================================

GRANT_CONFIGS = [

    # ── API-based ──────────────────────────────────────────────────────────

    {   # CA Open Data CKAN API — returns ~160 active grants with rich metadata
        'abbr': 'CA', 'name': 'California',
        'method': 'api',
        'source_name': 'California Grants Portal',
        'organization': 'State of California',
        'location': 'California',
        'opportunity_type': 'grant',
        'api_type': 'ckan',
        'api_url': 'https://data.ca.gov/api/3/action/datastore_search_sql',
        'resource_id': '111c8c88-21f6-453c-ae2c-b4785a0624f5',
        'page_size': 100,
    },

    # ── HTML-based (requests + BeautifulSoup) ──────────────────────────────

    {   # nc.gov HTML table — returns ~74 grant programs
        'abbr': 'NC', 'name': 'North Carolina',
        'method': 'html',
        'source_name': 'North Carolina Grants',
        'organization': 'State of North Carolina',
        'location': 'North Carolina',
        'opportunity_type': 'grant',
        'url': 'https://www.nc.gov/your-government/all-nc-state-services/grant-opportunities',
        'parser': 'table',
        'table_selector': 'table',
        'skip_header': True,
        'col_category': 0,
        'col_title_link': 1,
        'col_description': 2,
    },

    {   # Governor's office external grant links — ~108 programs
        'abbr': 'VA', 'name': 'Virginia',
        'method': 'html',
        'source_name': 'Virginia Grants',
        'organization': 'Commonwealth of Virginia',
        'location': 'Virginia',
        'opportunity_type': 'grant',
        'url': 'https://www.governor.virginia.gov/constituent-services/grants/',
        'parser': 'links_external',
        'container_selector': '.field-items, .content-area, main, article',
    },

    {   # PA DCED grant programs listing
        'abbr': 'PA', 'name': 'Pennsylvania',
        'method': 'html',
        'source_name': 'Pennsylvania DCED Grants',
        'organization': 'Commonwealth of Pennsylvania',
        'location': 'Pennsylvania',
        'opportunity_type': 'grant',
        'url': 'https://dced.pa.gov/program_categories/grant/',
        'parser': 'links',
        'container_selector': '.content-area, main, article, .program-list',
    },

    {   # Indiana OCRA CDBG programs
        'abbr': 'IN', 'name': 'Indiana',
        'method': 'html',
        'source_name': 'Indiana Community Grants',
        'organization': 'State of Indiana',
        'location': 'Indiana',
        'opportunity_type': 'grant',
        'url': 'https://www.in.gov/ocra/cdbg/',
        'parser': 'links',
        'container_selector': 'main, article, .content-area',
    },
]


# ============================================================================
# Factory
# ============================================================================

def get_all_state_grant_scrapers():
    """Create scraper instances for supplementary state grant sources."""
    scrapers = create_state_scrapers(GRANT_CONFIGS)
    logger.info(f"Created {len(scrapers)} supplementary state GRANT scrapers")
    return scrapers
