import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database Configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'postgres')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    
    # Scraper Configuration
    SCRAPER_DELAY = int(os.getenv('SCRAPER_DELAY', '2'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # SAM.gov Configuration
    SAM_GOV_API_KEY = os.getenv('SAM_GOV_API_KEY')
    SAM_GOV_BASE_URL = os.getenv('SAM_GOV_BASE_URL', 'https://sam.gov')
    SAM_GOV_API_URL = os.getenv('SAM_GOV_API_URL', 'https://api.sam.gov/prod/opportunities/v2/search')
    SAM_GOV_OPP_DELAY = float(os.getenv('SAM_GOV_OPP_DELAY', '10.0'))
    SAM_GOV_PAGE_DELAY = float(os.getenv('SAM_GOV_PAGE_DELAY', '60.0'))
    
    # Grants.gov Configuration
    GRANTS_GOV_BASE_URL = os.getenv('GRANTS_GOV_BASE_URL', 'https://www.grants.gov')
    GRANTS_GOV_API_URL = os.getenv('GRANTS_GOV_API_URL', 'https://api.grants.gov/v1/api/search2')
    GRANTS_GOV_DETAIL_PAGE_TIMEOUT = int(os.getenv('GRANTS_GOV_DETAIL_PAGE_TIMEOUT', '15'))
    GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT = int(os.getenv('GRANTS_GOV_DETAIL_PAGE_RENDER_WAIT', '3'))
    
    # Duke Research Funding Configuration
    DUKE_BASE_URL = os.getenv('DUKE_BASE_URL', 'https://researchfunding.duke.edu')
    DUKE_LISTING_URL = os.getenv(
        'DUKE_LISTING_URL',
        'https://researchfunding.duke.edu/search-results?open=1&sort_bef_combine=deadline_ASC'
    )
    
    # User Agents
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')

config = Config()
