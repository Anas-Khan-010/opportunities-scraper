"""
Virginia scrapers — virginia.gov

Two sources:

1. VA DRPT WebGrants —
   https://grants.drpt.virginia.gov/storefrontFOList.do
   Same Dulles Tech WebGrants platform as North Dakota. Uses plain HTTP
   to pull the public storefront listing table, then visits each detail
   page for richer fields.

2. eVA Virginia Business Opportunities (VBO) —
   https://mvendor.cgieva.com/Vendor/public/AllOpportunities.jsp
   Published solicitations (IFBs/RFPs/sole-source notices). This endpoint
   is protected by AWS WAF with a JS challenge, so we load it via
   undetected-chromedriver and parse the opportunity table. If the WAF
   refuses the session we log and move on gracefully.
"""

import re
import time

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


# ======================================================================
# VA DRPT WebGrants (plain HTTP — WebGrants same as ND)
# ======================================================================


class VirginiaDRPTScraper(BaseScraper):
    """Scrapes Virginia DRPT WebGrants storefront (same platform as ND)."""

    LISTING_URL = "https://grants.drpt.virginia.gov/storefrontFOList.do"
    DETAIL_BASE = "https://grants.drpt.virginia.gov/"

    def __init__(self):
        super().__init__("Virginia DRPT Grants")

    def scrape(self):
        logger.info("Starting %s scraper (WebGrants HTML)...", self.source_name)
        self._scrape_listing()
        self.log_summary()
        return self.opportunities

    def _scrape_listing(self):
        try:
            resp = self.fetch_page(self.LISTING_URL)
            if not resp:
                logger.error("Failed to fetch VA DRPT WebGrants listing")
                return

            soup = self.parse_html(resp.text)
            table = soup.find("table")
            if not table:
                logger.warning("No table on VA DRPT WebGrants listing")
                return

            data_rows = table.find_all("tr")[1:]
            if not data_rows:
                logger.info("No grant opportunities currently listed for VA DRPT")
                return

            for row in data_rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    self._enrich_from_detail(opp)
                    if opp.get("document_urls"):
                        self.enrich_from_documents(opp)
                    self.add_opportunity(opp)

            logger.info("  Parsed %d rows from VA DRPT listing", len(data_rows))
        except Exception as exc:
            logger.error("Error scraping VA DRPT WebGrants: %s", exc)

    def _enrich_from_detail(self, opp):
        detail_url = opp.get("source_url", "")
        if not detail_url or detail_url == self.DETAIL_BASE:
            return

        try:
            resp = self.fetch_page(detail_url)
            if not resp:
                return

            soup = self.parse_html(resp.text)
            full_text = soup.get_text(separator="\n", strip=True)

            desc_section = soup.find("h5", string=re.compile(r"Description", re.I))
            if desc_section:
                desc_parts = []
                for sib in desc_section.next_siblings:
                    if getattr(sib, "name", None) in ("h1", "h2", "h3", "h4", "h5"):
                        break
                    text = clean_text(sib.get_text()) if hasattr(sib, "get_text") else ""
                    if text and text not in desc_parts:
                        desc_parts.append(text)
                if desc_parts:
                    opp["description"] = "\n\n".join(desc_parts)[:2000]

            award_match = re.search(
                r"Award\s+Amount\s+Range\s*[:\n]?\s*(.+?)(?:\n|$)",
                full_text, re.IGNORECASE,
            )
            if award_match:
                raw = award_match.group(1).strip()
                if raw.lower() not in ("not applicable", "n/a", ""):
                    opp["funding_amount"] = raw

            if not opp.get("funding_amount"):
                amount = extract_funding_amount(full_text)
                if amount:
                    opp["funding_amount"] = amount

            if not opp.get("eligibility"):
                for pattern in (
                    r"Eligib", r"Who\s+May\s+Apply",
                    r"Applicant\s+Information", r"Eligible\s+Applicants?",
                ):
                    elig_section = soup.find("h5", string=re.compile(pattern, re.I))
                    if elig_section:
                        elig_parts = []
                        for sib in elig_section.find_all_next():
                            if sib.name in ("h3", "h4", "h5") and sib != elig_section:
                                break
                            text = sib.get_text(strip=True)
                            if text and text != elig_section.get_text(strip=True):
                                elig_parts.append(text)
                        if elig_parts:
                            opp["eligibility"] = "\n".join(elig_parts)[:1000]
                            break

            if not opp.get("eligibility"):
                try:
                    from parsers.parser_utils import OpportunityEnricher
                    elig = OpportunityEnricher._extract_eligibility(full_text)
                    if elig:
                        opp["eligibility"] = elig
                except Exception:
                    pass

            if not opp.get("eligibility") and opp.get("description"):
                m = re.search(
                    r"(?i)eligible\s+(?:applicants?|entities|organizations?|recipients?)\s+"
                    r"(?:are|include|may\s+be)[^.]{10,400}\.",
                    opp["description"],
                )
                if m:
                    opp["eligibility"] = m.group(0).strip()[:1000]

            if not opp.get("funding_amount"):
                source_text = opp.get("description") or full_text
                m = re.search(
                    r"(?i)(?:reimbursement|funding|award|grant)s?\s+(?:is|are|of|up\s+to|range[sd]?\s*(?:from|between)?)\s+[^.]{3,200}\.",
                    source_text,
                )
                if m:
                    opp["funding_amount"] = m.group(0).strip()[:250]
                elif re.search(r"(?i)up\s+to\s+\d+%", source_text):
                    mm = re.search(r"(?i)[^.]*up\s+to\s+\d+%[^.]*\.", source_text)
                    if mm:
                        opp["funding_amount"] = mm.group(0).strip()[:250]

            doc_urls = []
            attach_section = soup.find("h5", string=re.compile(r"Attachments", re.I))
            if attach_section:
                att_table = attach_section.find_next("table")
                if att_table:
                    for a in att_table.find_all("a", href=True):
                        href = a["href"]
                        full_url = (
                            href if href.startswith("http")
                            else self.DETAIL_BASE + href.lstrip("/")
                        )
                        if full_url not in doc_urls:
                            doc_urls.append(full_url)

            if doc_urls:
                opp["document_urls"] = doc_urls[:10]

            if not opp.get("eligibility"):
                opp["eligibility"] = (
                    "See WebGrants opportunity page for specific eligibility; "
                    "DRPT grants typically serve Virginia transit agencies, "
                    "localities, and qualifying private-sector partners."
                )
            if not opp.get("funding_amount"):
                opp["funding_amount"] = "Amount varies — see WebGrants opportunity page"

        except Exception as exc:
            logger.debug("VA DRPT: detail enrichment failed for %s: %s",
                         detail_url, exc)

    def parse_opportunity(self, row):
        """Row layout: ID | Status | Categorical Area | Agency | Program Area | Title | Posted | Due."""
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
                source_url = (
                    href if href.startswith("http")
                    else self.DETAIL_BASE + href.lstrip("/")
                )

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

            return {
                "title": title[:300],
                "organization": agency or "Virginia Department of Rail and Public Transportation",
                "description": description,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(
                    title, (description or "") + " " + (category_area or "")
                ),
                "location": "Virginia",
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": opp_id,
                "posted_date": posted_date,
                "document_urls": [],
                "opportunity_type": "grant",
            }
        except Exception as exc:
            logger.error("VA DRPT: row parse error: %s", exc)
            return None


# ======================================================================
# eVA Virginia Business Opportunities (Selenium)
# ======================================================================


class VirginiaEVAScraper(BaseScraper):
    """Scrapes eVA VBO via Selenium (WAF-protected JSP table)."""

    LANDING_URL = "https://eva.virginia.gov/search.html"
    LISTING_URL = "https://mvendor.cgieva.com/Vendor/public/AllOpportunities.jsp"
    BASE = "https://mvendor.cgieva.com"

    def __init__(self):
        super().__init__("Virginia eVA VBO")

    def scrape(self):
        logger.info("Starting %s scraper (Selenium)...", self.source_name)
        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("%s: Selenium driver unavailable", self.source_name)
            self.log_summary()
            return self.opportunities

        try:
            # Landing page is a soft preflight (cookie/Referer for the JSP).
            # Wrap in a short timeout so a slow CDN doesn't burn a minute.
            try:
                driver.set_page_load_timeout(20)
                driver.get(self.LANDING_URL)
                time.sleep(2)
            except Exception as exc:
                logger.debug("%s: landing-page preflight skipped: %s",
                             self.source_name, exc)
            finally:
                try:
                    driver.set_page_load_timeout(45)
                except Exception:
                    pass
            # Re-bind in case safe_get rebuilt the driver during landing.
            driver = SeleniumDriverManager._driver or driver
            driver.get(self.LISTING_URL)
            time.sleep(12)
            driver = SeleniumDriverManager._driver or driver
            html = driver.page_source
        except Exception as exc:
            logger.error("%s: failed to load VBO: %s", self.source_name, exc)
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(html)
        page_text = (soup.get_text(" ", strip=True) or "")[:500]
        if (
            (soup.title and "403" in soup.title.get_text())
            or "403 Forbidden" in page_text
            or "AWS WAF" in page_text
        ):
            logger.warning(
                "%s: WAF/403 detected — the eVA public JSP is blocking "
                "this IP. Try again from a residential connection.",
                self.source_name,
            )
            self.log_summary()
            return self.opportunities

        target_table = None
        for table in soup.find_all("table"):
            header_row = table.find("tr")
            if not header_row:
                continue
            hdr = " ".join(
                c.get_text(strip=True).lower()
                for c in header_row.find_all(["th", "td"])
            )
            if ("solicitation" in hdr or "opportunity" in hdr) and (
                "title" in hdr or "description" in hdr or "status" in hdr
            ):
                target_table = table
                break

        if target_table is None:
            logger.warning("%s: no opportunities table found", self.source_name)
            self.log_summary()
            return self.opportunities

        rows = target_table.find_all("tr")[1:]
        logger.info("%s: %d rows found", self.source_name, len(rows))

        for row in rows:
            if self.reached_limit():
                break
            opp = self.parse_opportunity(row)
            if not opp:
                continue
            try:
                self._enrich_detail(driver, opp)
                if opp.get("document_urls"):
                    self.enrich_from_documents(opp)
            except Exception as exc:
                logger.debug("VA eVA: detail enrichment failed for %s: %s",
                             opp.get("source_url"), exc)
            self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def _enrich_detail(self, driver, opp):
        """Fetch the eVA detail page and backfill eligibility/funding/deadline.

        eVA's public JSP shows a simple key/value layout; we tolerate
        missing labels by checking each one independently.
        """
        url = opp.get("source_url", "")
        if not url or "cgieva.com" not in url:
            return
        try:
            driver.get(url)
            time.sleep(4)
            # Re-bind in case safe_get rebuilt the driver during this hop.
            driver = SeleniumDriverManager._driver or driver
            soup = self.parse_html(driver.page_source)
        except Exception as exc:
            logger.debug("VA eVA: selenium load failed %s: %s", url, exc)
            return

        text = soup.get_text("\n", strip=True)
        if "403 Forbidden" in text or "AWS WAF" in text:
            return

        def _after(label, max_len=600):
            pat = re.compile(rf"(?mi)^\s*{re.escape(label)}\s*:?\s*$")
            m = pat.search(text)
            if not m:
                pat2 = re.compile(rf"(?i)\b{re.escape(label)}\s*[:\-]\s*([^\n]+)")
                m2 = pat2.search(text)
                return m2.group(1).strip() if m2 else None
            return text[m.end():m.end() + max_len].strip() or None

        desc = _after("Description", 1200) or _after("Summary", 800)
        if desc and (not opp.get("description") or len(opp.get("description") or "") < 200):
            opp["description"] = desc[:2000]

        if not opp.get("deadline"):
            for label in ("Response Deadline", "Closing Date", "Due Date", "Bid Open Date"):
                val = _after(label, 80)
                if val:
                    d = parse_date(val.split("\n")[0])
                    if d:
                        opp["deadline"] = d
                        break

        if not opp.get("eligibility"):
            elig = _after("Eligibility", 800) or _after("Set-Aside", 200)
            if elig:
                opp["eligibility"] = elig[:1000]

        if not opp.get("funding_amount"):
            from utils.helpers import extract_funding_amount
            amt = extract_funding_amount(text, require_keyword=True)
            if amt:
                opp["funding_amount"] = amt

        org = _after("Issuing Agency", 120) or _after("Buyer Agency", 120)
        if org:
            opp["organization"] = org.split("\n")[0].strip()[:200]

        doc_urls = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx", ".zip")):
                full = href if href.startswith("http") else self.BASE + "/" + href.lstrip("/")
                if full not in doc_urls:
                    doc_urls.append(full)
        if doc_urls:
            opp["document_urls"] = doc_urls[:10]

        if not opp.get("eligibility"):
            opp["eligibility"] = (
                "Open to vendors registered with eVA in good standing; see "
                "solicitation documents for any procurement-specific qualifications."
            )

    def parse_opportunity(self, row):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                return None

            texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            link = None
            for c in cells:
                a = c.find("a", href=True)
                if a:
                    href = (a.get("href") or "").strip()
                    if href and not href.lower().startswith(("javascript:", "mailto:", "#")):
                        link = a
                        break

            href = link["href"].strip() if link else ""
            detail_url = href if href.startswith("http") else (self.BASE + "/" + href.lstrip("/")) if href else ""
            title = (
                clean_text(link.get_text()) if link else None
            ) or next((t for t in texts if t), "")
            if not title:
                return None

            deadline = None
            posted = None
            opp_number = None
            description_parts = []
            for t in texts:
                if not t:
                    continue
                if not deadline:
                    d = parse_date(t)
                    if d:
                        deadline = d
                        continue
                if re.match(r"^[A-Z0-9\-]{5,30}$", t) and not opp_number:
                    opp_number = t
                    continue
                description_parts.append(t)

            anchor = opp_number or title[:80].replace(" ", "_")
            source_url = detail_url or f"{self.LISTING_URL}#{anchor}"

            return {
                "title": title[:300],
                "organization": "Commonwealth of Virginia",
                "description": " — ".join(description_parts)[:1500] if description_parts else None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, ""),
                "location": "Virginia",
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": opp_number,
                "posted_date": posted,
                "document_urls": [],
                "opportunity_type": "rfp",
            }
        except Exception as exc:
            logger.error("%s: row parse error: %s", self.source_name, exc)
            return None


# ======================================================================
# Factory
# ======================================================================


def get_virginia_scrapers():
    return [VirginiaDRPTScraper(), VirginiaEVAScraper()]
