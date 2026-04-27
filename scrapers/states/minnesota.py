"""
Minnesota Grants scraper — mn.gov/grants

Scrapes Minnesota state grant program listings directly from the Watson
Explorer / Vivisimo XML search backend at search.wcm.mnit.mn.gov.

This bypasses the Radware Bot Manager on mn.gov entirely by hitting the
search backend subdomain, which serves raw XML without bot protection.

Strategy:
  1. Fetch paginated XML from the Vivisimo search backend
     (search.wcm.mnit.mn.gov) — each page returns 10 documents.
  2. Filter to actual grant program pages (URL contains ``?id=``).
  3. For each program, try the external agency link for enrichment
     (description, eligibility, funding, deadlines, PDFs).

Source: https://mn.gov/grants/
"""

import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import requests

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


class MinnesotaGrantsScraper(BaseScraper):
    """Scrapes Minnesota state grant programs via Vivisimo XML backend."""

    PORTAL_URL = "https://mn.gov/grants/"
    XML_URL = (
        "https://search.wcm.mnit.mn.gov/vivisimo/cgi-bin/query-meta"
        "?v:project=mn-gov"
        "&v:sources=mn-grants-content-live"
        "&render.function=xml-feed-display"
        "&content-type=text/xml"
        "&num=200"
    )

    def __init__(self):
        super().__init__("Minnesota Grants")
        self.max_pages = getattr(config, "MN_GRANTS_MAX_PAGES", 10)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/xml, application/xml, */*",
        })

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        self._scrape_programs()
        self.log_summary()
        return self.opportunities

    def _scrape_programs(self):
        root = self._fetch_xml(self.XML_URL)
        if root is None:
            logger.error("Minnesota: could not fetch Vivisimo XML endpoint")
            return

        src = root.find(".//added-source[@name='mn-grants-content-live']")
        total = int(src.get("total-results", 0)) if src is not None else 0
        logger.info("Minnesota: %d grant programs indexed", total)

        all_entries = self._parse_documents(root)

        nav = root.find("navigation")
        if nav is not None:
            base_url = nav.get("base-url", "")
            pages_fetched = 1
            for link in nav.findall("link"):
                if pages_fetched >= self.max_pages:
                    break
                start = link.get("start", "")
                if start == "0":
                    continue
                link_val = (link.text or "").strip()
                if not link_val:
                    continue

                page_url = base_url + link_val
                page_root = self._fetch_xml(page_url)
                if page_root is not None:
                    all_entries.extend(self._parse_documents(page_root))
                    pages_fetched += 1

        seen_urls = set()
        unique = []
        for e in all_entries:
            url = e.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            unique.append(e)

        logger.info("Minnesota: %d unique grant programs after dedup", len(unique))

        for entry in unique:
            if self.reached_limit():
                break
            opp = self._build_opportunity(entry)
            if opp is None:
                continue
            self._enrich_from_external_link(opp)
            if opp.get("document_urls"):
                self.enrich_from_documents(opp)
            self.add_opportunity(opp)

    # ------------------------------------------------------------------
    # XML fetching / parsing
    # ------------------------------------------------------------------

    def _fetch_xml(self, url):
        try:
            resp = self._session.get(url, timeout=20)
            if resp.status_code != 200:
                logger.debug("Minnesota: HTTP %d from %s", resp.status_code, url[:80])
                return None
            text = resp.text.strip()
            if not text.startswith("<?xml") and not text.startswith("<vce"):
                logger.debug("Minnesota: non-XML response from %s", url[:80])
                return None
            return ET.fromstring(text)
        except Exception as exc:
            logger.debug("Minnesota: XML fetch error: %s", exc)
            return None

    @staticmethod
    def _parse_documents(root):
        entries = []
        for doc_el in root.iter("document"):
            entry = {"url": doc_el.get("url", "")}
            for content in doc_el.iter("content"):
                name = content.get("name", "")
                value = content.get("value", "") or (content.text or "")
                if name and value:
                    entry[name] = value.strip()
            entries.append(entry)
        return entries

    # ------------------------------------------------------------------
    # Build opportunity dict from a flat entry
    # ------------------------------------------------------------------

    def _build_opportunity(self, entry):
        url = entry.get("url", "")
        if "?id=" not in url:
            return None

        title = clean_text(
            entry.get("field_title")
            or entry.get("title")
            or entry.get("dc.title")
            or ""
        )
        if not title or len(title) < 5:
            return None

        external_link = (entry.get("field_link_externallink") or "").strip()
        source_url = external_link or url or self.PORTAL_URL

        raw_desc = (
            entry.get("field_description")
            or entry.get("description")
            or entry.get("dc.description")
            or ""
        )
        if raw_desc:
            decoded = html.unescape(raw_desc)
            decoded = re.sub(r"<[^>]*>?", " ", decoded)
            decoded = re.sub(r"\s*https?://\S+\s*", " ", decoded)
            description = clean_text(decoded)
        else:
            description = None

        raw_category = clean_text(entry.get("field_category") or "")
        agency = None
        if raw_category:
            parts = [p.strip() for p in raw_category.split(",") if p.strip()]
            agency = parts[0] if parts else None

        tags = clean_text(entry.get("field_tag") or "")
        category = categorize_opportunity(
            title, (description or "") + " " + (tags or "")
        )

        tcm_id = entry.get("field_tcmid", "")
        opp_number = tcm_id if tcm_id else None

        posted_date = None
        dc_mod = entry.get("dc.modified") or entry.get("date") or ""
        if dc_mod:
            posted_date = parse_date(dc_mod[:25])

        return {
            "title": title,
            "organization": agency or "State of Minnesota",
            "description": description,
            "eligibility": None,
            "funding_amount": None,
            "deadline": None,
            "category": category,
            "location": "Minnesota",
            "source": self.source_name,
            "source_url": source_url,
            "opportunity_number": opp_number,
            "posted_date": posted_date,
            "document_urls": [],
            "opportunity_type": "grant",
        }

    # ------------------------------------------------------------------
    # Enrichment: external agency page (plain requests, no mn.gov needed)
    # ------------------------------------------------------------------

    _DATE_PATTERN = re.compile(
        r"(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})",
    )

    def _enrich_from_external_link(self, opp):
        ext_url = opp.get("source_url", "")
        if not ext_url or ext_url == self.PORTAL_URL or "mn.gov/grants/?id=" in ext_url:
            return

        try:
            resp = self._session.get(ext_url, timeout=25, allow_redirects=True)
            if resp.status_code != 200:
                return

            ct = resp.headers.get("Content-Type", "")
            if ct and not ct.startswith("text/"):
                return

            soup = self.parse_html(resp.text)
            full_text = soup.get_text(separator="\n", strip=True)

            if "captcha" in full_text.lower() and "validate your request" in full_text.lower():
                logger.debug("MN: CAPTCHA on %s, skipping", ext_url)
                return

            self._extract_from_tables(soup, opp)
            self._extract_from_dls(soup, opp)

            if not opp.get("description") or len(opp["description"]) < 80:
                paras = []
                for p in soup.find_all("p"):
                    t = clean_text(p.get_text())
                    if t and len(t) > 40:
                        paras.append(t)
                if paras:
                    new_desc = " ".join(paras[:5])[:2000]
                    existing = opp.get("description") or ""
                    if len(new_desc) > len(existing):
                        opp["description"] = new_desc

            if not opp.get("deadline"):
                deadline_match = re.search(
                    r"(?:deadline|due\s*date|close[sd]?\s*(?:date)?|application\s*due|submit\s*by|"
                    r"applications?\s*(?:must\s+be\s+)?(?:received|submitted)\s+by|target\s+date)"
                    r"\s*[:\-]?\s*"
                    r"(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})",
                    full_text,
                    re.IGNORECASE,
                )
                if deadline_match:
                    opp["deadline"] = parse_date(deadline_match.group(1))
                else:
                    # Fallback: search for any "date" in proximity to deadline keywords
                    m = re.search(r"deadline.*?(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.I | re.S)
                    if m:
                        opp["deadline"] = parse_date(m.group(1))


            if not opp.get("posted_date"):
                posted_match = re.search(
                    r"(?:posted|published|open\s*date|start\s*date|available)\s*[:\-]?\s*"
                    r"(\w+\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})",
                    full_text,
                    re.IGNORECASE,
                )
                if posted_match:
                    opp["posted_date"] = parse_date(posted_match.group(1))

            if not opp.get("funding_amount"):
                amount = extract_funding_amount(full_text)
                if amount:
                    opp["funding_amount"] = amount

            if not opp.get("eligibility"):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if elig:
                    opp["eligibility"] = elig

            if not opp.get("opportunity_number"):
                from parsers.parser_utils import OpportunityEnricher
                opp_num = OpportunityEnricher._extract_opp_number(full_text)
                if opp_num:
                    opp["opportunity_number"] = opp_num
                else:
                    url_id = re.search(
                        r"(?:program[_\-]?id|grant[_\-]?id|cfda)[=/](\w[\w\-\.]+)",
                        ext_url,
                        re.I,
                    )
                    if url_id:
                        opp["opportunity_number"] = url_id.group(1)

            doc_urls = list(opp.get("document_urls") or [])
            for a in soup.select('a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"]'):
                href = a.get("href", "").strip()
                if href:
                    href = urljoin(ext_url, href) if not href.startswith("http") else href
                    if href not in doc_urls:
                        doc_urls.append(href)
            if doc_urls:
                opp["document_urls"] = doc_urls[:10]

        except Exception as exc:
            logger.debug("MN: external link enrichment failed for %s: %s", ext_url, exc)

    # ------------------------------------------------------------------
    # Table / DL extraction helpers
    # ------------------------------------------------------------------

    def _extract_from_tables(self, soup, opp):
        _DEADLINE_LABELS = {
            "deadline", "due date", "close date", "closing date",
            "application deadline", "submission deadline",
        }
        _ELIG_LABELS = {
            "eligibility", "eligible applicants", "who may apply",
            "applicant type", "eligible entities",
        }
        _FUNDING_LABELS = {
            "funding", "award amount", "funding amount",
            "available funding", "estimated funding", "grant amount",
        }

        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = tr.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                label = clean_text(cells[0].get_text())
                value = clean_text(cells[1].get_text())
                if not label or not value:
                    continue
                label_lower = label.lower().rstrip(":").strip()

                if not opp.get("deadline") and label_lower in _DEADLINE_LABELS:
                    d = parse_date(value)
                    if d:
                        opp["deadline"] = d
                elif not opp.get("eligibility") and label_lower in _ELIG_LABELS:
                    if len(value) > 10:
                        opp["eligibility"] = value[:1000]
                elif not opp.get("funding_amount") and label_lower in _FUNDING_LABELS:
                    amt = extract_funding_amount(value)
                    if amt:
                        opp["funding_amount"] = amt

    def _extract_from_dls(self, soup, opp):
        _DEADLINE_KW = {"deadline", "due date", "close date", "application deadline"}
        _ELIG_KW = {"eligibility", "eligible applicants", "who may apply"}
        _FUNDING_KW = {"funding", "award amount", "funding amount"}

        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            for dt in dts:
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue
                label = (clean_text(dt.get_text()) or "").lower().rstrip(":").strip()
                value = clean_text(dd.get_text())
                if not label or not value:
                    continue

                if not opp.get("deadline") and label in _DEADLINE_KW:
                    d = parse_date(value)
                    if d:
                        opp["deadline"] = d
                elif not opp.get("eligibility") and label in _ELIG_KW:
                    if len(value) > 10:
                        opp["eligibility"] = value[:1000]
                elif not opp.get("funding_amount") and label in _FUNDING_KW:
                    amt = extract_funding_amount(value)
                    if amt:
                        opp["funding_amount"] = amt

    # ------------------------------------------------------------------
    # Required by BaseScraper ABC
    # ------------------------------------------------------------------

    def parse_opportunity(self, element):
        return None


def get_minnesota_scrapers():
    return [MinnesotaGrantsScraper()]
