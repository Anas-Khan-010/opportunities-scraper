import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config.settings import config
from utils.logger import logger

class Database:
    def __init__(self):
        self.connection_params = {
            'host': config.DB_HOST,
            'port': config.DB_PORT,
            'database': config.DB_NAME,
            'user': config.DB_USER,
            'password': config.DB_PASSWORD
        }
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = psycopg2.connect(**self.connection_params)
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def create_tables(self):
        """Create necessary database tables"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS opportunities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        
        CREATE INDEX IF NOT EXISTS idx_source ON opportunities(source);
        CREATE INDEX IF NOT EXISTS idx_deadline ON opportunities(deadline);
        CREATE INDEX IF NOT EXISTS idx_category ON opportunities(category);
        CREATE INDEX IF NOT EXISTS idx_scraped_at ON opportunities(scraped_at);
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_table_query)
                    logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise
    
    def opportunity_exists(self, source_url):
        """Check if opportunity already exists"""
        query = "SELECT id FROM opportunities WHERE source_url = %s"
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (source_url,))
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking opportunity existence: {e}")
            return False
    
    def insert_opportunity(self, data):
        """Insert new opportunity into database"""
        query = """
        INSERT INTO opportunities (
            title, organization, description, eligibility, funding_amount,
            deadline, category, location, source, source_url, opportunity_number,
            posted_date, document_urls, full_document
        ) VALUES (
            %(title)s, %(organization)s, %(description)s, %(eligibility)s, %(funding_amount)s,
            %(deadline)s, %(category)s, %(location)s, %(source)s, %(source_url)s, %(opportunity_number)s,
            %(posted_date)s, %(document_urls)s, %(full_document)s
        )
        ON CONFLICT (source_url) DO NOTHING
        RETURNING id
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, data)
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Inserted opportunity: {data['title']}")
                        return result[0]
                    else:
                        logger.debug(f"Duplicate skipped: {data['title']}")
                        return None
        except Exception as e:
            logger.error(f"Error inserting opportunity: {e}")
            return None
    
    def get_stats(self):
        """Get database statistics"""
        query = """
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT source) as sources,
            COUNT(CASE WHEN deadline > NOW() THEN 1 END) as active
        FROM opportunities
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    return dict(cur.fetchone())
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

db = Database()
