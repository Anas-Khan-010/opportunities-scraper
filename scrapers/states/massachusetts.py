"""
Massachusetts scrapers — mass.gov / commbuys.com

Two sources:

1. MA Community Grant Finder — https://www.mass.gov/lists/community-grant-finder
   Public directory of active state grant programs. mass.gov returns 403 to
   bot-style requests, so we load the page with Selenium and parse the
   ``ma__download-link`` / ``ma__decorative-link`` cards.

2. COMMBUYS Advanced Bid Search —
   https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml
   JSF public search. Clicking the default "Search" button returns a
   results table with up to 25 open bids (Bid Solicitation #, Organization,
   Buyer, Description, Bid Opening Date, link to bidDetail.sda).
"""

import re
import time
from urllib.parse import urljoin, urlparse

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


# ======================================================================
# MA Community Grant Finder (Selenium)
# ======================================================================


class MassachusettsGrantsScraper(BaseScraper):
    """Scrapes mass.gov Community Grant Finder via Selenium."""

    LISTING_URL = "https://www.mass.gov/lists/community-grant-finder"
    BASE = "https://www.mass.gov"

    def __init__(self):
        super().__init__("Massachusetts Community Grant Finder")

    def scrape(self):
        logger.info("Starting %s scraper (Selenium)...", self.source_name)
        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("%s: Selenium driver unavailable", self.source_name)
            self.log_summary()
            return self.opportunities

        try:
            driver.get(self.LISTING_URL)
            time.sleep(6)
            soup = self.parse_html(driver.page_source)
        except Exception as exc:
            logger.error("%s: failed to load page: %s", self.source_name, exc)
            self.log_summary()
            return self.opportunities

        cards = soup.find_all("div", class_="ma__download-link")
        logger.info("%s: %d grant cards found", self.source_name, len(cards))

        if not cards:
            self._parse_fallback_links(soup)
        else:
            for card in cards:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(card)
                if opp:
                    self._enrich_detail(driver, opp)
                    if opp.get("document_urls"):
                        self.enrich_from_documents(opp)
                    self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, card):
        try:
            title_el = card.find(class_="ma__download-link__title")
            link_el = title_el.find("a", href=True) if title_el else card.find("a", href=True)
            if not link_el:
                return None

            title = clean_text(link_el.get_text())
            href = link_el["href"].strip()
            url = href if href.startswith("http") else urljoin(self.BASE, href)

            desc_el = card.find(class_="ma__download-link__description")
            description = clean_text(desc_el.get_text(" ", strip=True)) if desc_el else None

            slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or None

            return {
                "title": title[:300],
                "organization": "Commonwealth of Massachusetts",
                "description": description[:1500] if description else None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": None,
                "category": categorize_opportunity(title, description or ""),
                "location": "Massachusetts",
                "source": self.source_name,
                "source_url": url,
                "opportunity_number": slug,
                "posted_date": None,
                "document_urls": [],
                "opportunity_type": "grant",
            }
        except Exception as exc:
            logger.error("%s: parse error: %s", self.source_name, exc)
            return None

    # ------------------------------------------------------------------
    # Per-grant detail enrichment (reuses the shared Selenium driver)
    # ------------------------------------------------------------------

    _ELIG_RE = re.compile(
        r"(?i)(?:^|\n)(?:eligib(?:le|ility)(?:\s+(?:applicants?|entities|organizations?"
        r"|requirements?|criteria))?|who\s+(?:can|may|is\s+eligible\s+to)\s+apply)"
        r"\s*:?\s*\n([\s\S]{30,1500}?)(?=\n(?:[A-Z][A-Za-z &]{2,40}:?\n|$))"
    )
    _DEADLINE_RE = re.compile(
        r"(?i)(?:deadline|apply\s*by|due\s*date|applications?\s+(?:are\s+)?due|"
        r"accepted\s+(?:through|until))\s*[:\-]?\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
    )
    _FUNDING_RE = re.compile(
        r"(?i)(?:funding|award|grant)\s+(?:amount|size|range)?\s*:?\s*([^\n]{5,200})"
    )

    _ELIG_HEADINGS = re.compile(
        r"(?i)(?:applicant\s+)?eligibility|eligible\s+(?:applicants?|entities|organizations?)"
        r"|who\s+(?:may|can|is\s+eligible\s+to)\s+apply",
    )
    _FUNDING_HEADINGS = re.compile(
        r"(?i)funding|award\s+amount|grant\s+amount|how\s+much",
    )
    _APPLY_HEADINGS = re.compile(
        r"(?i)how\s+to\s+apply|application\s+process|application\s+guidance",
    )
    _DATES_HEADINGS = re.compile(
        r"(?i)key\s+dates|deadline|important\s+dates|timeline",
    )

    @staticmethod
    def _section_text(heading, max_len=1500):
        """Collect text content of <p>/<ul>/<ol> siblings after a heading."""
        chunks = []
        for sib in heading.find_all_next():
            name = getattr(sib, "name", None)
            if name in ("h1", "h2", "h3", "h4") and sib is not heading:
                break
            if name in ("p", "ul", "ol"):
                t = clean_text(sib.get_text(" ", strip=True))
                if t:
                    chunks.append(t)
            if sum(len(c) for c in chunks) > max_len:
                break
        return "\n\n".join(chunks).strip()

    def _enrich_detail(self, driver, opp):
        url = opp.get("source_url", "")
        if not url or "mass.gov" not in url:
            return
        try:
            driver.get(url)
            time.sleep(3)
            soup = self.parse_html(driver.page_source)
        except Exception as exc:
            logger.debug("%s: selenium load failed %s: %s", self.source_name, url, exc)
            return

        h1 = soup.find("h1")
        if h1 and "can't find that page" in h1.get_text(strip=True).lower():
            logger.debug("%s: detail page 404 for %s", self.source_name, url)
            return

        main = soup.find("main") or soup.find("article") or soup

        # 1) Description: first few substantive <p> paragraphs
        paras = [clean_text(p.get_text(" ", strip=True)) for p in main.find_all("p")]
        paras = [p for p in paras if p and len(p) > 40]
        text = "\n".join([clean_text(el.get_text(" ", strip=True)) or ""
                          for el in main.find_all(["p", "ul", "ol", "li", "dd", "dt"])])

        if paras and (not opp.get("description") or len(opp.get("description") or "") < 200):
            opp["description"] = "\n\n".join(paras[:6])[:2000]

        # 2) Structured h2/h3 sections
        for h in main.find_all(["h2", "h3", "h4"]):
            label = (clean_text(h.get_text()) or "")
            if not label:
                continue
            if not opp.get("eligibility") and self._ELIG_HEADINGS.search(label):
                body = self._section_text(h)
                if body:
                    opp["eligibility"] = body[:1500]
            if not opp.get("funding_amount") and self._FUNDING_HEADINGS.search(label):
                body = self._section_text(h, max_len=600)
                amt = extract_funding_amount(body)
                opp["funding_amount"] = (amt or body)[:300] if body else opp.get("funding_amount")
            if not opp.get("deadline") and self._DATES_HEADINGS.search(label):
                body = self._section_text(h, max_len=600)
                m = re.search(
                    r"(?:deadline|apply\s*by|due\s*date|closes?\s*on|submission\s+deadline)"
                    r"\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
                    body, re.IGNORECASE,
                )
                if m:
                    d = parse_date(m.group(1))
                    if d:
                        opp["deadline"] = d

        # 3) Regex fallbacks on the whole text
        if not opp.get("eligibility"):
            m = self._ELIG_RE.search(text)
            if m:
                opp["eligibility"] = clean_text(m.group(1))[:1500]

        if not opp.get("deadline"):
            m = self._DEADLINE_RE.search(text)
            if m:
                d = parse_date(m.group(1))
                if d:
                    opp["deadline"] = d

        if not opp.get("funding_amount"):
            amt = extract_funding_amount(text)
            if amt:
                opp["funding_amount"] = amt

        # 4) Organization (bureau responsible)
        bureau = soup.find(class_=re.compile(r"ma__page-header__sub-title"))
        if bureau:
            org = clean_text(bureau.get_text(" ", strip=True))
            if org:
                opp["organization"] = org[:200]

        # 5) Posted date: either from "Date published:" definition list or meta date
        for dt in soup.find_all(["dt", "th", "strong"]):
            label = (clean_text(dt.get_text()) or "").lower()
            if "date published" in label or label == "published:":
                val = dt.find_next(["dd", "td", "span"])
                if val:
                    d = parse_date(clean_text(val.get_text()))
                    if d and not opp.get("posted_date"):
                        opp["posted_date"] = d
                        break

        if not opp.get("posted_date"):
            for meta_label in ("updated", "published", "last updated"):
                m = re.search(
                    rf"(?i){meta_label}:?\s*([A-Z][a-z]+\s+\d{{1,2}},?\s*\d{{4}})", text,
                )
                if m:
                    d = parse_date(m.group(1))
                    if d:
                        opp["posted_date"] = d
                        break

        # 6) Document URLs
        doc_urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx")):
                full = href if href.startswith("http") else urljoin(self.BASE, href)
                if full not in doc_urls:
                    doc_urls.append(full)
        if doc_urls:
            opp["document_urls"] = doc_urls[:10]

        # 7) Conservative defaults so every record has useful info on every
        # field — these kick in only when structured data isn't published on
        # the page itself.
        if not opp.get("eligibility"):
            opp["eligibility"] = (
                "See linked grant program page for specific eligibility "
                "criteria; most Community Grant Finder programs target "
                "Massachusetts municipalities, non-profits, or eligible entities."
            )
        if not opp.get("funding_amount"):
            opp["funding_amount"] = "Amount varies — see grant program page"

    def _parse_fallback_links(self, soup):
        main = soup.find("main") or soup
        seen = set()
        for a in main.find_all("a", href=True):
            if self.reached_limit():
                break
            href = a["href"].strip()
            text = clean_text(a.get_text())
            if not text or len(text) < 10:
                continue
            if not any(k in href.lower() for k in ("service-details", "info-details", "how-to", "grant", "fund")):
                continue
            full = href if href.startswith("http") else urljoin(self.BASE, href)
            if full in seen:
                continue
            seen.add(full)

            slug = urlparse(full).path.rstrip("/").rsplit("/", 1)[-1] or None
            self.add_opportunity({
                "title": text[:300],
                "organization": "Commonwealth of Massachusetts",
                "description": None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": None,
                "category": categorize_opportunity(text, ""),
                "location": "Massachusetts",
                "source": self.source_name,
                "source_url": full,
                "opportunity_number": slug,
                "posted_date": None,
                "document_urls": [],
                "opportunity_type": "grant",
            })


# ======================================================================
# COMMBUYS Bid Search (Selenium)
# ======================================================================


class MassachusettsCOMMBUYSScraper(BaseScraper):
    """Scrapes COMMBUYS advanced bid search via Selenium."""

    SEARCH_URL = (
        "https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml"
    )
    BASE = "https://www.commbuys.com"

    def __init__(self):
        super().__init__("Massachusetts COMMBUYS")

    def scrape(self):
        logger.info("Starting %s scraper (Selenium)...", self.source_name)
        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("%s: Selenium driver unavailable", self.source_name)
            self.log_summary()
            return self.opportunities

        try:
            driver.get(self.SEARCH_URL)
            time.sleep(5)

            from selenium.webdriver.common.by import By
            try:
                btn = driver.find_element(By.ID, "bidSearchForm:btnBidSearch")
            except Exception:
                btn = driver.find_element(
                    By.XPATH,
                    "//button[contains(normalize-space(.),'Search')] | "
                    "//input[@type='submit' and contains(@value,'Search')]",
                )
            btn.click()
            time.sleep(6)

            soup = self.parse_html(driver.page_source)
        except Exception as exc:
            logger.error("%s: failed to search: %s", self.source_name, exc)
            self.log_summary()
            return self.opportunities

        results = soup.find(id="bidSearchResultsForm:results")
        if not results:
            logger.warning("%s: no results container found", self.source_name)
            self.log_summary()
            return self.opportunities

        tables = results.find_all("table")
        rows = []
        for table in tables:
            for tr in table.find_all("tr"):
                if tr.find("a", href=lambda h: h and "bidDetail.sda" in h):
                    rows.append(tr)

        logger.info("%s: %d bid rows found", self.source_name, len(rows))

        for row in rows:
            if self.reached_limit():
                break
            opp = self.parse_opportunity(row)
            if opp:
                self._enrich_detail(driver, opp)
                if opp.get("document_urls"):
                    self.enrich_from_documents(opp)
                self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    # ------------------------------------------------------------------
    # Per-bid detail enrichment (reuses the shared Selenium driver)
    # ------------------------------------------------------------------

    def _enrich_detail(self, driver, opp):
        url = opp.get("source_url", "")
        if not url or "bidDetail.sda" not in url:
            return
        try:
            driver.get(url)
            time.sleep(3)
            soup = self.parse_html(driver.page_source)
        except Exception as exc:
            logger.debug("%s: selenium load failed %s: %s", self.source_name, url, exc)
            return

        text = soup.get_text("\n", strip=True)

        def after(label, stop_labels=(), max_len=600):
            pat = rf"(?mi)^\s*{re.escape(label)}\s*:?\s*$"
            m = re.search(pat, text)
            if not m:
                return None
            region = text[m.end():m.end() + max_len]
            stop_pat = re.compile(
                r"\n(?:" + "|".join(re.escape(s) for s in stop_labels) + r")\s*:?\s*(?:\n|$)"
            ) if stop_labels else None
            if stop_pat:
                m2 = stop_pat.search(region)
                if m2:
                    region = region[:m2.start()]
            return region.strip() or None

        common_stops = (
            "Header Information", "Bid Number", "Description", "Bid Opening Date",
            "Purchaser", "Organization", "Department", "Location", "Fiscal Year",
            "Type Code", "Allow Electronic Quote", "Alternate Id", "Required Date",
            "Available Date", "Info Contact", "Bid Type", "Informal Bid Flag",
            "Purchase Method", "Pre Bid Conference", "Bulletin Desc",
            "Ship-to Address", "Bill-to Address", "Print Format",
            "Required Quote Attachments", "Item Information",
        )

        desc = after("Description", common_stops, 1000)
        bulletin = after("Bulletin Desc", common_stops, 2000)
        desc_parts = []
        if bulletin:
            desc_parts.append(bulletin)
        elif desc:
            desc_parts.append(desc)
        pre_bid = after("Pre Bid Conference", common_stops, 800)
        if pre_bid:
            desc_parts.append(f"Pre-Bid Conference: {pre_bid}")
        contact = after("Info Contact", common_stops, 200)
        if contact:
            desc_parts.append(f"Contact: {contact}")
        if desc_parts:
            opp["description"] = "\n\n".join(desc_parts)[:2000]

        org = after("Organization", common_stops, 100)
        if org:
            opp["organization"] = org.splitlines()[0].strip()[:200]

        dept = after("Department", common_stops, 100)
        if dept and opp.get("organization"):
            opp["organization"] = f"{opp['organization']} — {dept.splitlines()[0].strip()[:100]}"

        avail = after("Available Date", common_stops, 60)
        if avail:
            d = parse_date(avail.splitlines()[0].strip())
            if d and not opp.get("posted_date"):
                opp["posted_date"] = d

        if not opp.get("eligibility"):
            opp["eligibility"] = (
                "Open to vendors registered and in good standing with COMMBUYS. "
                "See bid documents for any bid-specific qualifications."
            )

        # Try a few attachment link patterns; may be empty for many bids
        doc_urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(strip=True)
            if (href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx", ".zip"))
                    or "fileView.sda" in href or "fileDownload.sda" in href):
                full = href if href.startswith("http") else urljoin(self.BASE, href)
                if full not in doc_urls:
                    doc_urls.append(full)
        if doc_urls:
            opp["document_urls"] = doc_urls[:10]

    def parse_opportunity(self, row):
        try:
            fields = {}
            for cell in row.find_all(["td", "th"]):
                text = cell.get_text(" ", strip=True)
                m = re.match(
                    r"^(Bid Solicitation #|Organization Name|Blanket #|Buyer|Description|Bid Opening Date|Bid Holder List|Awarded Vendor\(s\))\s*(.*)$",
                    text,
                )
                if m:
                    key = m.group(1)
                    val = m.group(2).strip()
                    if key not in fields or len(val) > len(fields.get(key, "")):
                        fields[key] = val

            link = row.find("a", href=lambda h: h and "bidDetail.sda" in h)
            sol_number = clean_text(fields.get("Bid Solicitation #", ""))
            if not sol_number and link:
                sol_number = clean_text(link.get_text())
            if not sol_number:
                return None

            href = link["href"] if link else ""
            detail_url = href if href.startswith("http") else urljoin(self.BASE, href)

            title = clean_text(fields.get("Description", "")) or sol_number
            organization = clean_text(fields.get("Organization Name", "")) or "Commonwealth of Massachusetts"
            buyer = clean_text(fields.get("Buyer", ""))
            opening_str = clean_text(fields.get("Bid Opening Date", ""))
            deadline = parse_date(opening_str) if opening_str else None

            description_parts = []
            if fields.get("Description"):
                description_parts.append(fields["Description"])
            if buyer:
                description_parts.append(f"Buyer: {buyer}")
            description = " — ".join(description_parts)[:1500] if description_parts else None

            return {
                "title": title[:300],
                "organization": organization,
                "description": description,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, description or ""),
                "location": "Massachusetts",
                "source": self.source_name,
                "source_url": detail_url,
                "opportunity_number": sol_number,
                "posted_date": None,
                "document_urls": [],
                "opportunity_type": "bid",
            }
        except Exception as exc:
            logger.error("%s: row parse error: %s", self.source_name, exc)
            return None


# ======================================================================
# Factory
# ======================================================================


def get_massachusetts_scrapers():
    return [MassachusettsGrantsScraper(), MassachusettsCOMMBUYSScraper()]
