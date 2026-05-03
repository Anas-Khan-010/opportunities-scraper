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

    # Minimum gap (seconds) between consecutive requests to the same host.
    # Enforced across ALL scraper instances in the process to keep us
    # below trigger thresholds of common gov-site WAFs / rate limiters.
    PER_HOST_MIN_INTERVAL = float(os.getenv('PER_HOST_MIN_INTERVAL', '2.0'))

    SELENIUM_DELAY_MIN = float(os.getenv('SELENIUM_DELAY_MIN', '4'))
    SELENIUM_DELAY_MAX = float(os.getenv('SELENIUM_DELAY_MAX', '9'))

    # Polite delay between consecutive scrapers in the orchestrator.
    # On a fixed deployment IP (e.g. Chris's server), running 50+ scrapers
    # back-to-back creates an unmistakable burst pattern. Inserting a
    # randomised pause makes the traffic look less like a crawler and gives
    # gov-site WAFs time to forget us between hits. Range is in seconds.
    INTER_SCRAPER_DELAY_MIN = float(os.getenv('INTER_SCRAPER_DELAY_MIN', '15'))
    INTER_SCRAPER_DELAY_MAX = float(os.getenv('INTER_SCRAPER_DELAY_MAX', '45'))

    # Free-proxy switch. The fp.fp.FreeProxy package returns dead/slow
    # proxies more often than not, which causes the shared Chrome driver to
    # restart between every scraper that asks for use_proxy=True (driver
    # thrash). Default OFF — set ENABLE_FREE_PROXY=true only if you have a
    # working free-proxy source.
    ENABLE_FREE_PROXY = os.getenv('ENABLE_FREE_PROXY', 'false').lower() == 'true'

    # Disable scrapers known to require network/IP changes that no code fix
    # can solve (Group B). Default ON — they are skipped with a clear log
    # message instead of wasting cycles + risking IP flags. Set
    # RUN_BLOCKED_SCRAPERS=true to attempt them anyway (e.g. from a server
    # with a residential exit IP).
    RUN_BLOCKED_SCRAPERS = os.getenv('RUN_BLOCKED_SCRAPERS', 'false').lower() == 'true'

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

    # ── 3. California Grants Portal (CKAN API) ────────────────────────
    CA_GRANTS_API_URL = os.getenv('CA_GRANTS_API_URL', 'https://data.ca.gov/api/3/action/datastore_search_sql')
    CA_GRANTS_RESOURCE_ID = os.getenv('CA_GRANTS_RESOURCE_ID', '111c8c88-21f6-453c-ae2c-b4785a0624f5')

    # ── 4. Alaska DCRA Grants (ArcGIS Feature Service) ────────────────
    AK_DCRA_MAX_PAGES = int(os.getenv('AK_DCRA_MAX_PAGES', '200'))

    # ── 5. New York Grants Gateway (PeopleSoft / Selenium) ───────────
    NY_GRANTS_URL = os.getenv(
        'NY_GRANTS_URL',
        'https://esupplier.sfs.ny.gov/psp/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL',
    )

    # ── 6. Minnesota Grants (JSON search API) ────────────────────────
    MN_GRANTS_MAX_PAGES = int(os.getenv('MN_GRANTS_MAX_PAGES', '10'))

    # ── 7. North Dakota Grants (WebGrants HTML) ────────────────────
    # No special config needed — listing URL is hardcoded in the scraper

    # ── 8. Texas ESBD ─────────────────────────────────────────────────
    TX_ESBD_BASE_URL = os.getenv('TX_ESBD_BASE_URL', 'https://www.txsmartbuy.gov')
    TX_ESBD_GRANTS_MAX_PAGES = int(os.getenv('TX_ESBD_GRANTS_MAX_PAGES', '10'))
    TX_ESBD_SOLICITATIONS_MAX_PAGES = int(os.getenv('TX_ESBD_SOLICITATIONS_MAX_PAGES', '15'))
    TX_ESBD_PRESOLICITATIONS_MAX_PAGES = int(os.getenv('TX_ESBD_PRESOLICITATIONS_MAX_PAGES', '15'))

    # ── 9. NC eVP ─────────────────────────────────────────────────────
    NC_EVP_BASE_URL = os.getenv('NC_EVP_BASE_URL', 'https://evp.nc.gov')
    NC_EVP_MAX_PAGES = int(os.getenv('NC_EVP_MAX_PAGES', '50'))

    # ── 10. Michigan MI Funding Hub (Selenium SPA) ──────────────────
    MI_FUNDING_HUB_MAX_PAGES = int(os.getenv('MI_FUNDING_HUB_MAX_PAGES', '20'))

    # ── 11. Montana eMACS / Jaggaer (Selenium + PDF) ───────────────
    MT_EMACS_MAX_PAGES = int(os.getenv('MT_EMACS_MAX_PAGES', '15'))

    # ── 12. Illinois CSFA (HTML + detail pages) ────────────────────
    IL_CSFA_MAX_PROGRAMS = int(os.getenv('IL_CSFA_MAX_PROGRAMS', '200'))

    # ── 13. New Jersey DHS (Selenium + PDF) ─────────────────────────
    # No special config — single page with three tables

    # ── 14. Delaware MMP Bids (Selenium SPA + PDF) ──────────────────
    DE_BIDS_MAX_PAGES = int(os.getenv('DE_BIDS_MAX_PAGES', '10'))

    # ── 15. New Hampshire Procurement (Selenium + PDF) ──────────────
    NH_PROCUREMENT_MAX_PAGES = int(os.getenv('NH_PROCUREMENT_MAX_PAGES', '10'))

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
