"""
Illinois GATA/CSFA scraper — omb.illinois.gov

Scrapes the Catalog of State Financial Assistance (CSFA) program list
from the Illinois Grant Accountability and Transparency Act (GATA) portal.

The listing page is server-rendered ASP.NET HTML:
  https://omb.illinois.gov/PUBLIC/GATA/CSFA/PROGRAMLIST.ASPX

Each row links to a detail page (Program.aspx?csfa=<id>) that contains
richer information: description, eligibility, funding details, and
associated documents.

Transport: plain HTTP (requests + BeautifulSoup) — no Selenium needed.

DNS note: some networks cannot resolve omb.illinois.gov via the local
stub resolver.  The scraper detects this and falls back to a public DNS
lookup (dig @8.8.8.8) so the connection still succeeds.
"""

import re
import socket
import subprocess
import urllib.parse

import urllib3.util.connection as _urllib3_conn

from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity, extract_funding_amount

BASE_URL = "https://omb.illinois.gov/PUBLIC/GATA/CSFA"
LISTING_URL = f"{BASE_URL}/PROGRAMLIST.ASPX"
_IL_HOST = "omb.illinois.gov"


def _resolve_via_public_dns(hostname, dns_server="8.8.8.8"):
    """Resolve *hostname* via a public DNS server using ``dig``."""
    try:
        out = subprocess.check_output(
            ["dig", "+short", hostname, f"@{dns_server}"],
            timeout=10, text=True,
        )
        for line in out.strip().splitlines():
            line = line.strip().rstrip(".")
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", line):
                return line
    except Exception:
        pass
    return None


class _DnsFallbackPatch:
    """Context manager that monkey-patches urllib3's ``create_connection``
    so that a specific hostname is routed to a fallback IP when the local
    DNS resolver cannot handle it.  SNI / TLS hostname verification still
    uses the original hostname.
    """

    def __init__(self, hostname, fallback_ip):
        self._hostname = hostname
        self._fallback_ip = fallback_ip
        self._original_create_connection = None

    def __enter__(self):
        original = _urllib3_conn.create_connection
        hostname = self._hostname
        fallback_ip = self._fallback_ip

        def _patched_create_connection(address, *args, **kwargs):
            host, port = address
            if host == hostname:
                address = (fallback_ip, port)
            return original(address, *args, **kwargs)

        self._original_create_connection = original
        _urllib3_conn.create_connection = _patched_create_connection
        return self

    def __exit__(self, *exc):
        if self._original_create_connection is not None:
            _urllib3_conn.create_connection = self._original_create_connection


class IllinoisCSFAscraper(BaseScraper):
    """Scrapes Illinois CSFA grant programs with detail page enrichment."""

    def __init__(self):
        super().__init__("Illinois CSFA")
        self.max_programs = getattr(
            __import__('config.settings', fromlist=['config']).config,
            'IL_CSFA_MAX_PROGRAMS', 200
        )
        self._dns_patch = None

    def _ensure_dns(self):
        """If local DNS cannot resolve the IL host, install a fallback."""
        try:
            socket.getaddrinfo(_IL_HOST, 443)
            logger.debug("Illinois: local DNS resolves %s OK", _IL_HOST)
            return
        except socket.gaierror:
            pass

        logger.warning("Illinois: local DNS cannot resolve %s, trying public DNS...", _IL_HOST)
        ip = _resolve_via_public_dns(_IL_HOST)
        if not ip:
            logger.error("Illinois: public DNS fallback also failed for %s", _IL_HOST)
            return

        logger.info("Illinois: using DNS fallback %s -> %s", _IL_HOST, ip)
        self._dns_patch = _DnsFallbackPatch(_IL_HOST, ip)
        self._dns_patch.__enter__()

    def _release_dns(self):
        if self._dns_patch is not None:
            self._dns_patch.__exit__(None, None, None)
            self._dns_patch = None

    def scrape(self):
        logger.info("Starting Illinois CSFA scraper (HTML listing + detail pages)...")
        self._ensure_dns()
        try:
            self._scrape_listing()
        finally:
            self._release_dns()
        self.log_summary()
        return self.opportunities

    def _scrape_listing(self):
        resp = self.fetch_page(LISTING_URL)
        if not resp:
            logger.error("Failed to fetch Illinois CSFA listing page")
            return

        soup = self.parse_html(resp.text)

        table = soup.find('table')
        if not table:
            logger.warning("No table found on Illinois CSFA listing page")
            return

        rows = table.find_all('tr')
        data_rows = rows[1:]
        if not data_rows:
            logger.info("No programs listed on Illinois CSFA page")
            return

        logger.info(f"Illinois CSFA: found {len(data_rows)} program rows")

        count = 0
        for row in data_rows:
            if self.reached_limit() or count >= self.max_programs:
                break

            opp = self._parse_listing_row(row)
            if opp:
                self._enrich_from_detail(opp)
                if opp.get('document_urls'):
                    self.enrich_from_documents(opp)
                self.add_opportunity(opp)
                count += 1

        logger.info(f"Illinois CSFA: processed {count} programs")

    def _parse_listing_row(self, row):
        """Parse a single row from the CSFA program list table.

        Columns: Program Title | CSFA Number | Agency | ActiveAwards | ActiveOpportunities
        """
        cells = row.find_all('td')
        if len(cells) < 3:
            return None

        title_cell = cells[0]
        link = title_cell.find('a')
        title = clean_text(link.get_text()) if link else clean_text(title_cell.get_text())
        if not title or len(title) < 3:
            return None

        detail_url = LISTING_URL
        if link and link.get('href'):
            href = link['href']
            detail_url = href if href.startswith('http') else urllib.parse.urljoin(BASE_URL + '/', href)

        csfa_number = clean_text(cells[1].get_text()) if len(cells) > 1 else None
        agency_raw = clean_text(cells[2].get_text()) if len(cells) > 2 else None

        agency_name = agency_raw or 'State of Illinois'
        agency_code_match = re.match(r'^(.+?)\s*\(\d+\)\s*$', agency_name) if agency_name else None
        if agency_code_match:
            agency_name = agency_code_match.group(1).strip()

        AGENCY_MAP = {
            'AGE': 'Dept. on Aging',
            'AG': 'Dept. of Agriculture',
            'DHS': 'Dept. of Human Services',
            'DPH': 'Dept. of Public Health',
            'DOT': 'Dept. of Transportation',
            'DCEO': 'Dept. of Commerce & Economic Opportunity',
            'DNR': 'Dept. of Natural Resources',
            'ISBE': 'State Board of Education',
            'IEMA': 'Emergency Management Agency',
        }
        for code, name in AGENCY_MAP.items():
            if agency_name.upper().startswith(code):
                agency_name = f"Illinois {name}"
                break

        active_awards = None
        active_opps = None
        if len(cells) > 3:
            active_awards = clean_text(cells[3].get_text())
        if len(cells) > 4:
            active_opps = clean_text(cells[4].get_text())

        desc_parts = []
        if agency_raw:
            desc_parts.append(f"Agency: {agency_raw}")
        if active_awards and active_awards != '0':
            desc_parts.append(f"Active Awards: {active_awards}")
        if active_opps and active_opps != '0':
            desc_parts.append(f"Active Opportunities: {active_opps}")

        category = categorize_opportunity(title, ' '.join(desc_parts))

        return {
            'title': title,
            'organization': agency_name,
            'description': '; '.join(desc_parts) if desc_parts else None,
            'eligibility': None,
            'funding_amount': None,
            'deadline': None,
            'category': category,
            'location': 'Illinois',
            'source': self.source_name,
            'source_url': detail_url,
            'opportunity_number': csfa_number,
            'posted_date': None,
            'document_urls': [],
            'opportunity_type': 'grant',
        }

    def _enrich_from_detail(self, opp):
        """Fetch the CSFA Program detail page and extract richer data."""
        detail_url = opp.get('source_url', '')
        if not detail_url or 'Program.aspx' not in detail_url:
            return

        try:
            resp = self.fetch_page(detail_url)
            if not resp:
                return

            soup = self.parse_html(resp.text)

            detail_sections = soup.find_all(['div', 'table', 'section'])
            full_text = soup.get_text(separator='\n', strip=True)

            if not opp.get('description') or len(opp['description']) < 50:
                desc = self._extract_section(full_text, [
                    'Program Description', 'Description', 'Program Summary', 'Objective',
                ])
                if desc:
                    existing = opp.get('description') or ''
                    opp['description'] = f"{desc}\n{existing}".strip()[:2000]

            if not opp.get('eligibility'):
                elig = self._extract_section(full_text, [
                    'Eligibility Requirements', 'Eligible Applicants',
                    'Who May Apply', 'Eligibility',
                ])
                if elig:
                    opp['eligibility'] = elig[:1000]

            if not opp.get('funding_amount'):
                funding = self._extract_section(full_text, [
                    'Award Amount', 'Funding Amount', 'Grant Amount',
                    'Total Program Budget', 'Award Range',
                ])
                if funding:
                    amount = extract_funding_amount(funding)
                    if amount:
                        opp['funding_amount'] = amount
                    elif len(funding) < 200:
                        opp['funding_amount'] = funding

            deadline_text = self._extract_section(full_text, [
                'Application Deadline', 'Due Date', 'Submission Deadline',
                'Response Due By', 'Deadline', 'Closing Date',
            ])
            if deadline_text and not opp.get('deadline'):
                # Try to clean common debris like "by 5:00 PM"
                clean_date = re.sub(r'\s+by\s+\d{1,2}:\d{2}\s*(?:AM|PM|EDT|CDT|EST|CST).*$', '', deadline_text, flags=re.I).strip()
                opp['deadline'] = parse_date(clean_date[:100])

            doc_urls = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href'].lower()
                if any(href.endswith(ext) for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    full_url = a_tag['href']
                    if not full_url.startswith('http'):
                        full_url = urllib.parse.urljoin(detail_url, full_url)
                    doc_urls.append(full_url)
            if doc_urls:
                opp['document_urls'] = doc_urls[:5]

            if opp.get('description'):
                opp['category'] = categorize_opportunity(
                    opp['title'], opp['description']
                )

        except Exception as exc:
            logger.debug(f"Illinois: detail enrichment failed for {detail_url}: {exc}")

    def _extract_section(self, full_text, header_keywords):
        """Find a labeled section in the page text and return its content.
        Uses a more flexible regex to handle different spacing and multi-line values.
        """
        for keyword in header_keywords:
            # Matches "Keyword: Value" or "Keyword\nValue"
            # Captures until next uppercase field or double newline
            pattern = re.compile(
                rf'{re.escape(keyword)}\s*[:\-—]?\s*(.*?)(?:\n\s*\n|\n[A-Z][A-Za-z ]{{3,}}[:\-—]|\Z)',
                re.IGNORECASE | re.DOTALL,
            )
            m = pattern.search(full_text)
            if m:
                text = m.group(1).strip()
                if text and len(text) > 1:
                    # Clean up internal excessive whitespace
                    return re.sub(r'\s+', ' ', text)[:1500]
        return None

    def parse_opportunity(self, element):
        return None


def get_illinois_scrapers():
    return [IllinoisCSFAscraper()]
