"""
Pennsylvania scrapers — pa.gov

Two sources:

1. DCED Programs — https://dced.pa.gov/programs/
   Public listing of all DCED funding programs. Each `<div class="project_top">`
   block has an `<h3>` with the program name + link to a detail page, and a
   sibling `<div class="project_text">` with the program summary.

2. PA eMarketplace Solicitations — https://www.emarketplace.state.pa.us/
   The public search endpoint (Search.aspx?SearchType=Solicitation) returns
   an HTML page containing a result table with solicitation #, title,
   description, agency, start/due dates, and a link to the detail page.
"""

import re
from urllib.parse import urljoin, urlparse

from scrapers.base_scraper import BaseScraper
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


# ======================================================================
# PA DCED Programs
# ======================================================================


class PennsylvaniaDCEDScraper(BaseScraper):
    """Scrapes the PA DCED Programs listing."""

    LISTING_URL = "https://dced.pa.gov/programs/"
    BASE = "https://dced.pa.gov"

    def __init__(self):
        super().__init__("Pennsylvania DCED Programs")

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        resp = self.fetch_page(self.LISTING_URL)
        if resp is None:
            logger.error("%s: could not fetch listing", self.source_name)
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(resp.text)
        cards = soup.find_all("div", class_="programs_cnt")
        logger.info("%s: %d program cards found", self.source_name, len(cards))

        for card in cards:
            if self.reached_limit():
                break
            opp = self.parse_opportunity(card)
            if opp:
                self._enrich_detail(opp)
                if opp.get('document_urls'):
                    self.enrich_from_documents(opp)
                self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, card):
        try:
            top = card.find("div", class_="project_top")
            if not top:
                return None
            link = top.find("a", href=True)
            if not link:
                return None

            title = clean_text(link.get_text())
            href = link["href"].strip()
            url = href if href.startswith("http") else urljoin(self.BASE, href)
            if not title:
                return None

            desc_div = card.find("div", class_="project_text")
            description = clean_text(desc_div.get_text(" ", strip=True)) if desc_div else None
            if description:
                description = description[:2000]

            posted_date = None
            date_span = card.find("span", class_="date")
            if date_span:
                posted_date = parse_date(clean_text(date_span.get_text()))

            slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or None

            return {
                "title": title[:300],
                "organization": "PA Department of Community & Economic Development",
                "description": description,
                "eligibility": None,
                "funding_amount": None,
                "deadline": None,
                "category": categorize_opportunity(title, description or ""),
                "location": "Pennsylvania",
                "source": self.source_name,
                "source_url": url,
                "opportunity_number": slug,
                "posted_date": posted_date,
                "document_urls": [],
                "opportunity_type": "grant",
            }
        except Exception as exc:
            logger.error("%s: parse error: %s", self.source_name, exc)
            return None

    # ------------------------------------------------------------------
    # Detail-page enrichment
    # ------------------------------------------------------------------

    _SECTION_LABELS = ("overview", "eligibility", "uses", "funding", "how to apply",
                       "program guidelines", "terms")

    def _parse_sections(self, soup):
        """Parse <h3/h4/h5/h6>Label</h6> sections into a dict of label -> text.

        DCED detail pages mix heading levels — older programs use ``h3``
        while newer ones use ``h6``. We match only our known section labels
        to avoid picking up navigation headings like "More Programs".
        """
        sections = {}
        for h in soup.find_all(["h3", "h4", "h5", "h6"]):
            label = (clean_text(h.get_text()) or "").lower()
            if label not in self._SECTION_LABELS:
                continue
            chunks = []
            for sib in h.next_siblings:
                name = getattr(sib, "name", None)
                if name in ("h6", "h5", "h4", "h3", "h2"):
                    break
                if name in ("p", "ul", "ol", "div"):
                    txt = clean_text(sib.get_text(" ", strip=True))
                    if txt:
                        chunks.append(txt)
            if chunks:
                sections[label] = "\n\n".join(chunks)
        return sections

    def _enrich_detail(self, opp):
        url = opp.get("source_url", "")
        if not url:
            return
        try:
            resp = self.fetch_page(url)
            if resp is None:
                return
            soup = self.parse_html(resp.text)
            sections = self._parse_sections(soup)

            overview = sections.get("overview")
            uses = sections.get("uses")
            desc_parts = []
            if overview:
                desc_parts.append(overview)
            if uses:
                desc_parts.append(f"Uses: {uses}")
            if desc_parts:
                opp["description"] = "\n\n".join(desc_parts)[:2000]
            elif not opp.get("description"):
                # Fallback: grab any <p> inside main
                main = soup.find("main") or soup.find("article")
                if main:
                    paras = [clean_text(p.get_text(" ", strip=True)) for p in main.find_all("p")]
                    paras = [p for p in paras if p and len(p) > 40]
                    if paras:
                        opp["description"] = "\n\n".join(paras[:3])[:2000]

            eligibility = sections.get("eligibility")
            if eligibility:
                opp["eligibility"] = eligibility[:1500]

            funding = sections.get("funding")
            if funding:
                opp["funding_amount"] = (extract_funding_amount(funding) or funding)[:300]

            # Try to detect a deadline anywhere on the page (most DCED programs
            # are rolling but some advertise a specific due date).
            body_text = "\n".join(sections.values()) if sections else soup.get_text("\n", strip=True)
            m = re.search(
                r"(?i)(?:deadline|applications?\s+(?:are\s+)?due|apply\s+by|close[sd]?\s+on"
                r"|due\s+date|submission\s+deadline)\s*[:\-]?\s*"
                r"([A-Z][a-z]+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
                body_text,
            )
            if m and not opp.get("deadline"):
                d = parse_date(m.group(1))
                if d:
                    opp["deadline"] = d

            # Program categories / funding types as supplemental organization/category
            program_cats = soup.find(lambda t: t.name in ("h4", "h3")
                                     and "program categories" in t.get_text(strip=True).lower())
            if program_cats:
                cat_text = clean_text(program_cats.find_next(["ul", "p", "div"]).get_text(" ", strip=True)) \
                    if program_cats.find_next(["ul", "p", "div"]) else ""
                if cat_text and not opp.get("category"):
                    opp["category"] = cat_text[:100]

            # Collect document URLs: explicit PDFs + WPDM download links +
            # anchors whose text matches "Guidelines/Application/FAQ".
            doc_urls = []
            main = soup.find("main") or soup.find("article") or soup
            keywords = ("guideline", "application", "faq", "fact sheet",
                        "brochure", "manual", "instructions")
            for a in main.find_all("a", href=True):
                href = a["href"]
                text = (a.get_text() or "").strip().lower()
                is_doc = (
                    href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx"))
                    or "/download/" in href.lower()
                    or "wpdmdl=" in href.lower()
                    or any(k in text for k in keywords)
                )
                if not is_doc:
                    continue
                full = href if href.startswith("http") else urljoin(self.BASE, href)
                if full not in doc_urls:
                    doc_urls.append(full)
            if doc_urls:
                opp["document_urls"] = doc_urls[:10]

            if not opp.get("eligibility"):
                opp["eligibility"] = (
                    "See program guidelines for specific eligibility. DCED "
                    "programs typically serve PA municipalities, non-profits, "
                    "and qualifying for-profit businesses."
                )
            if not opp.get("funding_amount"):
                opp["funding_amount"] = "See program guidelines — amounts vary"
        except Exception as exc:
            logger.debug("%s: detail enrich failed for %s: %s", self.source_name, url, exc)


# ======================================================================
# PA eMarketplace Solicitations
# ======================================================================


class PennsylvaniaEMarketplaceScraper(BaseScraper):
    """Scrapes the PA eMarketplace active solicitations via Search.aspx."""

    SEARCH_URL = "https://www.emarketplace.state.pa.us/Search.aspx?SearchType=Solicitation"
    BASE = "https://www.emarketplace.state.pa.us/"

    def __init__(self):
        super().__init__("Pennsylvania eMarketplace")

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        resp = self.fetch_page(self.SEARCH_URL)
        if resp is None:
            logger.error("%s: could not fetch search page", self.source_name)
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(resp.text)

        sid_links = soup.find_all(
            "a",
            href=lambda h: h and "Solicitations.aspx?SID=" in h,
        )
        seen_rows = set()
        rows_to_parse = []
        for link in sid_links:
            tr = link.find_parent("tr")
            if tr is None or id(tr) in seen_rows:
                continue
            seen_rows.add(id(tr))
            rows_to_parse.append(tr)

        logger.info(
            "%s: %d solicitation rows found", self.source_name, len(rows_to_parse)
        )

        for row in rows_to_parse:
            if self.reached_limit():
                break
            opp = self.parse_opportunity(row)
            if opp:
                self._enrich_detail(opp)
                if opp.get("document_urls"):
                    self.enrich_from_documents(opp)
                self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        try:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 9:
                cells = row.find_all(["td", "th"])
            if len(cells) < 9:
                return None

            sol_link = cells[0].find("a", href=True)
            sol_number = clean_text(cells[0].get_text())
            sol_type = clean_text(cells[1].get_text())
            title = clean_text(cells[2].get_text())
            description = clean_text(cells[3].get_text(" ", strip=True))
            agency = clean_text(cells[4].get_text())
            start_str = clean_text(cells[7].get_text()) if len(cells) > 7 else ""
            due_str = clean_text(cells[8].get_text()) if len(cells) > 8 else ""

            if not title or not sol_number:
                return None

            if sol_link:
                href = sol_link["href"].strip()
                detail_url = href if href.startswith("http") else urljoin(self.BASE, href)
            else:
                detail_url = f"{self.BASE}Solicitations.aspx?SID={sol_number}"

            posted_date = parse_date(start_str) if start_str else None
            deadline = parse_date(due_str) if due_str else None

            return {
                "title": title[:300],
                "organization": agency or "Commonwealth of Pennsylvania",
                "description": description[:1500] if description else None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, description or ""),
                "location": "Pennsylvania",
                "source": self.source_name,
                "source_url": detail_url,
                "opportunity_number": sol_number,
                "posted_date": posted_date,
                "document_urls": [],
                "opportunity_type": "rfp" if sol_type.upper() in ("RFP", "SFP") else "bid",
            }
        except Exception as exc:
            logger.error("%s: row parse error: %s", self.source_name, exc)
            return None

    # ------------------------------------------------------------------
    # Detail-page enrichment (full description + attachments)
    # ------------------------------------------------------------------

    def _enrich_detail(self, opp):
        url = opp.get("source_url", "")
        if not url or "Solicitations.aspx" not in url:
            return
        try:
            resp = self.fetch_page(url)
            if resp is None:
                return
            soup = self.parse_html(resp.text)
            text = soup.get_text("\n", strip=True)

            def after_label(label, max_len=2000):
                m = re.search(r"(?mi)^\s*" + re.escape(label) + r"\s*:?\s*$", text)
                if not m:
                    return None
                start = m.end()
                rest = text[start:start + max_len].lstrip("\n")
                # stop at next ALL-CAPS heading or known label lines
                stop_pat = re.compile(
                    r"\n(?:Department Information|Contact Information|Solicitation Information"
                    r"|Opening Location|County|Delivery Location|Duration|First Name"
                    r"|Solicitation Start Date|Solicitation Due Date|Amended Date"
                    r"|No\. of Addendums|Additional Information)\s*:?\s*(?:\n|$)"
                )
                m2 = stop_pat.search(rest)
                if m2:
                    rest = rest[:m2.start()]
                return rest.strip() or None

            desc = after_label("Description", 3000)
            if desc:
                opp["description"] = desc[:2000]

            dept = after_label("Department/Agency", 200)
            if dept:
                opp["organization"] = dept.splitlines()[0].strip()[:200]

            # Collect PDF/attachment URLs
            doc_urls = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "FileDownload.aspx" in href or href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx")):
                    full = href if href.startswith("http") else urljoin(self.BASE, href)
                    if full not in doc_urls:
                        doc_urls.append(full)
            if doc_urls:
                opp["document_urls"] = doc_urls[:10]

            if not opp.get("eligibility"):
                opp["eligibility"] = (
                    "Open to any vendor registered on the PA Supplier Portal / "
                    "PA eMarketplace. See solicitation documents for any "
                    "solicitation-specific qualifications."
                )
        except Exception as exc:
            logger.debug("%s: detail enrich failed for %s: %s", self.source_name, url, exc)


# ======================================================================
# Factory
# ======================================================================


def get_pennsylvania_scrapers():
    return [PennsylvaniaDCEDScraper(), PennsylvaniaEMarketplaceScraper()]
