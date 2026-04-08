# US Government Opportunities Scraper

A production-grade data pipeline that aggregates **grants, contracts, and RFPs** from federal agencies, all 50 US states, and research foundations into a single Supabase (PostgreSQL) database.

The system scrapes data from **multiple federal portals, state procurement websites, open-data APIs, foundation funding databases, and nationwide grant/RFP aggregator platforms** — collectively targeting **over 1,000,000 live opportunities** across the United States.

---

## Data Coverage

### Federal Scrapers
- **Grants.gov** — All federal grant opportunities via REST API + Selenium detail page enrichment (~3,500+ active)
- **SAM.gov** — Federal contracts and procurement via REST API with strict rate limiting (~50,000+ active)

### Foundation & Research Scrapers
- **Duke Research Funding** — National research and academic funding opportunities via Selenium (~200+ active)

### State-Level Scrapers
- **California Grants Portal** — State grants via CKAN open-data API (~160+ active)
- **The Grant Portal** — Grant listings across all 50 states + DC via Selenium (~20,000+ listings)
- **Texas ESBD** — Texas state grants, solicitations, and pre-solicitations via Selenium (~1,000+ active)
- **NC eVP** — North Carolina solicitations and procurement via Selenium (~500+ active)

### RFP & Contract Aggregator Scrapers
- **GovernmentContracts.us** — State and local government RFPs across all 50 states (~10,000+ listings)
- **RFPMart** — Massive federal + state RFP aggregator with full public descriptions (~980,000+ total)

> Each scraper is a **separate, independent module** with its own parsing logic, anti-detection strategy, and detail-page enrichment pipeline — tailored to the specific structure and behavior of each source website.

**Combined, these scrapers target over 1,000,000+ grants, contracts, and RFPs across all 50 US states, federal agencies, and research foundations — making this one of the most comprehensive government opportunity aggregation pipelines available.**

---

## Architecture

```
opportunities-scraper/
├── main.py                          # Orchestrator — runs all scrapers sequentially
├── config/
│   └── settings.py                  # Centralized config loader (reads .env)
├── database/
│   └── db.py                        # PostgreSQL connection, upsert with COALESCE backfill
├── scrapers/
│   ├── base_scraper.py              # Abstract base class (retry, session, real-time DB writes)
│   ├── grants_gov.py                # Grants.gov federal grants scraper
│   ├── sam_gov.py                   # SAM.gov federal contracts scraper
│   ├── foundation_scrapers.py       # Duke Research Funding scraper
│   ├── state_scrapers.py            # Shared Selenium driver manager + state helpers
│   ├── state_grant_scrapers.py      # Config-driven state grant scrapers
│   ├── tgp_grant_scraper.py         # The Grant Portal — 50-state grant scraper
│   ├── texas_esbd_scraper.py        # Texas ESBD multi-section scraper
│   ├── nc_evp_scraper.py            # North Carolina eVP scraper
│   ├── govcontracts_rfp_scraper.py  # GovernmentContracts.us 50-state RFP scraper
│   └── rfpmart_scraper.py           # RFPMart nationwide RFP scraper
├── parsers/
│   └── parser_utils.py              # PDF extraction, validation, enrichment utilities
├── utils/
│   ├── helpers.py                   # Text cleaning, date parsing, categorization
│   └── logger.py                    # File + console logging
├── scripts/
│   ├── store_one_each.py            # Test harness — stores 1 record per source
│   └── fast_run.py                  # Full pipeline runner with per-scraper reporting
├── schema.sql                       # Canonical Supabase DDL (table + indexes + views)
├── setup.sh                         # One-command environment setup
├── requirements.txt                 # Pinned Python dependencies
├── .env.example                     # Template for all configuration variables
└── .gitignore
```

---

## Database Schema

Each opportunity record contains **14 data fields** designed to capture the complete picture of any grant or RFP:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Auto-generated primary key |
| `title` | TEXT | Opportunity title |
| `organization` | TEXT | Issuing agency or organization |
| `description` | TEXT | Full description / scope of work (up to 10,000 chars) |
| `eligibility` | TEXT | Who can apply (set-aside type, notice type, requirements) |
| `funding_amount` | TEXT | Award amount or estimated value |
| `deadline` | TIMESTAMP | Response / application deadline |
| `category` | TEXT | Auto-categorized + source-specific (NAICS, commodity codes) |
| `location` | TEXT | State, city, or "United States" for federal |
| `source` | TEXT | Which scraper produced this record |
| `source_url` | TEXT | **UNIQUE** — direct link to the original listing |
| `opportunity_number` | TEXT | Solicitation / grant number |
| `opportunity_type` | TEXT | `grant`, `contract`, or `rfp` |
| `posted_date` | TIMESTAMP | When the opportunity was published |
| `document_urls` | TEXT[] | Array of attachment / document download links |
| `scraped_at` | TIMESTAMP | Last scrape timestamp |

The `ON CONFLICT (source_url) DO UPDATE SET ... COALESCE(...)` upsert strategy means re-running scrapers **enriches** existing records — new data fills previously empty fields without overwriting existing values.

---

## Key Features

- **Real-time database writes** — Every opportunity is stored to the database the moment it is scraped. If the process is interrupted, shut down, or crashes, all data collected up to that point is already safely persisted.
- **Smart deduplication** — Each scraper checks the database before counting an opportunity as "new." It keeps paginating past already-seen records until it finds fresh ones, so every run produces genuinely new data.
- **Configurable per-run limit** — `MAX_NEW_PER_SCRAPER` (default: 100) caps how many new opportunities each scraper collects per run, keeping execution time and resource usage predictable.
- **Incremental enrichment** — The COALESCE-based upsert fills in missing fields on subsequent runs without overwriting existing data, so records get richer over time.

---

## Quick Start

### 1. Clone and set up

```bash
git clone <repo-url>
cd opportunities-scraper

# Automated setup (creates venv, installs deps, tests DB)
chmod +x setup.sh
./setup.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env   # Fill in your Supabase credentials + SAM.gov API key
```

**Required credentials:**
- Supabase database host, port, user, and password
- SAM.gov API key (free at [sam.gov/data-services](https://sam.gov/data-services/))

All other settings have sensible defaults.

### 3. Create the database table

Run this SQL in the **Supabase SQL Editor** (or use `psql`):

```sql
-- Drop existing table if starting fresh
DROP TABLE IF EXISTS opportunities CASCADE;

-- Then paste the contents of schema.sql, or run:
CREATE TABLE IF NOT EXISTS opportunities (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title             TEXT NOT NULL,
    organization      TEXT,
    description       TEXT,
    eligibility       TEXT,
    funding_amount    TEXT,
    deadline          TIMESTAMP,
    category          TEXT,
    location          TEXT,
    source            TEXT NOT NULL,
    source_url        TEXT UNIQUE NOT NULL,
    opportunity_number TEXT,
    opportunity_type  TEXT DEFAULT NULL,
    posted_date       TIMESTAMP,
    document_urls     TEXT[],
    scraped_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source           ON opportunities(source);
CREATE INDEX IF NOT EXISTS idx_deadline         ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_category         ON opportunities(category);
CREATE INDEX IF NOT EXISTS idx_scraped_at       ON opportunities(scraped_at);
CREATE INDEX IF NOT EXISTS idx_opportunity_type ON opportunities(opportunity_type);
CREATE INDEX IF NOT EXISTS idx_location         ON opportunities(location);
CREATE INDEX IF NOT EXISTS idx_posted_date      ON opportunities(posted_date);
```

### 4. Run

```bash
# Activate virtual environment
source .venv/bin/activate

# Full pipeline (all scrapers)
python main.py

# Quick test — store 1 record from each source
python scripts/store_one_each.py

# Full pipeline with per-scraper report
python scripts/fast_run.py
```

---

## Anti-Detection and Rate Limiting

- **Random delays** between every page load and detail page visit (configurable via `.env`)
- **Rotating User-Agent strings** across requests
- **`undetected-chromedriver`** for Selenium scrapers to bypass bot detection
- **Shared Selenium driver** (singleton pattern) to minimize browser instances
- **SAM.gov hard cap**: configurable requests/run with configurable inter-request delay
- **Configurable page limits** per scraper to control scraping depth

---

## Configuration Reference

All URLs, API endpoints, delays, and page limits are externalized in `.env`. See `.env.example` for the complete list with defaults. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_NEW_PER_SCRAPER` | 100 | Max new (non-duplicate) opportunities per scraper per run |
| `SCRAPER_DELAY` | 2 | Base delay between HTTP requests (seconds) |
| `SELENIUM_DELAY_MIN` / `MAX` | 4 / 9 | Random delay range for Selenium page loads |
| `SAM_GOV_MAX_REQUESTS` | 4 | Hard cap on SAM.gov API calls per run |
| `SAM_GOV_OPP_DELAY` | 1800 | Seconds between SAM.gov requests (30 min) |
| `TGP_MAX_PAGES_PER_STATE` | 10 | Max pages per state on The Grant Portal |
| `GOVCONTRACTS_MAX_PAGES_PER_STATE` | 5 | Max pages per state on GovernmentContracts.us |
| `RFPMART_MAX_PAGES` | 10 | Max listing pages on RFPMart (100 RFPs/page) |

---

## Useful SQL Queries

```sql
-- Total opportunities by source
SELECT source, opportunity_type, COUNT(*) AS total
FROM opportunities
GROUP BY source, opportunity_type
ORDER BY total DESC;

-- Active opportunities with upcoming deadlines
SELECT title, source, deadline, location
FROM opportunities
WHERE deadline > NOW()
ORDER BY deadline ASC
LIMIT 50;

-- Full-text search
SELECT title, source, deadline
FROM opportunities
WHERE to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,''))
      @@ plainto_tsquery('english', 'software development')
ORDER BY posted_date DESC;

-- Opportunities by state
SELECT location, COUNT(*) AS total
FROM opportunities
GROUP BY location
ORDER BY total DESC;

-- Cleanup expired opportunities older than 180 days
SELECT clean_old_opportunities(180);
```

---

## Scheduling (Cron)

```bash
# Run daily at 2 AM
crontab -e
# Add:
0 2 * * * cd /path/to/opportunities-scraper && source .venv/bin/activate && python main.py >> logs/cron.log 2>&1
```

---

## Tech Stack

- **Python 3.8+**
- **Selenium** + **undetected-chromedriver** — dynamic JS-rendered portals
- **requests** + **BeautifulSoup4** + **lxml** — static HTML scraping
- **psycopg2** — PostgreSQL / Supabase connection
- **python-dotenv** — environment configuration
- **python-dateutil** — flexible date parsing
- **PyPDF2** — PDF document text extraction
