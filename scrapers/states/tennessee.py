"""
Tennessee scrapers — tn.gov

Two sources:

1. TN F&A Grant Funding Opportunities:
   https://www.tn.gov/finance/grants-information-sharing/grants-information-sharing/grant-funding-opportunities.html
   Hub page that links to active grant programs across TN agencies.

2. TN General Services CPO RFP Opportunities:
   https://www.tn.gov/generalservices/procurement/central-procurement-office--cpo-/supplier-information/request-for-proposals--rfp--opportunities1.html
   Table/list of currently open state RFPs.

tn.gov aggressively blocks bot-style HTTP clients (WAF + IP reputation +
Akamai), so we try plain requests first and transparently fall back to
Selenium (undetected-chromedriver) when that fails.
"""

import re
import time
from urllib.parse import urljoin

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity


class _TennesseeBase(BaseScraper):
    """Shared helper for tn.gov pages that may need Selenium fallback."""

    BASE = "https://www.tn.gov"

    def _fetch_html(self, url):
        """Return page HTML via requests → Selenium fallback, or None."""
        try:
            resp = self.session.get(
                url,
                timeout=20,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if resp.status_code == 200 and len(resp.text) > 2000:
                return resp.text
            logger.info(
                "%s: requests returned %s/%d bytes; falling back to Selenium",
                self.source_name, resp.status_code, len(resp.text),
            )
        except Exception as exc:
            logger.info("%s: requests failed (%s); falling back to Selenium",
                        self.source_name, exc)

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("%s: Selenium driver unavailable", self.source_name)
            return None
        try:
            driver.get(url)
            time.sleep(5)
            html = driver.page_source
            if "ERR_TIMED_OUT" in html or "This site can" in html and "be reached" in html:
                logger.warning("%s: Selenium also blocked / timed out on %s",
                               self.source_name, url)
                return None
            return html
        except Exception as exc:
            logger.error("%s: Selenium fetch failed: %s", self.source_name, exc)
            return None


# ======================================================================
# TN F&A Grant Funding Opportunities
# ======================================================================


class TennesseeGrantsScraper(_TennesseeBase):
    """Scrapes TN F&A grant funding opportunities hub page."""

    LISTING_URL = (
        "https://www.tn.gov/finance/grants-information-sharing/"
        "grants-information-sharing/grant-funding-opportunities.html"
    )

    def __init__(self):
        super().__init__("Tennessee F&A Grants")

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        html = self._fetch_html(self.LISTING_URL)
        if not html:
            logger.error("%s: could not retrieve listing", self.source_name)
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(html)

        main = (
            soup.find("main")
            or soup.find("div", attrs={"role": "main"})
            or soup.find("div", class_=re.compile(r"(tn-main|main-content|content)", re.I))
            or soup
        )

        seen = set()
        for a in main.find_all("a", href=True):
            if self.reached_limit():
                break
            href = a["href"].strip()
            text = clean_text(a.get_text())

            if not text or len(text) < 6:
                continue
            if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue
            keywords = ("grant", "fund", "rfa", "rfp", "scholar", "award", "program", "ocjp", "volunteer")
            if not any(k in text.lower() for k in keywords) and not any(k in href.lower() for k in keywords):
                continue

            full = href if href.startswith("http") else urljoin(self.BASE, href)
            if full in seen:
                continue
            seen.add(full)

            opp = self.parse_opportunity({"title": text, "url": full})
            if opp:
                if opp.get("document_urls"):
                    self.enrich_from_documents(opp)
                self.add_opportunity(opp)

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, element):
        try:
            title = element.get("title", "").strip()
            url = element.get("url", "").strip()
            if not title or not url:
                return None

            document_urls = []
            if url.lower().endswith((".pdf", ".doc", ".docx")):
                document_urls.append(url)

            return {
                "title": title[:300],
                "organization": "State of Tennessee",
                "description": None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": None,
                "category": categorize_opportunity(title, ""),
                "location": "Tennessee",
                "source": self.source_name,
                "source_url": url,
                "opportunity_number": None,
                "posted_date": None,
                "document_urls": document_urls,
                "opportunity_type": "grant",
            }
        except Exception as exc:
            logger.error("%s: parse error: %s", self.source_name, exc)
            return None


# ======================================================================
# TN CPO RFP Opportunities
# ======================================================================


class TennesseeCPOScraper(_TennesseeBase):
    """Scrapes Tennessee Central Procurement Office RFP opportunities."""

    LISTING_URL = (
        "https://www.tn.gov/generalservices/procurement/central-procurement-office--cpo-/"
        "supplier-information/request-for-proposals--rfp--opportunities1.html"
    )

    def __init__(self):
        super().__init__("Tennessee CPO RFP")

    def scrape(self):
        logger.info("Starting %s scraper...", self.source_name)
        html = self._fetch_html(self.LISTING_URL)
        if not html:
            logger.error("%s: could not retrieve listing", self.source_name)
            self.log_summary()
            return self.opportunities

        soup = self.parse_html(html)
        parsed_any = False

        for table in soup.find_all("table"):
            header = table.find("tr")
            if not header:
                continue
            hdr_text = " ".join(c.get_text(strip=True).lower() for c in header.find_all(["th", "td"]))
            if not any(k in hdr_text for k in ("rfp", "proposal", "solicitation", "event", "title")):
                continue

            rows = table.find_all("tr")[1:]
            for row in rows:
                if self.reached_limit():
                    break
                opp = self.parse_opportunity(row)
                if opp:
                    parsed_any = True
                    if opp.get("document_urls"):
                        self.enrich_from_documents(opp)
                    self.add_opportunity(opp)
            if parsed_any:
                break

        if not parsed_any:
            self._parse_link_list(soup)

        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                return None

            title_cell = cells[0]
            link = title_cell.find("a", href=True)
            title = clean_text(title_cell.get_text())
            if not title:
                return None

            detail_href = link["href"] if link else ""
            if detail_href:
                detail_url = (
                    detail_href if detail_href.startswith("http")
                    else urljoin(self.BASE, detail_href)
                )
            else:
                detail_url = f"{self.LISTING_URL}#{title[:50]}"

            deadline = None
            description_parts = []
            opp_number = None
            for c in cells[1:]:
                text = clean_text(c.get_text(" ", strip=True))
                if not text:
                    continue
                if not deadline:
                    maybe = parse_date(text)
                    if maybe:
                        deadline = maybe
                        continue
                if re.match(r"^[\w\-\/]{4,30}$", text) and not opp_number:
                    opp_number = text
                    continue
                description_parts.append(text)

            doc_urls = []
            for a in row.find_all("a", href=True):
                h = a["href"]
                if h.lower().endswith((".pdf", ".doc", ".docx", ".zip")):
                    doc_urls.append(h if h.startswith("http") else urljoin(self.BASE, h))

            return {
                "title": title[:300],
                "organization": "Tennessee Central Procurement Office",
                "description": " — ".join(description_parts)[:1500] if description_parts else None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": deadline,
                "category": categorize_opportunity(title, ""),
                "location": "Tennessee",
                "source": self.source_name,
                "source_url": detail_url,
                "opportunity_number": opp_number,
                "posted_date": None,
                "document_urls": doc_urls[:10],
                "opportunity_type": "rfp",
            }
        except Exception as exc:
            logger.error("%s: row parse error: %s", self.source_name, exc)
            return None

    def _parse_link_list(self, soup):
        """Fallback: if there's no table, scan <li>/<a> for PDF RFP links."""
        seen = set()
        for a in soup.find_all("a", href=True):
            if self.reached_limit():
                break
            href = a["href"].strip()
            text = clean_text(a.get_text())
            if not text or len(text) < 5:
                continue
            hl = href.lower()
            if not (hl.endswith(".pdf") or "rfp" in hl or "rfp" in text.lower()):
                continue
            full = href if href.startswith("http") else urljoin(self.BASE, href)
            if full in seen:
                continue
            seen.add(full)

            opp = {
                "title": text[:300],
                "organization": "Tennessee Central Procurement Office",
                "description": None,
                "eligibility": None,
                "funding_amount": None,
                "deadline": None,
                "category": categorize_opportunity(text, ""),
                "location": "Tennessee",
                "source": self.source_name,
                "source_url": full,
                "opportunity_number": None,
                "posted_date": None,
                "document_urls": [full] if hl.endswith(".pdf") else [],
                "opportunity_type": "rfp",
            }
            if opp["document_urls"]:
                self.enrich_from_documents(opp)
            self.add_opportunity(opp)


# ======================================================================
# Factory
# ======================================================================


def get_tennessee_scrapers():
    return [TennesseeGrantsScraper(), TennesseeCPOScraper()]
