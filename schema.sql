-- ============================================================================
-- Opportunities Scraper — Database Schema
-- Target: Supabase (PostgreSQL 15+)
-- ============================================================================
-- Run this once in the Supabase SQL Editor to create (or recreate) the table.
-- If the table already exists, DROP it first:
--   DROP TABLE IF EXISTS opportunities CASCADE;
-- ============================================================================

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
    scraped_at        TIMESTAMP DEFAULT NOW(),
    created_at        TIMESTAMP DEFAULT NOW()
);

-- ── Performance indexes ──────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_source           ON opportunities(source);
CREATE INDEX IF NOT EXISTS idx_deadline         ON opportunities(deadline);
CREATE INDEX IF NOT EXISTS idx_category         ON opportunities(category);
CREATE INDEX IF NOT EXISTS idx_scraped_at       ON opportunities(scraped_at);
CREATE INDEX IF NOT EXISTS idx_opportunity_type ON opportunities(opportunity_type);
CREATE INDEX IF NOT EXISTS idx_location         ON opportunities(location);
CREATE INDEX IF NOT EXISTS idx_posted_date      ON opportunities(posted_date);

-- Full-text search on title + description
CREATE INDEX IF NOT EXISTS idx_fts ON opportunities
    USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));

-- ── Useful views ─────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW active_opportunities AS
SELECT * FROM opportunities
WHERE deadline IS NULL OR deadline > NOW()
ORDER BY posted_date DESC NULLS LAST;

CREATE OR REPLACE VIEW recent_opportunities AS
SELECT * FROM opportunities
ORDER BY scraped_at DESC
LIMIT 500;

CREATE OR REPLACE VIEW opportunity_stats AS
SELECT
    source,
    opportunity_type,
    COUNT(*)                                          AS total,
    COUNT(CASE WHEN deadline > NOW() THEN 1 END)     AS active,
    MIN(posted_date)                                  AS earliest_posted,
    MAX(posted_date)                                  AS latest_posted
FROM opportunities
GROUP BY source, opportunity_type
ORDER BY total DESC;

-- ── Maintenance function ─────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION clean_old_opportunities(days_old INTEGER DEFAULT 180)
RETURNS INTEGER AS $$
DECLARE
    deleted INTEGER;
BEGIN
    DELETE FROM opportunities
    WHERE deadline < NOW() - (days_old || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$ LANGUAGE plpgsql;
