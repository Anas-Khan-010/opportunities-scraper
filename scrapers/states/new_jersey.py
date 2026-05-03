"""
New Jersey DHS RFP/RFA/RFI scraper — nj.gov/humanservices

Scrapes Requests for Proposals, Applications, and Information from the
NJ Department of Human Services notices page.

NOTE: The NJ DHS portal sits behind Imperva/Incapsula bot protection.
Imperva's anti-headless JS sensor reliably crashes headless Chrome,
but plain ``requests`` (with browsery headers) is allowed through.
We therefore use requests-only here — no Selenium driver is needed.

Three separate HTML tables are parsed:
  1. Request For Proposals (RFPs)
  2. Request For Applications (RFAs)
  3. Request For Information / Letters of Interest (RFI/RLI)

Most detailed information lives in linked PDFs. PDF enrichment extracts
description, eligibility, and funding_amount from each RFP's document.

Source: https://www.nj.gov/humanservices/notices/grants/proposals/
"""

import re
import urllib.parse

from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


PORTAL_URL = "https://www.nj.gov/humanservices/notices/grants/proposals/"
NJ_BASE = "https://www.nj.gov"


class NewJerseyDHSScraper(BaseScraper):
    """Scrapes NJ DHS RFPs/RFAs/RFIs with PDF enrichment (requests-only)."""

    def __init__(self):
        super().__init__("New Jersey DHS")

    def scrape(self):
        logger.info("Starting New Jersey DHS scraper (requests + PDF enrichment)...")
        # Imperva blocks bare User-Agents, so make sure our session reads as a
        # real browser session (BaseScraper already rotates these per attempt).
        # We also set a Referer to the parent landing page to look natural.
        self.session.headers.update({
            'Referer': 'https://www.nj.gov/humanservices/',
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,*/*;q=0.8'
            ),
        })

        resp = self.fetch_page(PORTAL_URL, timeout=30)
        if resp is None:
            logger.error("New Jersey: failed to fetch portal page")
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(resp.text)
        tables = soup.find_all('table')
        logger.info(f"New Jersey DHS: found {len(tables)} tables on page")

        section_types = ['rfp', 'rfa', 'rfi']
        for idx, table in enumerate(tables):
            section = section_types[idx] if idx < len(section_types) else 'rfp'
            rows = table.find_all('tr')
            data_rows = rows[1:]

            if not data_rows:
                continue

            logger.info(f"New Jersey DHS: parsing {section.upper()} table — {len(data_rows)} rows")

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self._parse_row(row, section)
                if opp:
                    if opp.get('document_urls'):
                        self.enrich_from_documents(opp)
                    if not opp.get('opportunity_number'):
                        self._extract_opp_number_from_urls(opp)
                    self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def _parse_row(self, row, section_type):
        """Parse a single table row from any of the three NJ DHS tables."""
        cells = row.find_all('td')
        if len(cells) < 2:
            return None

        row_text = row.get_text(strip=True)
        if not row_text or len(row_text) < 10:
            return None

        division = clean_text(cells[0].get_text()) if cells[0] else None

        title_cell = cells[1] if len(cells) > 1 else None
        if not title_cell:
            return None

        cell_text = title_cell.get_text(strip=True)
        if not cell_text:
            return None

        links = title_cell.find_all('a', href=True)
        title = None
        source_url = PORTAL_URL
        doc_urls = []

        for link in links:
            href = link.get('href', '').strip()
            link_text = clean_text(link.get_text())

            if not href:
                continue

            full_url = href if href.startswith('http') else urllib.parse.urljoin(NJ_BASE, href)

            if any(href.lower().endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                doc_urls.append(full_url)
                if not title and link_text and len(link_text) > 5:
                    link_lower = link_text.lower()
                    if not any(kw in link_lower for kw in ('budget', 'template', 'q&a', 'q & a', 'faq')):
                        title = link_text
                        source_url = full_url
            else:
                if not title and link_text and len(link_text) > 5:
                    title = link_text
                    source_url = full_url

        if not title:
            title_text = clean_text(title_cell.get_text())
            if title_text and len(title_text) > 5:
                title = title_text[:300]

        if not title or len(title.strip()) < 5:
            return None

        deadline = None
        notify_date = None

        if section_type in ('rfp', 'rfa'):
            if len(cells) > 2:
                deadline_text = clean_text(cells[2].get_text())
                if deadline_text and deadline_text.lower() not in ('tbd', 'n/a', ''):
                    deadline = parse_date(deadline_text)
            if len(cells) > 3:
                notify_text = clean_text(cells[3].get_text())
                if notify_text and notify_text.lower() not in ('tbd', 'n/a', ''):
                    notify_date = notify_text
        elif section_type == 'rfi':
            if len(cells) > 2:
                notify_text = clean_text(cells[2].get_text())
                if notify_text:
                    date_match = re.search(
                        r'(\w+ \d{1,2},?\s*\d{4})', notify_text
                    )
                    if date_match:
                        deadline = parse_date(date_match.group(1))

        desc_parts = []
        if division:
            desc_parts.append(f"Division: {division}")
        desc_parts.append(f"Type: {section_type.upper()}")
        if notify_date:
            desc_parts.append(f"Notify Date: {notify_date}")
        description = '; '.join(desc_parts)

        opp_type = 'rfp' if section_type in ('rfp', 'rfa') else 'rfi'
        category = categorize_opportunity(title, description)

        return {
            'title': title,
            'organization': f"NJ DHS - {division}" if division else 'NJ Dept. of Human Services',
            'description': description,
            'eligibility': None,
            'funding_amount': None,
            'deadline': deadline,
            'category': category,
            'location': 'New Jersey',
            'source': self.source_name,
            'source_url': source_url,
            'opportunity_number': None,
            'posted_date': None,
            'document_urls': doc_urls[:5],
            'opportunity_type': opp_type,
        }

    @staticmethod
    def _extract_opp_number_from_urls(opp):
        """Try to extract an RFP/RFA number from document URL filenames."""
        for url in (opp.get('document_urls') or []):
            m = re.search(
                r'(?:RFP|RFA|RFQ|RFI)\s*[-_]?\s*([\w\-]+)',
                url.split('/')[-1], re.IGNORECASE,
            )
            if m:
                opp['opportunity_number'] = m.group(0).rstrip('.,;')
                return

    def parse_opportunity(self, element):
        return None


def get_new_jersey_scrapers():
    return [NewJerseyDHSScraper()]
