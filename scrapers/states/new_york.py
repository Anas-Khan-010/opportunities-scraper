"""
New York State Grants Gateway scraper — esupplier.sfs.ny.gov

Scrapes grant opportunities from the New York Statewide Financial System
(SFS) PeopleSoft portal.  The page lists ~25 grants in a table; each row
links to a detail page with rich metadata (description, funding amount,
deadlines, eligibility, contact info, document links).

PeopleSoft wraps page content inside the ``ptifrmtgtframe`` iframe, so
Selenium must switch into that frame before locating grant elements.

Source: https://esupplier.sfs.ny.gov/psp/fscm/SUPPLIER/ERP/c/NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL
"""

import time
import random
import re

from scrapers.base_scraper import BaseScraper, SeleniumDriverManager, SELENIUM_DELAY_RANGE
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity

BASE_URL = (
    "https://esupplier.sfs.ny.gov/psp/fscm/SUPPLIER/ERP/c/"
    "NY_SUPPUB_FL.AUC_RESP_INQ_AUC.GBL"
)

INITIAL_LOAD_WAIT = 60
DETAIL_LOAD_WAIT = 30
RETURN_LOAD_WAIT = 30
DELAY_BETWEEN_GRANTS = (3, 6)


class NewYorkGrantsScraper(BaseScraper):
    """Scrapes NY State grants from the SFS PeopleSoft Grants Gateway."""

    def __init__(self):
        super().__init__("NY Grants Gateway")

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (Selenium)...")

        driver = SeleniumDriverManager.get_driver()
        if driver is None:
            logger.error("Selenium driver unavailable — skipping NY Grants Gateway")
            return self.opportunities

        try:
            self._load_main_page(driver)
            self._scrape_all_grants(driver)
        except Exception as exc:
            logger.error(f"NY Grants Gateway: fatal error: {exc}")

        self.log_summary()
        return self.opportunities

    def _switch_to_peoplesoft_frame(self, driver):
        """Switch into the PeopleSoft content iframe if present."""
        from selenium.webdriver.common.by import By

        driver.switch_to.default_content()

        iframe_selectors = [
            "ptifrmtgtframe",
            "TargetContent",
            "main_target_win",
        ]

        for frame_id in iframe_selectors:
            try:
                frame = driver.find_element(By.ID, frame_id)
                driver.switch_to.frame(frame)
                logger.debug(f"NY Grants: switched to iframe '{frame_id}'")
                return True
            except Exception:
                continue

        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                logger.debug(f"NY Grants: found {len(iframes)} iframes, trying first one...")
                for iframe in iframes:
                    try:
                        iframe_id = iframe.get_attribute("id") or "(no id)"
                        iframe_name = iframe.get_attribute("name") or "(no name)"
                        logger.debug(f"NY Grants: trying iframe id={iframe_id} name={iframe_name}")
                        driver.switch_to.frame(iframe)
                        if driver.find_elements(By.ID, "AUC_NAME_LNK$0"):
                            logger.debug(f"NY Grants: found grant table in iframe {iframe_id}")
                            return True
                        driver.switch_to.default_content()
                    except Exception:
                        driver.switch_to.default_content()
                        continue
        except Exception:
            pass

        logger.debug("NY Grants: no PeopleSoft iframe found, staying in default context")
        return False

    def _load_main_page(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        time.sleep(random.uniform(*SELENIUM_DELAY_RANGE))

        old_timeout = None
        try:
            old_timeout = driver.timeouts.page_load
        except Exception:
            pass

        try:
            driver.set_page_load_timeout(90)
        except Exception:
            pass

        try:
            driver.get(BASE_URL)
        except Exception as exc:
            logger.debug(f"NY Grants: page load timed out ({exc}), continuing anyway")

        if old_timeout:
            try:
                driver.set_page_load_timeout(old_timeout)
            except Exception:
                pass

        try:
            WebDriverWait(driver, INITIAL_LOAD_WAIT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            logger.debug("NY Grants: readyState timeout on initial load, continuing")

        time.sleep(random.uniform(8, 14))

        self._switch_to_peoplesoft_frame(driver)

        grant_link_found = False
        try:
            WebDriverWait(driver, INITIAL_LOAD_WAIT).until(
                EC.presence_of_element_located((By.ID, "AUC_NAME_LNK$0"))
            )
            grant_link_found = True
        except Exception:
            pass

        if not grant_link_found:
            logger.debug("NY Grants: grant link not found in current context, retrying with iframe switch...")
            driver.switch_to.default_content()
            self._switch_to_peoplesoft_frame(driver)
            time.sleep(random.uniform(5, 8))

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "AUC_NAME_LNK$0"))
                )
                grant_link_found = True
            except Exception:
                pass

        if not grant_link_found:
            logger.warning("NY Grants: timed out waiting for grant table to load")
            self._log_page_debug(driver)

        time.sleep(random.uniform(2, 4))

    def _log_page_debug(self, driver):
        """Log page structure info to help diagnose loading failures."""
        from selenium.webdriver.common.by import By
        try:
            driver.switch_to.default_content()
            title = driver.title
            url = driver.current_url
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            iframe_ids = []
            for f in iframes:
                fid = f.get_attribute("id") or "(no id)"
                iframe_ids.append(fid)
            logger.debug(f"NY Grants debug: title='{title}', url='{url}', iframes={iframe_ids}")

            body_text = driver.find_element(By.TAG_NAME, "body").text[:500]
            logger.debug(f"NY Grants debug: body preview: {body_text[:200]}")
        except Exception as exc:
            logger.debug(f"NY Grants debug: failed to inspect page: {exc}")

    def _scrape_all_grants(self, driver):
        from selenium.webdriver.common.by import By

        soup = self.parse_html(driver.page_source)
        row_count = self._count_rows(soup)
        logger.info(f"NY Grants: found {row_count} grants on main page")

        for idx in range(row_count):
            if self.reached_limit():
                break

            try:
                self._scrape_single_grant(driver, idx)
            except Exception as exc:
                logger.error(f"NY Grants: error on grant #{idx}: {exc}")
                try:
                    self._ensure_on_main_page(driver)
                except Exception:
                    logger.error("NY Grants: could not recover to main page, stopping")
                    break

            time.sleep(random.uniform(*DELAY_BETWEEN_GRANTS))

    def _count_rows(self, soup):
        """Count grant rows by looking for AUC_NAME_LNK$N link elements."""
        count = 0
        while soup.find(id=f"AUC_NAME_LNK${count}"):
            count += 1
        return count

    def _scrape_single_grant(self, driver, idx):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        soup = self.parse_html(driver.page_source)
        listing = self._parse_listing_row(soup, idx)
        if not listing:
            return

        title = listing.get("title", "")
        logger.info(f"  [{idx + 1}] Clicking into: {title[:60]}...")

        link_id = f"AUC_NAME_LNK${idx}"
        try:
            link_el = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, link_id))
            )
            driver.execute_script("arguments[0].click();", link_el)
        except Exception as exc:
            logger.warning(f"NY Grants: could not click {link_id}: {exc}")
            return

        try:
            WebDriverWait(driver, DETAIL_LOAD_WAIT).until(
                EC.presence_of_element_located((By.ID, "NY_GG_ABSTRT_VW_AUC_ID"))
            )
        except Exception:
            logger.debug("NY Grants: detail page load timed out, parsing anyway")

        time.sleep(random.uniform(3, 6))

        detail_soup = self.parse_html(driver.page_source)
        opp = self._parse_detail_page(detail_soup, listing)

        if opp:
            if opp.get('document_urls'):
                self.enrich_from_documents(opp)
            self.add_opportunity(opp)

        self._click_return_to_search(driver)

    def _parse_listing_row(self, soup, idx):
        """Extract basic data from a single row on the main listing page."""
        try:
            event_id_el = soup.find(id=f"AUC_ID_COL$span${idx}")
            title_el = soup.find(id=f"AUC_NAME_LNK${idx}")
            agency_el = soup.find(id=f"NY_AUC_INQ1_WRK_BUSINESS_UNIT${idx}")
            status_el = soup.find(id=f"NY_AUC_INQ1_WRK_NY_GG_PORT_STATUS${idx}")
            eligibility_el = soup.find(id=f"NY_AUC_INQ1_WRK_FIELDLIST${idx}")
            avail_el = soup.find(id=f"RESP_INQA1_WK_AUC_DTTM_PREVIEW${idx}")
            release_el = soup.find(id=f"RESP_INQA1_WK_AUC_DTTM_START${idx}")
            due_el = soup.find(id=f"RESP_INQA1_WK_AUC_DTTM_FINISH${idx}")

            title = clean_text(title_el.get_text()) if title_el else None
            if not title:
                return None

            return {
                "title": title,
                "event_id": clean_text(event_id_el.get_text()) if event_id_el else None,
                "agency_code": clean_text(agency_el.get_text()) if agency_el else None,
                "status": clean_text(status_el.get_text()) if status_el else None,
                "eligibility": clean_text(eligibility_el.get_text()) if eligibility_el else None,
                "availability_date": clean_text(avail_el.get_text()) if avail_el else None,
                "release_date": clean_text(release_el.get_text()) if release_el else None,
                "due_date": clean_text(due_el.get_text()) if due_el else None,
            }
        except Exception as exc:
            logger.debug(f"NY Grants: error parsing listing row {idx}: {exc}")
            return None

    def _parse_detail_page(self, soup, listing):
        """Parse Overview + Full Announcement Details from the detail page."""
        try:
            opp_id = self._detail_field(soup, "NY_GG_ABSTRT_VW_AUC_ID")
            agency = self._detail_field(soup, "NY_GG_ABSTRT_VW_DESCR1")
            title = self._detail_field(soup, "NY_GG_ABSTRT_VW_AUC_NAME") or listing["title"]
            contact_name = self._detail_field(soup, "NY_GG_ABSTRT_VW_OPRID")
            description = self._detail_field(soup, "NY_GG_ABSTRT_VW_DESCRLONG2")

            due_datetime = self._detail_field(soup, "NY_GG_ABSTRT_VW_DATETIMESTRING")
            funding_raw = self._detail_field(soup, "NY_GG_ABSTRT_VW_FUNDED_AMT")
            anticipated_award = self._detail_field(soup, "NY_GG_ABSTRT_VW_DATE_STRING2")
            contract_length = self._detail_field(soup, "NY_GG_ABSTRT_VW_STRING_TEXT")
            loi_narrative = self._detail_field(soup, "NY_GG_ABSTRT_VW_DESCRLONG")
            loi_due = self._detail_field(soup, "NY_GG_ABSTRT_VW_DUE_DT")
            questions_due = self._detail_field(soup, "NY_GG_ABSTRT_VW_DATE_STRING1")
            qa_narrative = self._detail_field(soup, "NY_GG_ABSTRT_VW_DESCRLONG1")
            qa_posting_type = self._detail_field(soup, "NY_GG_ABSTRT_VW_NY_GG_POST_TYPE")
            qa_posting_date = self._detail_field(soup, "NY_GG_ABSTRT_VW_DATE_STRING")
            bidder_conf = self._detail_field(soup, "NY_GG_ABSTRT_VW_DESCR254")
            eligible_applicants = self._detail_field(soup, "NY_GG_SRCH_WRK_LONGVALUE")
            service_areas = self._detail_field(soup, "NY_GG_SRCH_WRK_DESCRLONG")

            contact_email = self._extract_contact_email(soup)
            announcement_url = self._extract_announcement_link(soup)
            doc_urls = self._extract_document_urls(soup)

            desc_parts = []
            if description:
                desc_parts.append(description)
            if contact_name:
                contact_str = f"Contact: {contact_name}"
                if contact_email:
                    contact_str += f" ({contact_email})"
                desc_parts.append(contact_str)
            if service_areas:
                desc_parts.append(f"Service Areas: {service_areas}")
            if contract_length and contract_length != "0 Month(s)":
                desc_parts.append(f"Contract Length: {contract_length}")
            if anticipated_award and anticipated_award.strip():
                desc_parts.append(f"Anticipated Award: {anticipated_award}")
            if loi_due and loi_due.strip():
                desc_parts.append(f"LOI Due: {loi_due}")
            if questions_due and questions_due.strip():
                desc_parts.append(f"Questions Due: {questions_due}")
            if bidder_conf and bidder_conf.strip():
                desc_parts.append(f"Bidder's Conference: {bidder_conf}")
            if listing.get("status"):
                desc_parts.append(f"Status: {listing['status']}")

            full_description = "; ".join(desc_parts) if desc_parts else None

            deadline = parse_date(due_datetime) if due_datetime else None
            if not deadline and listing.get("due_date"):
                deadline = parse_date(listing["due_date"])

            posted_date = None
            if listing.get("availability_date"):
                posted_date = parse_date(listing["availability_date"])

            eligibility = eligible_applicants or listing.get("eligibility")

            source_url = announcement_url or BASE_URL
            if announcement_url and announcement_url not in (doc_urls or []):
                doc_urls = doc_urls or []

            organization = agency or "New York State"
            category = categorize_opportunity(title, full_description or "")

            return {
                "title": title,
                "organization": organization,
                "description": full_description[:2000] if full_description else None,
                "eligibility": eligibility,
                "funding_amount": funding_raw,
                "deadline": deadline,
                "category": category,
                "location": "New York",
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": opp_id or listing.get("event_id"),
                "posted_date": posted_date,
                "document_urls": doc_urls or [],
                "opportunity_type": "grant",
            }

        except Exception as exc:
            logger.error(f"NY Grants: error parsing detail page: {exc}")
            return None

    def _detail_field(self, soup, element_id):
        """Get text from a PeopleSoft display-only field by ID."""
        el = soup.find(id=element_id)
        if not el:
            return None
        text = clean_text(el.get_text())
        if text in ("\xa0", "&nbsp;", ""):
            return None
        return text

    def _extract_contact_email(self, soup):
        """Pull the contact email from the HTML area mailto link."""
        area = soup.find(id="win0divNY_GG_SRCH_WRK_HTMLAREA")
        if not area:
            return None
        link = area.find("a", href=re.compile(r"^mailto:", re.IGNORECASE))
        if link:
            return link.get("href", "").replace("mailto:", "").strip()
        return clean_text(area.get_text())

    def _extract_announcement_link(self, soup):
        """Extract the announcement URL from the detail page HTML areas."""
        for area_id in ("win0divNY_GG_SRCH_WRK_HTMLAREA2", "win0divNY_GG_SRCH_WRK_HTML_AREA_01"):
            area = soup.find(id=area_id)
            if not area:
                continue
            link = area.find("a", href=True)
            if link:
                href = link.get("href", "").strip()
                if href and href.startswith("http"):
                    return href
        return None

    def _extract_document_urls(self, soup):
        """Extract any downloadable document URLs from the detail page."""
        doc_urls = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "").strip()
            if any(href.lower().endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
                if href.startswith("http") and href not in doc_urls:
                    doc_urls.append(href)

        announcement = self._extract_announcement_link(soup)
        if announcement and announcement not in doc_urls:
            doc_urls.insert(0, announcement)

        return doc_urls[:15]

    def _click_return_to_search(self, driver):
        """Click the 'Return to Search' button to go back to the listing."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "NY_GG_SRCH_WRK_RETURN_PB"))
            )
            driver.execute_script("arguments[0].click();", btn)

            WebDriverWait(driver, RETURN_LOAD_WAIT).until(
                EC.presence_of_element_located((By.ID, "AUC_NAME_LNK$0"))
            )
            time.sleep(random.uniform(2, 4))
        except Exception as exc:
            logger.warning(f"NY Grants: 'Return to Search' failed: {exc}")
            self._ensure_on_main_page(driver)

    def _ensure_on_main_page(self, driver):
        """Fallback: reload the main page if we can't navigate back."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        logger.info("NY Grants: reloading main page as fallback...")
        driver.switch_to.default_content()
        driver.get(BASE_URL)

        try:
            WebDriverWait(driver, INITIAL_LOAD_WAIT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

        time.sleep(random.uniform(8, 14))

        self._switch_to_peoplesoft_frame(driver)

        try:
            WebDriverWait(driver, INITIAL_LOAD_WAIT).until(
                EC.presence_of_element_located((By.ID, "AUC_NAME_LNK$0"))
            )
        except Exception:
            pass
        time.sleep(random.uniform(3, 5))

    def parse_opportunity(self, element):
        return None


def get_ny_grants_scrapers():
    """Create scraper instances for the NY Grants Gateway."""
    return [NewYorkGrantsScraper()]
