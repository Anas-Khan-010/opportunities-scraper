"""
Minnesota Grants scraper — mn.gov/grants

Scrapes Minnesota state grant programs from the Tridion-backed REST feed at
``mn.gov/grants/rest/rss/Grants?id=1093``, which returns the full set of
~56 grant programs with rich HTML descriptions, structured Category/Tag/
ExternalLink/pubdate metadata in a single call.

If the REST feed is unreachable, the scraper falls back to the Watson Explorer
/ Vivisimo XML search backend at ``search.wcm.mnit.mn.gov`` (which bypasses the
Radware Bot Manager fronting mn.gov).

After building each opportunity:
  1. Run text-based extraction on the rich description (funding, eligibility,
     deadline, opp number).
  2. If an external agency link is present, fetch it and try to enrich
     missing fields from page tables, definition lists, and free-text regex.
  3. Pull PDF/Doc attachments from the external page for the document
     enricher.

Source: https://mn.gov/grants/
"""

import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import (
    clean_text, parse_date, categorize_opportunity, extract_funding_amount,
)


class MinnesotaGrantsScraper(BaseScraper):
    """Scrapes Minnesota state grant programs via the Tridion REST feed."""

    PORTAL_URL = "https://mn.gov/grants/"

    REST_URL = "https://mn.gov/grants/rest/rss/Grants?id=1093"

    XML_URL = (
        "https://search.wcm.mnit.mn.gov/vivisimo/cgi-bin/query-meta"
        "?v:project=mn-gov"
        "&v:sources=mn-grants-content-live"
        "&render.function=xml-feed-display"
        "&content-type=text/xml"
        "&num=200"
    )

    _DEADLINE_KEYWORDS = (
        r"deadline|due\s*date|close[sd]?\s*(?:date)?|closing\s*date|"
        r"application\s*due|application\s*deadline|submission\s*deadline|"
        r"submit\s*by|applications?\s*(?:must\s+be\s+)?(?:received|submitted)"
        r"(?:\s+(?:by|no\s+later\s+than))?|target\s+date|expires?\s+on"
    )
    _DATE_TOKEN = (
        r"(?:[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{2,4}"
        r"|\d{4}-\d{2}-\d{2})"
    )

    def __init__(self):
        super().__init__("Minnesota Grants")
        self.max_pages = getattr(config, "MN_GRANTS_MAX_PAGES", 10)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        self._scrape_programs()
        self.log_summary()
        return self.opportunities

    def _scrape_programs(self):
        if self._scrape_via_rest():
            return
        logger.warning("Minnesota: REST feed empty/unreachable, falling back to Vivisimo")
        self._scrape_via_vivisimo()

    # ------------------------------------------------------------------
    # PRIMARY: Tridion REST feed (rich data, single call)
    # ------------------------------------------------------------------

    def _scrape_via_rest(self) -> bool:
        root = self._fetch_xml(self.REST_URL)
        if root is None:
            return False

        items = [lst for lst in root.findall("list") if lst.findtext("Title")]
        logger.info("Minnesota: %d grant programs from REST feed", len(items))
        if not items:
            return False

        any_added = False
        for item in items:
            if self.reached_limit():
                break
            opp = self._build_from_rest_item(item)
            if not opp:
                continue

            external_link = opp.pop("_external_link", "") or ""
            opp.pop("_portal_url", None)

            self._extract_from_description(opp)

            if external_link:
                self._enrich_from_external_link(opp, external_link)

            if opp.get("document_urls"):
                self.enrich_from_documents(opp)

            self.add_opportunity(opp)
            any_added = True

        return any_added

    def _build_from_rest_item(self, lst):
        title = clean_text(lst.findtext("Title") or "")
        if not title or len(title) < 5:
            return None

        raw_desc = lst.findtext("Description") or ""
        description = self._clean_html_description(raw_desc)

        agency = clean_text(lst.findtext("Category/Title") or "")

        ext_link_el = lst.find("Link/ExternalLink")
        external_link = ""
        if ext_link_el is not None and ext_link_el.text:
            external_link = ext_link_el.text.strip().rstrip(", \t")

        item_id = (lst.findtext("id") or "").strip()
        publication = (lst.findtext("publication") or "1093").strip()
        portal_url = (
            f"https://mn.gov/grants/?id={publication}-{item_id}"
            if item_id else self.PORTAL_URL
        )
        source_url = external_link or portal_url

        pubdate = (lst.findtext("pubdate") or "").strip()
        posted_date = parse_date(pubdate[:25]) if pubdate else None

        tag_titles = [t.text for t in lst.findall("Tag/Title") if t.text]
        category = categorize_opportunity(
            title, (description or "") + " " + " ".join(tag_titles)
        )

        opp_type = "rfp" if title.upper().startswith("RFP") else "grant_program"

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
            "opportunity_number": item_id or None,
            "posted_date": posted_date,
            "document_urls": [],
            "opportunity_type": opp_type,
            "_external_link": external_link,
            "_portal_url": portal_url,
        }

    @staticmethod
    def _clean_html_description(raw):
        if not raw:
            return None
        decoded = html.unescape(raw)
        decoded = re.sub(r"</(?:p|div|li|br|tr|h\d)\s*>", "\n", decoded, flags=re.I)
        decoded = re.sub(r"<[^>]+>", " ", decoded)
        decoded = decoded.replace("\xa0", " ")
        decoded = re.sub(r"[ \t]+", " ", decoded)
        decoded = re.sub(r"\n[ \t]+", "\n", decoded)
        decoded = re.sub(r"\n{3,}", "\n\n", decoded)
        return clean_text(decoded) or None

    # ------------------------------------------------------------------
    # Description-based extraction (works on the rich HTML text from REST)
    # ------------------------------------------------------------------

    def _extract_from_description(self, opp):
        from parsers.parser_utils import OpportunityEnricher

        text = opp.get("description") or ""
        if not text or len(text) < 50:
            return

        if not opp.get("funding_amount"):
            amt = extract_funding_amount(text)
            if amt:
                opp["funding_amount"] = amt

        if not opp.get("eligibility"):
            elig = OpportunityEnricher._extract_eligibility(text)
            if elig:
                opp["eligibility"] = elig

        if not opp.get("deadline"):
            d = self._find_labelled_date(
                text, self._DEADLINE_KEYWORDS,
            )
            if d:
                opp["deadline"] = d

        if not opp.get("opportunity_number"):
            opp_num = OpportunityEnricher._extract_opp_number(text)
            if opp_num:
                opp["opportunity_number"] = opp_num

    def _find_labelled_date(self, text, keyword_pattern):
        pattern = (
            r"(?:" + keyword_pattern + r")"
            r"\s*[:\-]?\s*"
            r"(" + self._DATE_TOKEN + r")"
        )
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return None
        try:
            return parse_date(m.group(1))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # FALLBACK: Vivisimo XML search backend
    # ------------------------------------------------------------------

    def _scrape_via_vivisimo(self):
        root = self._fetch_xml(self.XML_URL)
        if root is None:
            logger.error("Minnesota: could not fetch Vivisimo XML endpoint")
            return

        src = root.find(".//added-source[@name='mn-grants-content-live']")
        total = int(src.get("total-results", 0)) if src is not None else 0
        logger.info("Minnesota: %d grant programs indexed (Vivisimo)", total)

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

        seen = set()
        unique = []
        for e in all_entries:
            url = e.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            unique.append(e)

        logger.info("Minnesota: %d unique grant programs after dedup", len(unique))

        for entry in unique:
            if self.reached_limit():
                break
            opp = self._build_from_vivisimo(entry)
            if opp is None:
                continue
            external_link = opp.pop("_external_link", "")
            self._extract_from_description(opp)
            if external_link:
                self._enrich_from_external_link(opp, external_link)
            if opp.get("document_urls"):
                self.enrich_from_documents(opp)
            self.add_opportunity(opp)

    def _build_from_vivisimo(self, entry):
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

        external_link = (entry.get("field_link_externallink") or "").strip().rstrip(", \t")
        source_url = external_link or url or self.PORTAL_URL

        raw_desc = (
            entry.get("field_description")
            or entry.get("description")
            or entry.get("dc.description")
            or ""
        )
        description = self._clean_html_description(raw_desc)

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

        opp_type = "rfp" if title.upper().startswith("RFP") else "grant_program"

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
            "opportunity_type": opp_type,
            "_external_link": external_link,
        }

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
    # External agency page enrichment
    # ------------------------------------------------------------------

    def _enrich_from_external_link(self, opp, ext_url):
        if not ext_url or ext_url == self.PORTAL_URL:
            return

        try:
            resp = self.fetch_page(ext_url, timeout=25)
            if not resp or resp.status_code != 200:
                return

            ct = resp.headers.get("Content-Type", "")
            if ct and not ct.startswith(("text/", "application/xhtml")):
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
                d = self._find_labelled_date(full_text, self._DEADLINE_KEYWORDS)
                if d:
                    opp["deadline"] = d

            if not opp.get("posted_date"):
                d = self._find_labelled_date(
                    full_text,
                    r"posted|published|open\s*date|start\s*date|available",
                )
                if d:
                    opp["posted_date"] = d

            if not opp.get("funding_amount"):
                amount = extract_funding_amount(full_text, require_keyword=True)
                if amount:
                    opp["funding_amount"] = amount

            if not opp.get("eligibility"):
                from parsers.parser_utils import OpportunityEnricher
                elig = OpportunityEnricher._extract_eligibility(full_text)
                if self._is_real_eligibility(elig):
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
    # Quality validators
    # ------------------------------------------------------------------

    @staticmethod
    def _is_real_eligibility(text):
        """Reject nav-menu strings masquerading as eligibility text.

        Real eligibility paragraphs read like prose: long-ish sentences,
        verbs like 'must', 'are', 'include', 'eligible'. Nav menus are
        many short lines with capitalized phrases and no verbs.
        """
        if not text or len(text) < 40:
            return False

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False

        short_lines = sum(1 for ln in lines if len(ln) < 30)
        if len(lines) >= 4 and short_lines / len(lines) > 0.5:
            return False

        prose_signal = re.search(
            r"\b(must|shall|are|include|require|eligible|qualify|"
            r"applicant|individual|organization|nonprofit|government)\b",
            text,
            re.IGNORECASE,
        )
        if not prose_signal:
            return False

        sentence_starts = re.findall(r"(?:[.!?]\s+|^)[A-Z][a-z]", text)
        if len(sentence_starts) < 1 and len(text) < 200:
            return False

        return True

    # ------------------------------------------------------------------
    # Table / DL extraction helpers (kept from previous implementation)
    # ------------------------------------------------------------------

    _DEADLINE_LABELS = {
        "deadline", "due date", "close date", "closing date",
        "application deadline", "submission deadline", "applications due",
        "expires on",
    }
    _ELIG_LABELS = {
        "eligibility", "eligible applicants", "who may apply",
        "applicant type", "eligible entities", "who can apply",
        "eligibility requirements",
    }
    _FUNDING_LABELS = {
        "funding", "award amount", "funding amount", "amount",
        "available funding", "estimated funding", "grant amount",
        "award range", "grant range", "maximum award",
    }

    def _extract_from_tables(self, soup, opp):
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

                if not opp.get("deadline") and label_lower in self._DEADLINE_LABELS:
                    d = parse_date(value)
                    if d:
                        opp["deadline"] = d
                elif not opp.get("eligibility") and label_lower in self._ELIG_LABELS:
                    if len(value) > 10:
                        opp["eligibility"] = value[:1000]
                elif not opp.get("funding_amount") and label_lower in self._FUNDING_LABELS:
                    amt = extract_funding_amount(value)
                    if amt:
                        opp["funding_amount"] = amt
                    elif "$" in value and len(value) <= 200:
                        opp["funding_amount"] = value

    def _extract_from_dls(self, soup, opp):
        for dl in soup.find_all("dl"):
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue
                label = (clean_text(dt.get_text()) or "").lower().rstrip(":").strip()
                value = clean_text(dd.get_text())
                if not label or not value:
                    continue

                if not opp.get("deadline") and label in self._DEADLINE_LABELS:
                    d = parse_date(value)
                    if d:
                        opp["deadline"] = d
                elif not opp.get("eligibility") and label in self._ELIG_LABELS:
                    if len(value) > 10:
                        opp["eligibility"] = value[:1000]
                elif not opp.get("funding_amount") and label in self._FUNDING_LABELS:
                    amt = extract_funding_amount(value)
                    if amt:
                        opp["funding_amount"] = amt
                    elif "$" in value and len(value) <= 200:
                        opp["funding_amount"] = value

    # ------------------------------------------------------------------
    # XML fetching helper (uses BaseScraper.fetch_page for full retry/anti-bot)
    # ------------------------------------------------------------------

    def _fetch_xml(self, url):
        try:
            resp = self.fetch_page(
                url,
                timeout=25,
                headers={"Accept": "application/xml, text/xml, */*"},
            )
            if not resp or resp.status_code != 200:
                logger.debug(
                    "Minnesota: HTTP %s from %s",
                    resp.status_code if resp else "no-response",
                    url[:100],
                )
                return None
            text = resp.text.strip()
            if not text.startswith(("<?xml", "<results", "<vce")):
                logger.debug("Minnesota: non-XML response from %s", url[:100])
                return None
            return ET.fromstring(text)
        except Exception as exc:
            logger.debug("Minnesota: XML fetch error for %s: %s", url[:100], exc)
            return None

    # ------------------------------------------------------------------
    # Required by BaseScraper ABC
    # ------------------------------------------------------------------

    def parse_opportunity(self, element):
        return None


def get_minnesota_scrapers():
    return [MinnesotaGrantsScraper()]
