"""
North Dakota Grants scraper — WebGrants (grants.nd.gov)

Scrapes active state grant funding opportunities from North Dakota's
official WebGrants portal.  Parses the public storefront listing table,
then visits each detail page to extract the full description, award
amount range, program officer, attachments, and website links.

Source: https://grants.nd.gov/
Listing: https://grants.nd.gov/storefrontFOList.do
"""

import re

from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity, extract_funding_amount


class NorthDakotaGrantsScraper(BaseScraper):
    """Scrapes North Dakota grant opportunities from the WebGrants HTML listing."""

    LISTING_URL = "https://grants.nd.gov/storefrontFOList.do"
    DETAIL_BASE = "https://grants.nd.gov/"

    def __init__(self):
        super().__init__("North Dakota Grants")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (WebGrants HTML)...")
        self._scrape_listing()
        self.log_summary()
        return self.opportunities

    def _scrape_listing(self):
        try:
            resp = self.fetch_page(self.LISTING_URL)
            if not resp:
                logger.error("Failed to fetch ND WebGrants listing page")
                return

            soup = self.parse_html(resp.text)
            table = soup.find("table")
            if not table:
                logger.warning("No table found on ND WebGrants listing page")
                return

            rows = table.find_all("tr")
            data_rows = rows[1:]
            if not data_rows:
                logger.info("No grant opportunities currently listed for North Dakota")
                return

            for row in data_rows:
                opp = self.parse_opportunity(row)
                if opp:
                    self._enrich_from_detail(opp)
                    if opp.get('document_urls'):
                        self.enrich_from_documents(opp)
                    self.add_opportunity(opp)
                if self.reached_limit():
                    break

            logger.info(f"  Parsed {len(data_rows)} rows from listing table")

        except Exception as e:
            logger.error(f"Error scraping ND WebGrants listing: {e}")

    def _enrich_from_detail(self, opp):
        """Fetch the WebGrants detail page and extract richer fields."""
        detail_url = opp.get('source_url', '')
        if not detail_url or detail_url == self.DETAIL_BASE:
            return

        try:
            resp = self.fetch_page(detail_url)
            if not resp:
                return

            soup = self.parse_html(resp.text)
            full_text = soup.get_text(separator='\n', strip=True)

            desc_section = soup.find('h5', string=re.compile(r'Description', re.I))
            if desc_section:
                desc_parts = []
                for sib in desc_section.find_all_next():
                    if sib.name in ('h3', 'h4', 'h5') and sib != desc_section:
                        break
                    text = sib.get_text(strip=True)
                    if text and text != 'Description':
                        desc_parts.append(text)
                if desc_parts:
                    rich_desc = '\n\n'.join(desc_parts)[:2000]
                    opp['description'] = rich_desc

            award_match = re.search(
                r'Award\s+Amount\s+Range\s*[:\n]?\s*(.+?)(?:\n|$)',
                full_text, re.IGNORECASE,
            )
            if award_match:
                raw = award_match.group(1).strip()
                if raw.lower() not in ('not applicable', 'n/a', ''):
                    opp['funding_amount'] = raw

            if not opp.get('funding_amount'):
                amount = extract_funding_amount(full_text)
                if amount:
                    opp['funding_amount'] = amount

            if not opp.get('eligibility'):
                for pattern in [r'Eligib', r'Who\s+May\s+Apply', r'Applicant\s+Information',
                                r'Eligible\s+Applicants?']:
                    elig_section = soup.find('h5', string=re.compile(pattern, re.I))
                    if elig_section:
                        elig_parts = []
                        for sib in elig_section.find_all_next():
                            if sib.name in ('h3', 'h4', 'h5') and sib != elig_section:
                                break
                            text = sib.get_text(strip=True)
                            if text and text != elig_section.get_text(strip=True):
                                elig_parts.append(text)
                        if elig_parts:
                            opp['eligibility'] = '\n'.join(elig_parts)[:1000]
                            break

            if not opp.get('eligibility'):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if elig:
                    opp['eligibility'] = elig

            officer_match = re.search(
                r'Program\s+Officer\s*[:\n]?\s*(.+?)(?:\n|Phone)',
                full_text, re.IGNORECASE,
            )
            if officer_match:
                officer = officer_match.group(1).strip()
                if officer and opp.get('description'):
                    opp['description'] = f"{opp['description']}\n\nProgram Officer: {officer}"

            doc_urls = []
            attach_section = soup.find('h5', string=re.compile(r'Attachments', re.I))
            if attach_section:
                table = attach_section.find_next('table')
                if table:
                    for a in table.find_all('a', href=True):
                        href = a['href']
                        full_url = href if href.startswith('http') else self.DETAIL_BASE + href.lstrip('/')
                        if full_url not in doc_urls:
                            doc_urls.append(full_url)

            links_section = soup.find('h5', string=re.compile(r'Website\s+[Ll]inks', re.I))
            if links_section:
                table = links_section.find_next('table')
                if table:
                    for a in table.find_all('a', href=True):
                        href = a['href'].strip()
                        if href.startswith('http') and href not in doc_urls:
                            doc_urls.append(href)

            if doc_urls:
                opp['document_urls'] = doc_urls[:10]

        except Exception as exc:
            logger.debug(f"ND: detail enrichment failed for {detail_url}: {exc}")

    def parse_opportunity(self, row):
        """Parse a single table row.

        Column layout:
          0: ID  |  1: Status  |  2: Categorical Area  |  3: Agency
          4: Program Area  |  5: Title (with link)  |  6: Posted Date
          7: Due Date
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 6:
                return None

            opp_id = clean_text(cells[0].get_text())
            status = clean_text(cells[1].get_text())
            category_area = clean_text(cells[2].get_text())
            agency = clean_text(cells[3].get_text())
            program_area = clean_text(cells[4].get_text())

            title_cell = cells[5]
            link = title_cell.find("a")
            title = clean_text(link.get_text()) if link else clean_text(title_cell.get_text())
            if not title:
                return None

            source_url = self.DETAIL_BASE
            if link and link.get("href"):
                href = link["href"]
                source_url = href if href.startswith("http") else self.DETAIL_BASE + href.lstrip("/")

            posted_str = clean_text(cells[6].get_text()) if len(cells) > 6 else None
            deadline_str = clean_text(cells[7].get_text()) if len(cells) > 7 else None

            posted_date = parse_date(posted_str) if posted_str else None
            deadline = None
            if deadline_str and deadline_str.lower() not in ("not applicable", "n/a", "tbd", ""):
                deadline = parse_date(deadline_str)

            description_parts = []
            if agency:
                description_parts.append(f"Agency: {agency}")
            if program_area:
                description_parts.append(f"Program: {program_area}")
            if category_area:
                description_parts.append(f"Category: {category_area}")
            if status:
                description_parts.append(f"Status: {status}")
            description = "; ".join(description_parts) if description_parts else None

            category = categorize_opportunity(
                title, (description or "") + " " + (category_area or "")
            )

            return {
                "title": title,
                "organization": agency or "State of North Dakota",
                "description": description,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": category,
                "location": "North Dakota",
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": opp_id,
                "posted_date": posted_date,
                "document_urls": [],
                "opportunity_type": "grant",
            }
        except Exception as e:
            logger.error(f"Error parsing ND WebGrants row: {e}")
            return None


def get_north_dakota_scrapers():
    """Create scraper instances for North Dakota Grants."""
    return [NorthDakotaGrantsScraper()]
