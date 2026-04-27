import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from database.db import db
from utils.logger import logger
from utils.pdf_parser import download_and_extract_pdf_text, heuristically_extract_fields


class OpportunityEnricher:
    """
    De-coupled engine to scan the database for incomplete opportunities
    and traverse their `source_url` detail pages / attached PDFs to extract
    deeper fields to achieve >90% completeness.
    """

    def __init__(self, limit=50):
        self.limit = limit
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        })
        self.enriched_count = 0

    def get_incomplete_opportunities(self):
        """Fetch rows missing crucial deep-level fields."""
        q = """
            SELECT id, source_url, description, eligibility, funding_amount, document_urls
            FROM opportunities
            WHERE source_url IS NOT NULL
              AND source_url != ''
              AND (
                  funding_amount IS NULL OR funding_amount = '' OR
                  eligibility IS NULL OR eligibility = '' OR
                  document_urls::text = '[]' OR document_urls IS NULL
              )
            ORDER BY created_at DESC
            LIMIT %s
        """
        try:
            from psycopg2.extras import RealDictCursor
            with db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(q, (self.limit,))
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching incomplete opportunities: {e}")
            return []

    def enrich(self):
        logger.info("Starting Field Enrichment Engine...")
        targets = self.get_incomplete_opportunities()
        logger.info(f"Found {len(targets)} incomplete opportunities to analyze.")

        for row in targets:
            try:
                self._enrich_single(row)
            except Exception as e:
                logger.warning(f"Error enriching opp {row['id']}: {e}")

        logger.info(f"Enrichment Complete. Successfully updated {self.enriched_count} records.")

    def _enrich_single(self, row):
        opp_id = row['id']
        url = row['source_url']

        if url.lower().endswith('.pdf'):
            text = download_and_extract_pdf_text(url)
            new_docs = [url]
        else:
            # HTML Page
            try:
                resp = self.session.get(url, timeout=12)
                if resp.status_code != 200:
                    return
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                text = soup.get_text(separator=' ')
                
                # Extract PDF links
                new_docs = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.lower().endswith('.pdf') or 'getfile' in href.lower() or 'download' in href.lower():
                        full_url = urljoin(url, href)
                        new_docs.append(full_url)
                
                # Pass into PDF parser if we are still missing fields
                if new_docs and (not row['funding_amount'] or not row['eligibility']):
                    # Only download the first relevant-looking PDF to save time
                    pdf_text = download_and_extract_pdf_text(new_docs[0])
                    text += " \n " + pdf_text
            except Exception as e:
                logger.debug(f"Failed to fetch HTML for enrichment {url}: {e}")
                return

        if not text:
            return

        # Use NLP Heuristics
        extracted = heuristically_extract_fields(text)
        
        # Merge results, prioritizing existing DB data
        update_data = {}
        if not row['funding_amount'] and extracted['funding_amount']:
            update_data['funding_amount'] = extracted['funding_amount']
        if not row['eligibility'] and extracted['eligibility']:
            update_data['eligibility'] = extracted['eligibility']
        if not row['description'] and extracted['description']:
            update_data['description'] = extracted['description']
        
        # Merge Document URLs
        import json
        current_docs_str = row['document_urls']
        current_docs = []
        if current_docs_str:
            try:
                current_docs = json.loads(current_docs_str)
            except:
                pass
                
        merged_docs = list(set(current_docs + new_docs))
        if len(merged_docs) > len(current_docs):
            update_data['document_urls'] = json.dumps(merged_docs)

        # Update if we have new data
        if update_data:
            self._update_db(opp_id, update_data)
            self.enriched_count += 1
            logger.info(f"Enriched ID {opp_id} | Fields: {list(update_data.keys())}")

        # Be polite to government servers
        time.sleep(1)

    def _update_db(self, opp_id, update_data):
        """Perform the UPDATE safely."""
        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        values = list(update_data.values()) + [opp_id]
        
        q = f"UPDATE opportunities SET {set_clause} WHERE id = %s"
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(q, values)
        except Exception as e:
            logger.error(f"DB update failed during enrichment: {e}")


if __name__ == "__main__":
    enricher = OpportunityEnricher(limit=20)
    enricher.enrich()
