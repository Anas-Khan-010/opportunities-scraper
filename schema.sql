-- RFP and Grants Database Schema
-- PostgreSQL / Supabase

-- Drop existing table if needed (use with caution)
-- DROP TABLE IF EXISTS opportunities CASCADE;

-- Create opportunities table
CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Core fields
    title TEXT NOT NULL,
    organization TEXT,
    description TEXT,
    eligibility TEXT,
    
    -- Financial info
    funding_amount TEXT,
    
    -- Dates
    deadline TIMESTAMP,
    posted_date TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Classification
    category TEXT,
    location TEXT,
    
    -- Source tracking
    source TEXT NOT NULL,
    source_url TEXT UNIQUE NOT NULL,
    opportunity_number TEXT,
    
    -- Documents
    document_urls TEXT[],
    full_document TEXT
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_source ON opportunities(source);
CREATE INDEX IF NOT EXISTS idx_deadline ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_category ON opportunities(category);
CREATE INDEX IF NOT EXISTS idx_scraped_at ON opportunities(scraped_at);
CREATE INDEX IF NOT EXISTS idx_posted_date ON opportunities(posted_date);
CREATE INDEX IF NOT EXISTS idx_organization ON opportunities(organization);

-- Create full-text search index
CREATE INDEX IF NOT EXISTS idx_title_search ON opportunities USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_description_search ON opportunities USING gin(to_tsvector('english', description));

-- Create view for active opportunities
CREATE OR REPLACE VIEW active_opportunities AS
SELECT 
    id,
    title,
    organization,
    funding_amount,
    deadline,
    category,
    location,
    source,
    source_url,
    posted_date
FROM opportunities
WHERE deadline > NOW() OR deadline IS NULL
ORDER BY posted_date DESC;

-- Create view for recent opportunities
CREATE OR REPLACE VIEW recent_opportunities AS
SELECT 
    id,
    title,
    organization,
    funding_amount,
    deadline,
    category,
    source,
    scraped_at
FROM opportunities
ORDER BY scraped_at DESC
LIMIT 100;

-- Create statistics view
CREATE OR REPLACE VIEW opportunity_stats AS
SELECT 
    COUNT(*) as total_opportunities,
    COUNT(DISTINCT source) as total_sources,
    COUNT(CASE WHEN deadline > NOW() THEN 1 END) as active_opportunities,
    COUNT(CASE WHEN deadline <= NOW() THEN 1 END) as expired_opportunities,
    COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '7 days' THEN 1 END) as new_this_week,
    MAX(scraped_at) as last_scrape_time
FROM opportunities;

-- Create function to clean old opportunities (optional)
CREATE OR REPLACE FUNCTION clean_old_opportunities(days_old INTEGER DEFAULT 365)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM opportunities
    WHERE deadline < NOW() - INTERVAL '1 day' * days_old
    AND deadline IS NOT NULL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Example queries

-- Get all active grants
-- SELECT * FROM active_opportunities WHERE category = 'Research';

-- Get opportunities by source
-- SELECT source, COUNT(*) FROM opportunities GROUP BY source ORDER BY COUNT(*) DESC;

-- Search opportunities by keyword
-- SELECT title, organization, deadline 
-- FROM opportunities 
-- WHERE to_tsvector('english', title || ' ' || COALESCE(description, '')) @@ to_tsquery('english', 'healthcare');

-- Get statistics
-- SELECT * FROM opportunity_stats;

-- Clean old opportunities (older than 1 year)
-- SELECT clean_old_opportunities(365);

COMMENT ON TABLE opportunities IS 'Stores RFP and grant opportunities from various sources';
COMMENT ON COLUMN opportunities.source_url IS 'Unique URL - prevents duplicates';
COMMENT ON COLUMN opportunities.document_urls IS 'Array of PDF/document URLs';
COMMENT ON COLUMN opportunities.full_document IS 'Extracted text from documents';
