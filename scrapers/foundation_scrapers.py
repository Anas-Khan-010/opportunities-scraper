import os
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, parse_date, categorize_opportunity
from database.db import db

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


class DukeResearchFundingScraper(BaseScraper):
    """
    Scraper for Duke Research Funding open opportunities.

    Uses Selenium for listing navigation (handles Anubis JS anti-bot challenge
    and pagination), then attempts requests-based detail parsing with Selenium
    fallback.  All configurable values are read from environment / settings.
    """

    ANTIBOT_MARKERS = [
        "checking your connection",
        "anubis",
        "proof-of-work",
        "please enable javascript",
        "access denied",
        "ddos protection",
        "cloudflare",
    ]
    NO_RESULTS_MARKERS = [
        "no opportunities found",
        "no results found",
        "0 results",
    ]
    CARD_LINK_SELECTORS = [
        "a.opportunity--teaser__card-link[href]",
        ".more-link a.more-link[href]",
    ]
    FALLBACK_LINK_SELECTORS = [
        "a.opportunity--teaser__card-link[href]",
        ".views-row a.opportunity--teaser__card-link[href]",
        ".views-row .more-link a.more-link[href]",
        ".view-content .views-row a[href]",
    ]
    BLOCKED_PATH_PREFIXES = (
        "/search-results",
        "/user",
        "/node",
        "/taxonomy",
        "/admin",
    )
    NEXT_PAGE_SELECTORS = [
        "a[rel='next']",
        "li.pager__item--next a",
        "a[title*='next page' i]",
        "a[aria-label*='next' i]",
        ".pager a[href*='page=']",
    ]

    def __init__(self):
        super().__init__("Duke Research Funding")
        self.base_url = config.DUKE_BASE_URL
        self.listing_url = config.DUKE_LISTING_URL
        self._driver = None
        self._wait = None
        self._headless = self._env_bool("DUKE_HEADLESS", True)
        self._challenge_wait = self._env_int(
            "DUKE_CHALLENGE_WAIT_SECONDS", 90
        )
        self._headless_challenge_wait = self._env_int(
            "DUKE_HEADLESS_CHALLENGE_WAIT_SECONDS", 240
        )
        self._listing_attempts = self._env_int("DUKE_LISTING_MAX_ATTEMPTS", 3)
        self._max_pages = self._env_int("DUKE_MAX_PAGES", 10)
        self._page_load_timeout = self._env_int("DUKE_PAGE_LOAD_TIMEOUT", 60)

    # ------------------------------------------------------------------
    # Environment helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _env_bool(key, default):
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _env_int(key, default):
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    # ------------------------------------------------------------------
    # Selenium driver lifecycle
    # ------------------------------------------------------------------

    def _init_driver(self):
        if self._driver is not None:
            return True
        try:
            options = Options()
            if self._headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--lang=en-US,en")
            options.add_argument(f"--user-agent={config.USER_AGENTS[0]}")
            options.add_experimental_option(
                "excludeSwitches", ["enable-automation", "enable-logging"]
            )
            options.add_experimental_option("useAutomationExtension", False)

            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(self._page_load_timeout)
            self._wait = WebDriverWait(self._driver, 45)
            self._apply_stealth_patches()
            logger.info(
                f"Duke driver initialized (headless={self._headless}, "
                f"challenge_wait={self._challenge_wait}s, "
                f"headless_challenge_wait={self._headless_challenge_wait}s)"
            )
            return True
        except WebDriverException as e:
            logger.error(f"Duke driver init failed: {e}")
            self._driver = None
            self._wait = None
            return False

    def _quit_driver(self):
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                logger.warning(f"Duke driver quit error: {e}")
            finally:
                self._driver = None
                self._wait = None

    def _apply_stealth_patches(self):
        if not self._driver:
            return
        try:
            self._driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                        "Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});"
                        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4]});"
                        "window.chrome=window.chrome||{runtime:{}};"
                    )
                },
            )
        except Exception as e:
            logger.debug(f"Stealth patch skipped: {e}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape(self, max_pages=None, max_opportunities=None):
        """
        Interleaved flow: load one listing page, parse its detail links,
        then advance.  Partial results are rescued on KeyboardInterrupt.
        """
        if max_pages is None:
            max_pages = self._max_pages

        logger.info(
            f"Starting {self.source_name} scraper (max_pages={max_pages})..."
        )

        if not self._init_driver():
            self.log_summary()
            return self.opportunities

        skipped_existing = 0
        skipped_dupe = 0
        parsed_ok = 0
        parsed_fail = 0
        total_collected = 0
        pages_visited = 0
        interrupted = False
        seen_urls: set[str] = set()

        try:
            if not self._load_listing_with_retries():
                raise RuntimeError("Unable to load Duke listing after retries")

            while pages_visited < max_pages:
                page_urls = self._extract_opportunity_links_from_page()

                new_on_page = []
                for url in page_urls:
                    canonical = self._canonicalize_url(url)
                    if not canonical or canonical in seen_urls:
                        skipped_dupe += 1
                        continue
                    seen_urls.add(canonical)
                    new_on_page.append(canonical)

                total_collected += len(new_on_page)
                logger.info(
                    f"Duke listing page {pages_visited + 1}: "
                    f"found {len(page_urls)} links, {len(new_on_page)} new"
                )

                for canonical_url in new_on_page:
                    if max_opportunities and parsed_ok >= max_opportunities:
                        break

                    if db.opportunity_exists(canonical_url):
                        skipped_existing += 1
                        continue

                    opportunity = self._fetch_and_parse_detail(canonical_url)
                    if opportunity:
                        self.opportunities.append(opportunity)
                        parsed_ok += 1
                        logger.info(
                            f"[page {pages_visited + 1}] Parsed ({parsed_ok}): "
                            f"{opportunity['title'][:80]}"
                        )
                    else:
                        parsed_fail += 1
                        logger.warning(
                            f"[page {pages_visited + 1}] Failed: {canonical_url}"
                        )

                pages_visited += 1

                if max_opportunities and parsed_ok >= max_opportunities:
                    logger.info(
                        f"Reached max_opportunities cap ({max_opportunities})"
                    )
                    break

                if not self._go_to_next_page():
                    logger.info("No more listing pages available")
                    break

                status = self._wait_for_listing_ready(timeout=45)
                if status.get("antibot"):
                    logger.warning(
                        "Anti-bot detected after pagination — stopping"
                    )
                    self._log_listing_diagnostics("pagination-antibot")
                    break
                self._sync_cookies()

        except KeyboardInterrupt:
            interrupted = True
            logger.warning(
                f"User interrupted {self.source_name}. "
                f"Rescuing {len(self.opportunities)} opportunities."
            )
        except RuntimeError as e:
            logger.error(f"{self.source_name}: {e}")
        except Exception as e:
            logger.error(f"Error scraping {self.source_name}: {e}")
        finally:
            self._quit_driver()

        logger.info(
            f"{self.source_name} summary: pages={pages_visited}, "
            f"collected={total_collected}, skipped_existing={skipped_existing}, "
            f"skipped_dupe={skipped_dupe}, parsed_ok={parsed_ok}, "
            f"parsed_fail={parsed_fail}"
        )
        self.log_summary()

        if interrupted:
            raise KeyboardInterrupt

        return self.opportunities

    def parse_opportunity(self, element):
        if isinstance(element, dict):
            return element
        return None

    # ------------------------------------------------------------------
    # Listing page loading & readiness
    # ------------------------------------------------------------------

    def _load_listing_with_retries(self):
        backoff = [5, 10, 20]
        for attempt in range(1, self._listing_attempts + 1):
            try:
                self._driver.get(self.listing_url)
                status = self._wait_for_listing_ready(timeout=60)
                self._sync_cookies()

                if status.get("ready"):
                    return True

                if status.get("antibot"):
                    self._wait_for_challenge_resolution()
                    self._wait_for_manual_challenge_clearance()
                    status = self._wait_for_listing_ready(timeout=45)
                    if status.get("ready"):
                        return True

                self._log_listing_diagnostics(
                    f"not-ready-attempt-{attempt}"
                )
            except TimeoutException as e:
                logger.warning(
                    f"Listing attempt {attempt}/{self._listing_attempts} "
                    f"timed out: {e}"
                )
            except WebDriverException as e:
                logger.warning(
                    f"Listing attempt {attempt}/{self._listing_attempts} "
                    f"driver error: {e}"
                )
            except Exception as e:
                logger.warning(
                    f"Listing attempt {attempt}/{self._listing_attempts} "
                    f"failed: {e}"
                )

            if attempt < self._listing_attempts:
                delay = backoff[min(attempt - 1, len(backoff) - 1)]
                logger.info(f"Retrying Duke listing in {delay}s...")
                time.sleep(delay)

        logger.error("Unable to load Duke listing after all retries")
        return False

    def _wait_for_listing_ready(self, timeout=60):
        status = {"ready": False, "antibot": False, "no_results": False}
        try:
            self._wait_for_document_ready(timeout=min(timeout, 30))
        except TimeoutException:
            logger.warning("Document readyState timeout on listing page")

        deadline = time.time() + timeout
        while time.time() < deadline:
            html = self._driver.page_source or ""
            title = self._driver.title or ""

            if self._is_antibot_page(html, title):
                status["antibot"] = True
                time.sleep(2)
                continue

            links = self._extract_opportunity_links_from_page()
            if links:
                status["ready"] = True
                status["antibot"] = False
                return status

            if self._listing_has_no_results():
                status["ready"] = True
                status["no_results"] = True
                status["antibot"] = False
                return status

            time.sleep(2)

        logger.warning("Timed out waiting for listing links")
        self._log_listing_diagnostics("listing-timeout")
        return status

    # ------------------------------------------------------------------
    # Anti-bot detection & waits
    # ------------------------------------------------------------------

    def _is_antibot_page(self, html, title=""):
        blob = f"{title or ''} {html or ''}".lower()
        return any(m in blob for m in self.ANTIBOT_MARKERS)

    def _listing_has_no_results(self):
        try:
            text = (self._driver.page_source or "").lower()
            return any(m in text for m in self.NO_RESULTS_MARKERS)
        except Exception:
            return False

    def _wait_for_challenge_resolution(self):
        if not self._headless or self._headless_challenge_wait <= 0:
            return
        html = self._driver.page_source or ""
        title = self._driver.title or ""
        if not self._is_antibot_page(html, title):
            return

        logger.warning(
            f"Anti-bot detected (headless). Waiting up to "
            f"{self._headless_challenge_wait}s for resolution..."
        )
        deadline = time.time() + self._headless_challenge_wait
        while time.time() < deadline:
            html = self._driver.page_source or ""
            title = self._driver.title or ""
            if not self._is_antibot_page(html, title):
                logger.info("Challenge cleared (headless)")
                return
            time.sleep(3)

    def _wait_for_manual_challenge_clearance(self):
        if self._headless or self._challenge_wait <= 0:
            return
        html = self._driver.page_source or ""
        title = self._driver.title or ""
        if not self._is_antibot_page(html, title):
            return

        logger.warning(
            f"Anti-bot detected (interactive). Waiting up to "
            f"{self._challenge_wait}s for manual solve..."
        )
        deadline = time.time() + self._challenge_wait
        while time.time() < deadline:
            html = self._driver.page_source or ""
            title = self._driver.title or ""
            if not self._is_antibot_page(html, title):
                logger.info("Challenge cleared (interactive)")
                return
            time.sleep(2)

    def _wait_for_detail_challenge(self, url, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            html = self._driver.page_source or ""
            title = self._driver.title or ""
            if not self._is_antibot_page(html, title):
                logger.debug(f"Detail challenge cleared: {url}")
                return
            time.sleep(2)

    def _wait_for_document_ready(self, timeout=30):
        WebDriverWait(self._driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    # ------------------------------------------------------------------
    # Link extraction from listing pages
    # ------------------------------------------------------------------

    def _extract_opportunity_links_from_page(self):
        links = []
        seen: set[str] = set()

        cards = self._driver.find_elements(
            By.CSS_SELECTOR, ".view-content .views-row"
        )
        for card in cards:
            href = self._first_href_from_card(card)
            if not href or not self._is_valid_detail_url(href):
                continue
            canonical = self._canonicalize_url(href)
            if canonical and canonical not in seen:
                seen.add(canonical)
                links.append(canonical)

        if links:
            return links

        for selector in self.FALLBACK_LINK_SELECTORS:
            for anchor in self._driver.find_elements(By.CSS_SELECTOR, selector):
                href = (anchor.get_attribute("href") or "").strip()
                if not self._is_valid_detail_url(href):
                    continue
                canonical = self._canonicalize_url(href)
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    links.append(canonical)
        return links

    def _first_href_from_card(self, card):
        for selector in self.CARD_LINK_SELECTORS:
            try:
                elem = card.find_element(By.CSS_SELECTOR, selector)
                href = (elem.get_attribute("href") or "").strip()
                if href:
                    return href
            except Exception:
                continue
        return None

    def _is_valid_detail_url(self, href):
        if not href:
            return False
        canonical = self._canonicalize_url(href)
        if not canonical:
            return False
        parts = urlsplit(canonical)
        path = (parts.path or "").strip()
        if not path or path == "/":
            return False
        if any(path.lower().startswith(p) for p in self.BLOCKED_PATH_PREFIXES):
            return False
        return path.count("/") == 1

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _go_to_next_page(self):
        current_url = self._driver.current_url
        for selector in self.NEXT_PAGE_SELECTORS:
            candidates = self._driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in candidates:
                try:
                    if not btn.is_displayed() or not btn.is_enabled():
                        continue
                    text = (btn.text or "").lower()
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    title = (btn.get_attribute("title") or "").lower()
                    rel = (btn.get_attribute("rel") or "").lower()
                    if any(
                        "next" in attr or "›" in attr
                        for attr in (text, aria, title, rel)
                    ):
                        self._driver.execute_script(
                            "arguments[0].click();", btn
                        )
                        self._wait.until(
                            lambda d: d.current_url != current_url
                        )
                        return True
                except (TimeoutException, WebDriverException):
                    continue
                except Exception:
                    continue
        return False

    # ------------------------------------------------------------------
    # Detail page fetching & parsing
    # ------------------------------------------------------------------

    def _fetch_and_parse_detail(self, url):
        opp = self._parse_detail_via_requests(url)
        if opp:
            return opp
        return self._parse_detail_via_selenium(url)

    def _parse_detail_via_requests(self, url):
        self._sync_cookies()
        response = self.fetch_page(url)
        if not response:
            return None
        content = response.text or ""
        if self._is_antibot_page(content):
            return None
        soup = self.parse_html(response.content)
        return self._parse_detail_soup(soup, url)

    def _parse_detail_via_selenium(self, url):
        try:
            self._driver.get(url)
            self._wait_for_document_ready(timeout=30)

            if self._is_antibot_page(
                self._driver.page_source, self._driver.title
            ):
                self._wait_for_detail_challenge(url, timeout=60)
                if self._is_antibot_page(
                    self._driver.page_source, self._driver.title
                ):
                    logger.warning(
                        f"Selenium detail still blocked: {url}"
                    )
                    return None

            self._wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
            )
            soup = self.parse_html(self._driver.page_source)
            self._sync_cookies()
            return self._parse_detail_soup(soup, url)
        except TimeoutException:
            logger.warning(f"Selenium detail timed out: {url}")
            return None
        except WebDriverException as e:
            logger.warning(f"Selenium detail driver error for {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Selenium detail parse failed for {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Detail page field extraction
    # ------------------------------------------------------------------

    def _parse_detail_soup(self, soup, url):
        article = soup.select_one("article.opportunity") or soup

        title = self._extract_title(article)
        if not title:
            return None

        description = self._extract_field_text(
            article, "field--name-field-purpose"
        )
        eligibility = self._extract_field_text(
            article, "field--name-field-requirements"
        )
        amount_description = self._extract_field_text(
            article, "field--name-field-amount-description"
        )

        amount_exact = self._extract_field_value(
            article, "field--name-field-amount"
        )
        amount_from_desc = self._extract_amount_from_text(
            amount_description or description
        )
        funding_amount = clean_text(amount_exact or amount_from_desc)

        organization = self._extract_organization(article)

        posted_raw = self._extract_sidebar_label_value(article, "Posted")
        if not posted_raw:
            meta_date = article.select_one(".opportunity__meta__date")
            if meta_date:
                match = re.search(
                    r"(\d{1,2}/\d{1,2}/\d{4})", meta_date.get_text()
                )
                if match:
                    posted_raw = match.group(1)

        deadline_raw = self._extract_deadline(article)

        discipline = self._extract_field_link_texts(
            article, "field--name-field-discipline"
        )
        topic_areas = self._extract_field_link_texts(
            article, "field--name-field-keywords"
        )
        funding_type = self._extract_field_link_texts(
            article, "field--name-field-funding-type"
        )
        eligibility_tags = self._extract_field_link_texts(
            article, "field--name-field-eligibility"
        )

        if eligibility_tags and eligibility:
            eligibility = f"{eligibility_tags}. {eligibility}"
        elif eligibility_tags:
            eligibility = eligibility_tags

        category_hint = self._join_parts(
            [funding_type, discipline, topic_areas, title, description]
        )
        category = categorize_opportunity(title, category_hint or "")

        canonical_url = self._canonicalize_url(url)
        slug = (
            canonical_url.rstrip("/").split("/")[-1]
            if canonical_url
            else None
        )

        return {
            "title": title,
            "organization": organization,
            "description": description,
            "eligibility": eligibility,
            "funding_amount": funding_amount,
            "deadline": parse_date(deadline_raw) if deadline_raw else None,
            "category": category,
            "location": "United States",
            "source": self.source_name,
            "source_url": canonical_url,
            "opportunity_number": slug,
            "posted_date": parse_date(posted_raw) if posted_raw else None,
            "document_urls": [],
            "full_document": None,
        }

    # ------------------------------------------------------------------
    # Granular field helpers
    # ------------------------------------------------------------------

    def _extract_title(self, article):
        for selector in ["h1 .field--name-title", "h1", ".page-title"]:
            elem = article.select_one(selector)
            if elem:
                text = clean_text(elem.get_text(" ", strip=True))
                if text:
                    return text
        return None

    def _extract_field_text(self, article, field_class):
        container = article.select_one(f".{field_class}")
        if not container:
            return None
        item = container.select_one(".field__item")
        if item:
            return clean_text(item.get_text(" ", strip=True))
        return clean_text(container.get_text(" ", strip=True))

    def _extract_field_value(self, article, field_class):
        container = article.select_one(f".{field_class}")
        if not container:
            return None
        item = container.select_one(".field__item")
        if item:
            return clean_text(item.get_text(" ", strip=True))
        return None

    def _extract_field_link_texts(self, article, field_class):
        container = article.select_one(f".{field_class}")
        if not container:
            return None
        items = container.select(".field__item")
        texts = [clean_text(i.get_text(" ", strip=True)) for i in items]
        texts = [t for t in texts if t]
        return ", ".join(texts) if texts else None

    def _extract_organization(self, article):
        container = article.select_one(".field--name-field-funding-agency")
        if container:
            link = container.select_one("a")
            if link:
                return clean_text(link.get_text(" ", strip=True))
            item = container.select_one(".field__item")
            if item:
                return clean_text(item.get_text(" ", strip=True))
        return "Duke Research Funding"

    def _extract_deadline(self, article):
        val = self._extract_sidebar_label_value(article, "Deadline")
        if val:
            match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", val)
            if match:
                return match.group(1)

        time_elem = article.select_one(
            ".field--name-field-external-deadline time.datetime"
        )
        if time_elem:
            return clean_text(time_elem.get_text(strip=True))
        return None

    def _extract_sidebar_label_value(self, article, label_text):
        sidebar = article.select_one(".opportunity__sidebar")
        search_in = sidebar if sidebar else article
        label_lower = label_text.lower()

        for field_div in search_in.select("div.field"):
            label_div = field_div.select_one("div.field__label")
            if not label_div:
                continue
            if clean_text(label_div.get_text(strip=True)).lower() != label_lower:
                continue
            items = field_div.select("div.field__item")
            if items:
                return clean_text(
                    " ".join(i.get_text(" ", strip=True) for i in items)
                )
            return None
        return None

    def _extract_amount_from_text(self, text):
        if not text:
            return None
        patterns = [
            r"up to\s*\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|m|b|k))?",
            r"\$[\d,]+(?:\.\d+)?\s*(?:to|-|–)\s*\$[\d,]+(?:\.\d+)?",
            r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|m|b|k))?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return clean_text(match.group(0))
        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _join_parts(parts):
        cleaned = [clean_text(p) for p in parts if clean_text(p)]
        return clean_text(" ".join(cleaned)) if cleaned else None

    def _sync_cookies(self):
        if not self._driver:
            return
        try:
            for cookie in self._driver.get_cookies():
                self.session.cookies.set(
                    cookie.get("name"),
                    cookie.get("value"),
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )
        except Exception as e:
            logger.debug(f"Cookie sync skipped: {e}")

    def _canonicalize_url(self, url):
        if not url:
            return None
        absolute = urljoin(self.base_url, url)
        parts = urlsplit(absolute)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")
        )

    def _log_listing_diagnostics(self, context):
        try:
            title = (self._driver.title or "").strip()
            current_url = self._driver.current_url
            html = self._driver.page_source or ""
            anti_bot = self._is_antibot_page(html, title)
            body = self._driver.find_element(By.TAG_NAME, "body")
            preview = clean_text(body.text or "")[:500]
            logger.warning(
                f"Duke diagnostics [{context}] | url={current_url} | "
                f"title={title[:120]} | anti_bot={anti_bot} | "
                f"preview={preview}"
            )
        except Exception as e:
            logger.warning(f"Duke diagnostics [{context}] failed: {e}")
