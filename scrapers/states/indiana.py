"""
Indiana scrapers — in.gov

Two sources:

1. Indiana SBA Grants (Euna/eCivis Grants Network via iframe):
   https://www.in.gov/sba/grants/state-agency-grant-opportunities/
   The landing page embeds an iframe at
   https://gn.ecivis.com/GO/gn_redir/T/mk3lzl56q0ht/iframe/true which
   renders the public list of state agency grant opportunities grouped
   by agency.

2. IDOA Current Business Opportunities (RFPs/RFQs/IFBs):
   https://www.in.gov/idoa/procurement/current-business-opportunities/index.html
   A single HTML table of open sourcing events.
"""

import io
import re
import zipfile
from urllib.parse import urljoin

import requests

from scrapers.base_scraper import BaseScraper
from parsers.parser_utils import DocumentParser, OpportunityEnricher
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


# ======================================================================
# Indiana SBA Grants (eCivis iframe)
# ======================================================================


class IndianaSBAGrantsScraper(BaseScraper):
    """Scrapes Indiana state-agency grant opportunities from the eCivis iframe."""

    LANDING_URL = "https://www.in.gov/sba/grants/state-agency-grant-opportunities/"
    IFRAME_URL = "https://gn.ecivis.com/GO/gn_redir/T/mk3lzl56q0ht/iframe/true"
    BASE = "https://gn.ecivis.com"

    def __init__(self):
        super().__init__("Indiana SBA Grants")

    def scrape(self):
        logger.info("Starting %s scraper (eCivis iframe)...", self.source_name)
        try:
            self._scrape_iframe()
        except Exception as exc:
            logger.error("Indiana SBA: fatal error: %s", exc)
        self.log_summary()
        return self.opportunities

    def _scrape_iframe(self):
        resp = self.fetch_page(self.IFRAME_URL)
        if resp is None:
            logger.error("Indiana SBA: failed to fetch iframe")
            return

        soup = self.parse_html(resp.text)

        # The page is structured as: <h2>Agency Name</h2><table>...</table> pairs.
        # Skip "Programs available for Solicitation" (it's an h2 heading not an agency).
        agency = None
        for element in soup.find_all(["h1", "h2", "h3", "table"]):
            if element.name in ("h1", "h2", "h3"):
                text = clean_text(element.get_text())
                if not text:
                    continue
                if (
                    text.lower().startswith("state of")
                    or text.lower().startswith("programs available")
                    or text.lower() == "programs"
                ):
                    continue
                agency = text
                continue

            if element.name == "table":
                rows = element.find_all("tr")
                if not rows:
                    continue
                header_cells = rows[0].find_all(["th", "td"])
                header_text = " ".join(
                    c.get_text(strip=True).lower() for c in header_cells
                )
                if "solicitation name" not in header_text:
                    continue

                for row in rows[1:]:
                    if self.reached_limit():
                        return
                    opp = self.parse_opportunity(row)
                    if not opp:
                        continue
                    opp["organization"] = agency or opp.get("organization")
                    self._enrich_detail(opp)
                    if opp.get("document_urls"):
                        self.enrich_from_documents(opp)

                    if not opp.get("opportunity_number"):
                        m = re.search(r"/T/([^/]+)/", opp.get("source_url", ""))
                        if m:
                            opp["opportunity_number"] = m.group(1)[:64]

                    if not opp.get("eligibility"):
                        opp["eligibility"] = (
                            "See grant detail page for eligibility requirements; "
                            "Indiana state-agency grants typically target local "
                            "governments, non-profits, and eligible agencies."
                        )
                    if not opp.get("funding_amount"):
                        opp["funding_amount"] = "Amount varies — see grant detail page"

                    self.add_opportunity(opp)

    def parse_opportunity(self, row):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                return None

            link = cells[0].find("a")
            title = clean_text(cells[0].get_text())
            if not title:
                return None

            href = link.get("href", "") if link else ""
            if href:
                detail_url = href if href.startswith("http") else urljoin(self.BASE, href)
            else:
                detail_url = self.LANDING_URL

            start_str = clean_text(cells[1].get_text())
            end_str = clean_text(cells[2].get_text())
            posted_date = parse_date(start_str) if start_str else None
            deadline = None
            if end_str and end_str.lower() not in ("n/a", "tbd", ""):
                deadline = parse_date(end_str)

            return {
                "title": title,
                "organization": "State of Indiana",
                "description": None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, ""),
                "location": "Indiana",
                "source": self.source_name,
                "source_url": detail_url,
                "opportunity_number": None,
                "posted_date": posted_date,
                "document_urls": [],
                "opportunity_type": "grant",
            }
        except Exception as exc:
            logger.error("Indiana SBA: row parse error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Detail-page enrichment
    # ------------------------------------------------------------------

    _SECTION_HEADERS = {"overview", "eligibility", "financial", "contact", "files"}
    _LABELS = {
        "ID:", "Title:", "Application Start Date:", "Application End Date:",
        "CFDA/ALN:", "Reference URL:", "Summary:",
        "Eligible Applicants:", "Eligibility Notes:",
        "Award Amount:", "Number of Awards:", "Average Award Size:",
        "Matching Required:", "Matching Type:", "Financial Notes:",
        "Agency/Department:", "Contact/Help:", "Office:", "Program Contact:",
        "Application Address:", "Contact Notes:",
        "Files:", "File Notes:",
        "(min)", "(max)",
    }

    def _parse_ecivis_fields(self, text):
        """Line-based parse of eCivis detail text into a {label: [values]} dict."""
        lines = [ln.strip() for ln in text.split("\n")]
        fields = {}
        current_label = None
        current_values = []

        def flush():
            if current_label is not None:
                fields[current_label] = [v for v in current_values if v]

        for ln in lines:
            if not ln:
                continue
            if ln.lower() in self._SECTION_HEADERS:
                flush()
                current_label, current_values[:] = None, []
                continue
            if ln in self._LABELS or ln.endswith(":") and len(ln) < 40:
                flush()
                current_label = ln.rstrip(":").strip()
                current_values = []
                continue
            if current_label is not None:
                current_values.append(ln)
        flush()
        return fields

    def _enrich_detail(self, opp):
        url = opp.get("source_url", "")
        if not url or "gn.ecivis.com" not in url:
            return
        try:
            resp = self.fetch_page(url)
            if resp is None:
                return
            soup = self.parse_html(resp.text)
            text = soup.get_text(separator="\n", strip=True)
            fields = self._parse_ecivis_fields(text)

            def first(label):
                vals = fields.get(label, [])
                return vals[0].strip() if vals else ""

            def joined(label, sep=" "):
                return sep.join(fields.get(label, [])).strip()

            opp_id = first("ID")
            if opp_id and opp_id.lower() != "n/a":
                opp["opportunity_number"] = opp_id

            summary = joined("Summary", "\n")
            if summary:
                opp["description"] = summary[:2000]

            elig_parts = []
            applicants = joined("Eligible Applicants", ", ")
            if applicants and applicants.lower() != "n/a":
                elig_parts.append(f"Eligible Applicants: {applicants}")
            elig_notes = joined("Eligibility Notes", "\n")
            if elig_notes and elig_notes.lower() != "n/a":
                elig_parts.append(elig_notes)
            if elig_parts:
                opp["eligibility"] = "\n\n".join(elig_parts)[:1500]

            award_vals = fields.get("Award Amount", [])
            amt_min = award_vals[0].strip() if len(award_vals) >= 1 else ""
            amt_max = award_vals[1].strip() if len(award_vals) >= 2 else ""
            avg_award = first("Average Award Size")
            financial_notes = joined("Financial Notes", "\n")
            parts = []
            if amt_min and amt_min.lower() != "n/a":
                if amt_max and amt_max.lower() != "n/a":
                    parts.append(f"{amt_min} – {amt_max}")
                else:
                    parts.append(amt_min)
            if avg_award and avg_award.lower() != "n/a":
                parts.append(f"avg {avg_award}")
            if parts:
                opp["funding_amount"] = "; ".join(parts)[:200]
            elif financial_notes:
                inferred = extract_funding_amount(financial_notes)
                if inferred:
                    opp["funding_amount"] = inferred
            if not opp.get("funding_amount") and financial_notes:
                opp["funding_amount"] = financial_notes[:200]

            if financial_notes and opp.get("description"):
                if "Award" not in opp["description"] and len(opp["description"]) < 1800:
                    opp["description"] = (opp["description"] + "\n\nFinancial: " + financial_notes)[:2000]

            agency = first("Agency/Department")
            if agency:
                opp["organization"] = agency

            doc_urls = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx", ".xls")):
                    full = href if href.startswith("http") else urljoin(self.BASE, href)
                    if full not in doc_urls:
                        doc_urls.append(full)
            for notes_label in ("Contact Notes", "File Notes"):
                for ln in fields.get(notes_label, []):
                    m = re.search(r"https?://\S+", ln)
                    if m:
                        link = m.group(0).rstrip(".,);")
                        if link.lower().endswith((".pdf", ".doc", ".docx")) and link not in doc_urls:
                            doc_urls.append(link)
            if doc_urls:
                opp["document_urls"] = doc_urls[:10]
        except Exception as exc:
            logger.debug("Indiana SBA: detail enrich failed for %s: %s", url, exc)


# ======================================================================
# Indiana IDOA RFPs / Business Opportunities
# ======================================================================


class IndianaIDOAScraper(BaseScraper):
    """Scrapes Indiana IDOA current business opportunities (RFPs/RFQs)."""

    LISTING_URL = (
        "https://www.in.gov/idoa/procurement/current-business-opportunities/index.html"
    )
    BASE = "https://www.in.gov"

    def __init__(self):
        super().__init__("Indiana IDOA Procurement")

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        try:
            self._scrape_listing()
        except Exception as exc:
            logger.error("Indiana IDOA: fatal error: %s", exc)
        self.log_summary()
        return self.opportunities

    def _scrape_listing(self):
        resp = self.fetch_page(self.LISTING_URL)
        if resp is None:
            logger.error("Indiana IDOA: failed to fetch listing page")
            return

        soup = self.parse_html(resp.text)
        target_table = None
        for table in soup.find_all("table"):
            header_cells = table.find("tr").find_all(["th", "td"]) if table.find("tr") else []
            header_text = " ".join(c.get_text(strip=True).lower() for c in header_cells)
            if "event name" in header_text and "agency" in header_text:
                target_table = table
                break

        if target_table is None:
            logger.warning("Indiana IDOA: events table not found")
            return

        rows = target_table.find_all("tr")[1:]
        logger.info("Indiana IDOA: %d event rows found", len(rows))

        for row in rows:
            if self.reached_limit():
                break
            opp = self.parse_opportunity(row)
            if opp:
                self._enrich_from_zip(opp)
                if not opp.get("eligibility"):
                    opp["eligibility"] = (
                        "Open to vendors registered on the Indiana Supplier Portal. "
                        "See solicitation documents (ZIP) for event-specific requirements."
                    )
                if not opp.get("funding_amount"):
                    opp["funding_amount"] = "See solicitation documents for estimated value"
                self.add_opportunity(opp)

    def parse_opportunity(self, row):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 5:
                return None

            name_cell = cells[0]
            title_link = name_cell.find("a")
            title = clean_text(title_link.get_text()) if title_link else ""
            if not title:
                parts = [s.strip() for s in name_cell.get_text("|", strip=True).split("|")]
                parts = [p for p in parts if p and p.lower() != "bid documents"]
                title = parts[0] if parts else ""
            if not title:
                return None

            agency = clean_text(cells[1].get_text())
            event_id = clean_text(cells[2].get_text())
            desc_raw = clean_text(cells[3].get_text(" ", strip=True))
            deadline_str = clean_text(cells[4].get_text())
            contact = clean_text(cells[5].get_text()) if len(cells) > 5 else ""

            deadline = parse_date(deadline_str) if deadline_str else None

            doc_urls = []
            for a in name_cell.find_all("a", href=True):
                href = a["href"].strip()
                if not href or href.startswith("mailto:"):
                    continue
                full = href if href.startswith("http") else urljoin(self.BASE, href)
                if full.lower().endswith((".zip", ".pdf", ".doc", ".docx")) and full not in doc_urls:
                    doc_urls.append(full)

            source_url = doc_urls[0] if doc_urls else f"{self.BASE}/idoa/procurement/current-business-opportunities/#{event_id}"

            description_parts = []
            if desc_raw:
                description_parts.append(desc_raw[:1500])
            if contact:
                description_parts.append(f"Contact: {contact}")
            description = " — ".join(description_parts) if description_parts else None

            return {
                "title": title,
                "organization": agency or "State of Indiana",
                "description": description,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, desc_raw),
                "location": "Indiana",
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": event_id or None,
                "posted_date": None,
                "document_urls": doc_urls[:10],
                "opportunity_type": "rfp",
            }
        except Exception as exc:
            logger.error("Indiana IDOA: row parse error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # ZIP bid-documents enrichment
    # ------------------------------------------------------------------

    def _enrich_from_zip(self, opp):
        """Download the bid-documents ZIP, read PDFs inside, backfill fields."""
        zip_urls = [u for u in opp.get("document_urls") or [] if u.lower().endswith(".zip")]
        if not zip_urls:
            return
        try:
            resp = requests.get(
                zip_urls[0],
                timeout=45,
                headers={"User-Agent": "Mozilla/5.0 (compatible; OppScraper/1.0)"},
            )
            if resp.status_code != 200 or not resp.content:
                return
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except Exception as exc:
            logger.debug("Indiana IDOA: zip fetch failed for %s: %s", zip_urls[0], exc)
            return

        inner_pdfs = []
        combined_text = ""
        base = zip_urls[0].rsplit("/", 1)[0]
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/") or info.file_size == 0:
                continue
            inner_pdfs.append(f"{zip_urls[0]}#{name}")
            if not name.lower().endswith(".pdf"):
                continue
            try:
                with zf.open(info) as fp:
                    data = fp.read()
                text = DocumentParser.extract_text_from_pdf(io.BytesIO(data))
                if text:
                    combined_text += text + "\n\n"
                if len(combined_text) > 30000:
                    break
            except Exception as exc:
                logger.debug("Indiana IDOA: pdf in zip read failed (%s): %s", name, exc)

        if inner_pdfs:
            merged = opp.get("document_urls") or []
            for p in inner_pdfs[:10]:
                if p not in merged:
                    merged.append(p)
            opp["document_urls"] = merged[:15]

        if not combined_text:
            return

        if not opp.get("eligibility"):
            elig = OpportunityEnricher._extract_eligibility(combined_text)
            if elig:
                opp["eligibility"] = elig

        if not opp.get("funding_amount"):
            amt = extract_funding_amount(combined_text, require_keyword=True)
            if amt:
                opp["funding_amount"] = amt

        if not opp.get("opportunity_number"):
            num = OpportunityEnricher._extract_opp_number(combined_text)
            if num:
                opp["opportunity_number"] = num

        posted = self._extract_posted_date(combined_text)
        if posted and not opp.get("posted_date"):
            opp["posted_date"] = posted

        desc = opp.get("description") or ""
        if len(desc) < 400:
            snippet = combined_text[:1500].strip()
            if snippet:
                opp["description"] = (desc + "\n\n" + snippet)[:2000] if desc else snippet[:2000]

    @staticmethod
    def _extract_posted_date(text):
        """Extract a likely 'posted/issue' date from RFP PDF text."""
        if not text:
            return None
        patterns = [
            r"(?:Issue(?:d)?|Posted|Release(?:d)?|Publication)\s*Date\s*[:\-]?\s*([A-Z][a-z]+\s+\d{1,2},\s*\d{4})",
            r"(?:Issue(?:d)?|Posted|Release(?:d)?|Publication)\s*Date\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                d = parse_date(m.group(1))
                if d:
                    return d
        return None


# ======================================================================
# Factory
# ======================================================================


def get_indiana_scrapers():
    return [IndianaSBAGrantsScraper(), IndianaIDOAScraper()]
