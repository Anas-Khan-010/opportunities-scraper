"""
Supplementary state grant scrapers — verified working sources that complement TGP.

The Grant Portal (tgp_grant_scraper.py) is the PRIMARY grant source covering
all 50 US states.  Texas ESBD grants are handled by texas_esbd_scraper.py.

Only configs that were tested and confirmed to return real data are kept here.
Currently: California CKAN API only (the HTML scrapers were unreliable).
"""

from scrapers.state_scrapers import create_state_scrapers
from config.settings import config
from utils.logger import logger


# ============================================================================
# SUPPLEMENTARY GRANT CONFIGS — verified working sources
# ============================================================================

GRANT_CONFIGS = [

    {   # CA Open Data CKAN API — returns ~160 active grants with rich metadata
        'abbr': 'CA', 'name': 'California',
        'method': 'api',
        'source_name': 'California Grants Portal',
        'organization': 'State of California',
        'location': 'California',
        'opportunity_type': 'grant',
        'api_type': 'ckan',
        'api_url': config.CA_GRANTS_API_URL,
        'resource_id': config.CA_GRANTS_RESOURCE_ID,
        'page_size': 100,
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
