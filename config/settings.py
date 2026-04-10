import os
from dotenv import load_dotenv

load_dotenv()


def _float_tuple(env_min, env_max, default_min, default_max):
    return (
        float(os.getenv(env_min, str(default_min))),
        float(os.getenv(env_max, str(default_max))),
    )


class Config:
    # ── Database ───────────────────────────────────────────────────────
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'postgres')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')

    # ── Global scraper settings ────────────────────────────────────────
    SCRAPER_DELAY = int(os.getenv('SCRAPER_DELAY', '2'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    MAX_NEW_PER_SCRAPER = int(os.getenv('MAX_NEW_PER_SCRAPER', '100'))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    SELENIUM_DELAY_MIN = float(os.getenv('SELENIUM_DELAY_MIN', '4'))
    SELENIUM_DELAY_MAX = float(os.getenv('SELENIUM_DELAY_MAX', '9'))

    # ── 1. Grants.gov ──────────────────────────────────────────────────
    GRANTS_GOV_BASE_URL = os.getenv('GRANTS_GOV_BASE_URL', 'https://www.grants.gov')
    GRANTS_GOV_API_URL = os.getenv('GRANTS_GOV_API_URL', 'https://api.grants.gov/v1/api/search2')
    GRANTS_GOV_DETAIL_API_URL = os.getenv('GRANTS_GOV_DETAIL_API_URL', 'https://api.grants.gov/v1/api/fetchOpportunity')
    GRANTS_GOV_DETAIL_PAGE_TIMEOUT = int(os.getenv('GRANTS_GOV_DETAIL_PAGE_TIMEOUT', '15'))
    GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT = int(os.getenv('GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT', '3'))

    # ── 2. SAM.gov ─────────────────────────────────────────────────────
    SAM_GOV_API_KEY = os.getenv('SAM_GOV_API_KEY')
    SAM_GOV_BASE_URL = os.getenv('SAM_GOV_BASE_URL', 'https://sam.gov')
    SAM_GOV_API_URL = os.getenv('SAM_GOV_API_URL', 'https://api.sam.gov/prod/opportunities/v2/search')
    SAM_GOV_OPP_DELAY = float(os.getenv('SAM_GOV_OPP_DELAY', '1800'))
    SAM_GOV_PAGE_DELAY = float(os.getenv('SAM_GOV_PAGE_DELAY', '1800'))
    SAM_GOV_MAX_REQUESTS = int(os.getenv('SAM_GOV_MAX_REQUESTS', '4'))

    # ── 3. Duke Research Funding ───────────────────────────────────────
    DUKE_BASE_URL = os.getenv('DUKE_BASE_URL', 'https://researchfunding.duke.edu')
    DUKE_LISTING_URL = os.getenv(
        'DUKE_LISTING_URL',
        'https://researchfunding.duke.edu/search-results?open=1&sort_bef_combine=deadline_ASC',
    )

    # ── 4. California Grants Portal (CKAN API) ────────────────────────
    CA_GRANTS_API_URL = os.getenv('CA_GRANTS_API_URL', 'https://data.ca.gov/api/3/action/datastore_search_sql')
    CA_GRANTS_RESOURCE_ID = os.getenv('CA_GRANTS_RESOURCE_ID', '111c8c88-21f6-453c-ae2c-b4785a0624f5')

    # ── 5. The Grant Portal (TGP) ─────────────────────────────────────
    TGP_BASE_URL = os.getenv('TGP_BASE_URL', 'https://www.thegrantportal.com')
    TGP_MAX_PAGES_PER_STATE = int(os.getenv('TGP_MAX_PAGES_PER_STATE', '10'))
    TGP_MAX_NEW_PER_STATE = int(os.getenv('TGP_MAX_NEW_PER_STATE', '10'))
    TGP_EMAIL = os.getenv('TGP_EMAIL', '')
    TGP_PASSWORD = os.getenv('TGP_PASSWORD', '')

    # ── 6. Texas ESBD ─────────────────────────────────────────────────
    TX_ESBD_BASE_URL = os.getenv('TX_ESBD_BASE_URL', 'https://www.txsmartbuy.gov')
    TX_ESBD_GRANTS_MAX_PAGES = int(os.getenv('TX_ESBD_GRANTS_MAX_PAGES', '10'))
    TX_ESBD_SOLICITATIONS_MAX_PAGES = int(os.getenv('TX_ESBD_SOLICITATIONS_MAX_PAGES', '15'))
    TX_ESBD_PRESOLICITATIONS_MAX_PAGES = int(os.getenv('TX_ESBD_PRESOLICITATIONS_MAX_PAGES', '15'))

    # ── 7. NC eVP ─────────────────────────────────────────────────────
    NC_EVP_BASE_URL = os.getenv('NC_EVP_BASE_URL', 'https://evp.nc.gov')
    NC_EVP_MAX_PAGES = int(os.getenv('NC_EVP_MAX_PAGES', '50'))

    # ── 8. GovernmentContracts.us ──────────────────────────────────────
    GOVCONTRACTS_BASE_URL = os.getenv('GOVCONTRACTS_BASE_URL', 'https://www.governmentcontracts.us')
    GOVCONTRACTS_MAX_PAGES_PER_STATE = int(os.getenv('GOVCONTRACTS_MAX_PAGES_PER_STATE', '5'))
    GOVCONTRACTS_MAX_NEW_PER_STATE = int(os.getenv('GOVCONTRACTS_MAX_NEW_PER_STATE', '10'))

    # ── 9. RFPMart ────────────────────────────────────────────────────
    RFPMART_BASE_URL = os.getenv('RFPMART_BASE_URL', 'https://www.rfpmart.com')
    RFPMART_MAX_PAGES = int(os.getenv('RFPMART_MAX_PAGES', '10'))

    # ── User Agents ────────────────────────────────────────────────────
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    # ── Paths ──────────────────────────────────────────────────────────
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')


config = Config()
