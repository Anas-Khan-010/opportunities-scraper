# RFP and Grants Scraping System

Automated system for collecting U.S. federal, state, local, and foundation RFP and grant opportunities.

## 🎯 Project Overview

This system automatically scrapes grant opportunities, RFPs, and funding calls from multiple sources and stores them in a Supabase PostgreSQL database for easy access and integration with web applications.

## 📋 Features

- **Multi-Source Scraping**: Collects opportunities from federal, state, and foundation sources
- **Automated Daily Updates**: Runs on schedule to keep data fresh
- **Duplicate Prevention**: Smart detection to avoid storing duplicate opportunities
- **Document Extraction**: Downloads and extracts text from PDF documents
- **Categorization**: Automatically categorizes opportunities by type
- **Robust Error Handling**: Continues running even if individual scrapers fail
- **Comprehensive Logging**: Detailed logs for monitoring and debugging

## 🗂️ Project Structure

```
opportunities-scraper/
├── main.py                          # Main orchestrator script
├── requirements.txt                 # Python dependencies
├── .env                            # Environment configuration (create from .env.example)
├── .env.example                    # Environment template
├── .gitignore                      # Git ignore rules
│
├── config/
│   └── settings.py                 # Configuration management
│
├── database/
│   └── db.py                       # Database connection and operations
│
├── scrapers/
│   ├── base_scraper.py            # Base scraper class
│   ├── grants_gov.py              # Grants.gov scraper (Federal)
│   ├── sam_gov.py                 # SAM.gov scraper (Federal RFPs)
│   ├── state_scrapers.py          # State-level scrapers
│   └── foundation_scrapers.py     # Foundation grant scrapers
│
├── parsers/
│   └── parser_utils.py            # Data extraction utilities
│
├── utils/
│   ├── logger.py                  # Logging system
│   └── helpers.py                 # Helper functions
│
├── logs/                           # Log files (auto-generated)
└── downloads/                      # Downloaded documents (auto-generated)
```

## 🚀 Installation

### 1. Clone or navigate to project directory

```bash
cd /home/anas/Cleint-Projects/opportunities-scraper
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
nano .env
```

Update the `.env` file with your Supabase credentials:

```env
DB_HOST=your_supabase_host
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
```

## 🎮 Usage

### Run the scraper manually

```bash
python main.py
```

### Run with virtual environment

```bash
source venv/bin/activate
python main.py
```

## 📊 Data Sources

### Federal Sources (Implemented)
- ✅ **Grants.gov** - All federal grant opportunities
- ✅ **SAM.gov** - Federal RFPs and contracts (requires free API key)
- ✅ **NIH Grants** - National Institutes of Health
- ✅ **NSF Grants** - National Science Foundation
- ✅ **DOE Grants** - Department of Energy
- ✅ **USDA Grants** - Department of Agriculture
- ✅ **EPA Grants** - Environmental Protection Agency
- ✅ **HUD Grants** - Housing and Urban Development
- ✅ **SBA Grants** - Small Business Administration

### Foundation Sources (Implemented)
- ✅ **GrantWatch** - Foundation and corporate grants
- ✅ **Gates Foundation** - Bill & Melinda Gates Foundation
- ✅ **Ford Foundation** - Social justice grants
- ✅ **RWJF** - Robert Wood Johnson Foundation (Healthcare)
- ✅ **Kellogg Foundation** - W.K. Kellogg Foundation
- ✅ **MacArthur Foundation** - Global grants

### State Sources (Top 10 Implemented)
- ✅ **California** - State grants and opportunities
- ✅ **Texas** - State grants and opportunities
- ✅ **Florida** - State grants and opportunities
- ✅ **New York** - State grants and opportunities
- ✅ **Pennsylvania** - State grants and opportunities
- ✅ **Illinois** - State grants and opportunities
- ✅ **Ohio** - State grants and opportunities
- ✅ **Georgia** - State grants and opportunities
- ✅ **North Carolina** - State grants and opportunities
- ✅ **Michigan** - State grants and opportunities

## 🗄️ Database Schema

```sql
CREATE TABLE opportunities (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    organization TEXT,
    description TEXT,
    eligibility TEXT,
    funding_amount TEXT,
    deadline TIMESTAMP,
    category TEXT,
    location TEXT,
    source TEXT NOT NULL,
    source_url TEXT UNIQUE NOT NULL,
    opportunity_number TEXT,
    posted_date TIMESTAMP,
    document_urls TEXT[],
    full_document TEXT,
    scraped_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## ⏰ Automation Setup

### Using Cron (Linux/Mac)

Edit crontab:
```bash
crontab -e
```

Add daily run at 2 AM:
```bash
0 2 * * * cd /home/anas/Cleint-Projects/opportunities-scraper && source venv/bin/activate && python main.py >> logs/cron.log 2>&1
```

### Alternative schedules:

Every 6 hours:
```bash
0 */6 * * * cd /home/anas/Cleint-Projects/opportunities-scraper && source venv/bin/activate && python main.py
```

Every day at midnight:
```bash
0 0 * * * cd /home/anas/Cleint-Projects/opportunities-scraper && source venv/bin/activate && python main.py
```

## 📝 Logs

Logs are stored in the `logs/` directory with daily rotation:
- Format: `scraper_YYYYMMDD.log`
- Location: `/home/anas/Cleint-Projects/opportunities-scraper/logs/`

View latest log:
```bash
tail -f logs/scraper_$(date +%Y%m%d).log
```

## 🔧 Configuration

### Scraper Settings

Edit `config/settings.py` or `.env`:

```python
SCRAPER_DELAY = 2        # Delay between requests (seconds)
MAX_RETRIES = 3          # Number of retry attempts
LOG_LEVEL = INFO         # Logging level (DEBUG, INFO, WARNING, ERROR)
```

## 🛠️ Adding New Scrapers

1. Create new scraper class inheriting from `BaseScraper`
2. Implement `scrape()` and `parse_opportunity()` methods
3. Register in `main.py` orchestrator

Example:

```python
from scrapers.base_scraper import BaseScraper

class NewSourceScraper(BaseScraper):
    def __init__(self):
        super().__init__('New Source')
        self.base_url = 'https://example.com'
    
    def scrape(self):
        # Implementation
        pass
    
    def parse_opportunity(self, element):
        # Implementation
        pass
```

## 🔍 Monitoring

### Check database statistics

```python
from database.db import db
stats = db.get_stats()
print(stats)
```

### View recent opportunities

```sql
SELECT title, organization, deadline, source 
FROM opportunities 
ORDER BY scraped_at DESC 
LIMIT 10;
```

## 🐛 Troubleshooting

### Database connection issues
- Verify Supabase credentials in `.env`
- Check if Supabase is running: `docker ps`
- Test connection: `psql -h localhost -U postgres -d postgres`

### Scraper failures
- Check logs in `logs/` directory
- Verify internet connection
- Some sites may require API keys or authentication

### Missing dependencies
```bash
pip install -r requirements.txt --upgrade
```

## 📈 Performance

- **Average scraping time**: 5-10 minutes per session
- **Opportunities per run**: 100-500 (varies by source)
- **Database size**: ~1MB per 1000 opportunities

## 🔐 Security

- Never commit `.env` file
- Store credentials securely
- Use read-only database users when possible
- Respect robots.txt and rate limits

## 🚧 Future Enhancements

- [ ] Add more state-level sources
- [ ] Implement async scraping for better performance
- [ ] Add email notifications for new opportunities
- [ ] Create REST API for data access
- [ ] Build web dashboard for visualization
- [ ] Add AI-powered opportunity matching
- [ ] Implement full-text search

## 📞 Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review error messages
3. Verify configuration in `.env`

## 📄 License

Proprietary - Built for client project

## 👨‍💻 Developer

Built by Anas for Chris White
Project: RFP and Grants Scraping System
Timeline: 18 days
Budget: $1,200

---

**Last Updated**: March 2025
**Version**: 1.0.0
# opportunities-scraper
