import os
import signal
import subprocess
import re
import threading
import requests
import time
import random
from abc import ABC, abstractmethod
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from config.settings import config
from utils.logger import logger
# BaseIvaluaScraper.parse_ivalua_row uses these helpers; they were missing
# before, which made every row raise NameError → silently dropped by a bare
# `except: return None`. Importing them at module scope makes the latent bug
# fixable and observable.
from utils.helpers import clean_text, parse_date, categorize_opportunity

SELENIUM_DELAY_RANGE = (config.SELENIUM_DELAY_MIN, config.SELENIUM_DELAY_MAX)


def _detect_chrome_binary():
    """Locate a usable Chrome/Chromium binary on the system.

    Returns ``(path, major_version)`` or ``(None, None)``.
    """
    candidates = (
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/opt/google/chrome/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
    )
    import shutil
    for path in candidates:
        if not os.path.exists(path) and shutil.which(path) is None:
            continue
        try:
            out = subprocess.check_output(
                [path, '--version'], stderr=subprocess.STDOUT, text=True, timeout=10
            )
            m = re.search(r'(\d+)\.', out)
            if m:
                return path, int(m.group(1))
        except Exception:
            continue
    return None, None


def _detect_chrome_major_version():
    """Best-effort major Chrome/Chromium version for undetected_chromedriver."""
    _, version = _detect_chrome_binary()
    return version


class SeleniumDriverManager:
    """Manages a single shared headless Chrome instance across all scrapers."""

    _driver = None
    _current_proxy = None
    # PIDs we spawned, so we can SIGKILL leaked Chrome/chromedriver subprocesses
    # if the soft ``driver.quit()`` fails (e.g. chromedriver died mid-session).
    _tracked_pids = set()

    @classmethod
    def get_driver(cls, use_proxy=False, force_new=False):
        # ENABLE_FREE_PROXY gates the entire fp.fp.FreeProxy code path. When
        # it's off (the default), any caller passing use_proxy=True silently
        # gets a direct-connection driver. This prevents the shared Chrome
        # driver from being torn down + rebuilt between every scraper that
        # asks for a proxy (which previously caused crashes when free-proxy
        # returned None and the driver kept toggling between proxied and
        # direct mode).
        if use_proxy and not config.ENABLE_FREE_PROXY:
            use_proxy = False

        # Determine if we need to restart the driver for proxy change
        needs_restart = False
        if force_new or (use_proxy and not cls._current_proxy) or (not use_proxy and cls._current_proxy):
            needs_restart = True
            
        if cls._driver is not None:
            if needs_restart:
                cls.quit()
            else:
                try:
                    cls._driver.title
                    return cls._driver
                except Exception:
                    logger.warning("Shared Selenium driver is dead, restarting...")
                    cls._kill_tracked_pids()
                    cls._driver = None

        try:
            import undetected_chromedriver as uc

            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--log-level=3')
            options.add_argument('--dns-prefetch-disable')
            options.add_argument("--disable-blink-features=AutomationControlled")
            # Stability tweaks for low-memory hosts and long-running cron jobs:
            # avoid Chrome's memory-pressure SIGTERM, cap renderer JS heap.
            options.add_argument('--memory-pressure-off')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-features=TranslateUI,site-per-process')
            
            # --- Network Evasion (Free Proxy) ---
            proxy_url = None
            if use_proxy:
                try:
                    from fp.fp import FreeProxy
                    logger.info("Fetching a free US proxy for evasion...")
                    proxy_url = FreeProxy(country_id=['US'], https=True).get()
                    if proxy_url:
                        logger.info(f"Using Free Proxy: {proxy_url}")
                        options.add_argument(f'--proxy-server={proxy_url}')
                        cls._current_proxy = proxy_url
                except Exception as proxy_e:
                    logger.error(f"Failed to fetch proxy: {proxy_e}")
                    cls._current_proxy = None

            browser_path, version_main = _detect_chrome_binary()
            if version_main is None:
                logger.error("Chrome/Chromium not found on this system.")
                return None

            if browser_path:
                options.binary_location = browser_path

            cls._driver = uc.Chrome(
                options=options,
                headless=True,
                use_subprocess=True,
                version_main=version_main,
                browser_executable_path=browser_path,
            )

            # Track child PIDs so cleanup can SIGKILL orphans if .quit() fails.
            cls._tracked_pids = set()
            try:
                # chromedriver subprocess (Selenium service)
                svc_proc = getattr(getattr(cls._driver, 'service', None), 'process', None)
                if svc_proc and getattr(svc_proc, 'pid', None):
                    cls._tracked_pids.add(svc_proc.pid)
                # Chrome browser process (set by undetected_chromedriver)
                browser_pid = getattr(cls._driver, 'browser_pid', None)
                if browser_pid:
                    cls._tracked_pids.add(browser_pid)
            except Exception:
                pass

            # Stealth: patch navigator.webdriver
            cls._driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            
            # Increase timeout since free proxies are slow
            timeout_val = 60 if use_proxy else 45
            cls._driver.set_page_load_timeout(timeout_val)

            realistic_ua = (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                f'Chrome/{version_main}.0.0.0 Safari/537.36'
            )
            try:
                cls._driver.execute_cdp_cmd(
                    'Network.setUserAgentOverride',
                    {"userAgent": realistic_ua},
                )
            except Exception:
                pass

            proxy_str = f" (Proxy: {cls._current_proxy})" if cls._current_proxy else ""
            logger.info(f"Shared Selenium driver initialized{proxy_str}")

            # Wrap driver.get with auto-recovery so cold-start Chrome crashes
            # are transparently retried with a fresh driver instance.
            cls._install_auto_recovery_on(cls._driver)

            return cls._driver
        except Exception as e:
            logger.error(f"Failed to init shared Selenium driver: {e}")
            return None

    @staticmethod
    def resolve_host(host):
        """DNS Fallback for known blocked gov portals."""
        fallbacks = {
            'omb.illinois.gov': '216.124.52.91',
            'procure.ohio.gov': '156.63.155.65',
            'finance.ky.gov': '13.107.246.40', # FrontDoor IP
            'oa.mo.gov': '198.209.11.16',
            'arkansas.gov': '170.94.34.195',
            'doas.ga.gov': '167.196.1.18',
        }
        return fallbacks.get(host, host)

    @classmethod
    def _kill_tracked_pids(cls):
        """SIGKILL any tracked chromedriver/Chrome PIDs that are still alive.

        Used as a fallback when ``driver.quit()`` cannot reach the chromedriver
        port (because chromedriver itself crashed). Without this, every mid-run
        Chrome crash would leak the Chrome process tree on the host — a real
        problem for cron jobs running daily.
        """
        if not cls._tracked_pids:
            return
        for pid in list(cls._tracked_pids):
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                continue
            except Exception:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1.5)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                os.kill(pid, signal.SIGKILL)
                logger.warning(
                    f"SIGKILL'd leaked Chrome/chromedriver PID {pid} "
                    f"(driver.quit may have failed)"
                )
            except Exception as e:
                logger.debug(f"Could not kill PID {pid}: {e}")
        cls._tracked_pids = set()

    @classmethod
    def quit(cls):
        if cls._driver is not None:
            try:
                cls._driver.quit()
                logger.info("Shared Selenium driver closed")
            except Exception as e:
                logger.warning(f"Error closing shared Selenium driver: {e}")
            finally:
                cls._driver = None
                cls._current_proxy = None
        cls._kill_tracked_pids()

    # Exceptions that indicate Chrome/chromedriver itself died and we should
    # rebuild the driver, rather than treat as page-level errors.
    _DRIVER_DEAD_MARKERS = (
        'connection refused',
        'remotedisconnected',
        'remote end closed',
        'session deleted',
        'invalid session id',
        'chrome not reachable',
        'connection aborted',
        'no such window',
        'unable to receive message from renderer',
    )

    @classmethod
    def _is_driver_dead_error(cls, exc):
        msg = str(exc).lower()
        return any(m in msg for m in cls._DRIVER_DEAD_MARKERS)

    @classmethod
    def _hotswap_driver(cls, old_driver, new_driver):
        """Rebind ``old_driver`` to drive ``new_driver``'s chromedriver process.

        After ``get_driver(force_new=True)`` returns a fresh ``uc.Chrome``
        instance, callers that already held a reference to the *old* driver
        still want subsequent commands (``find_elements``, ``page_source``,
        next ``get``) to work. We can't change the caller's variable, but we
        can copy the session-level state from the new instance onto the old
        one — ``RemoteWebDriver`` routes commands via ``self.command_executor``
        keyed by ``self.session_id``, and both are simple attributes.

        Note: we deliberately do NOT touch ``_raw_get`` or re-install the
        auto-recovery wrapper on ``old_driver``. The wrapper from the first
        install is still in place; ``old_driver._raw_get`` is the original
        bound method on ``old_driver``, and that method dispatches via
        ``self.session_id`` / ``self.command_executor`` — both of which now
        point at the new chromedriver. Re-installing the wrapper here was
        causing ``RecursionError`` because ``old_driver.get`` was already
        the wrapper, so ``_raw_get = driver.get`` became wrapper-points-to-
        wrapper.
        """
        if old_driver is new_driver:
            return
        try:
            for attr in ('session_id', 'command_executor', 'browser_pid', 'service'):
                if hasattr(new_driver, attr):
                    try:
                        setattr(old_driver, attr, getattr(new_driver, attr))
                    except Exception:
                        pass
            # Converge cls._driver back on the original Python object so
            # every reference across the process points at the same handle.
            cls._driver = old_driver
            logger.debug("safe_get: hot-swapped rebuilt driver onto original reference")
        except Exception as exc:
            logger.debug(f"Driver hot-swap failed: {exc}")

    @classmethod
    def safe_get(cls, driver, url, retries=2, settle=0):
        """Navigate to ``url`` with cold-start crash recovery.

        First-call ``driver.get(...)`` against heavy gov portals occasionally
        kills the Chrome subprocess (~1 in 3 in our QA). When that happens we
        rebuild the driver via ``get_driver(force_new=True)`` and retry once.
        The rebuilt driver's session is hot-swapped onto the original Python
        instance so the caller's existing ``driver`` reference keeps working.

        Returns the (possibly hot-swapped) driver instance, or ``None`` if
        all retries failed. Scrapers can call this directly, but the driver
        returned by ``get_driver()`` already has its ``.get`` method wrapped
        to do this automatically.
        """
        from selenium.common.exceptions import WebDriverException
        try:
            from urllib3.exceptions import ProtocolError, MaxRetryError
        except Exception:
            ProtocolError = type('ProtocolError', (Exception,), {})
            MaxRetryError = type('MaxRetryError', (Exception,), {})
        try:
            from http.client import RemoteDisconnected
        except Exception:
            RemoteDisconnected = type('RemoteDisconnected', (Exception,), {})
        catch = (
            WebDriverException, ProtocolError, MaxRetryError,
            RemoteDisconnected, ConnectionError, OSError,
        )

        last_err = None
        for attempt in range(retries + 1):
            try:
                # Always go through the *original* underlying get to avoid
                # recursing into the wrapped get when the driver was wrapped
                # via _install_auto_recovery_on.
                raw_get = getattr(driver, '_raw_get', None) or driver.get
                raw_get(url)
                if settle:
                    time.sleep(settle)
                return driver
            except catch as exc:
                last_err = exc
                # MaxRetryError / Connection refused on a localhost chromedriver
                # port is the canonical "session is dead" signal even though
                # the message text doesn't match _DRIVER_DEAD_MARKERS.
                is_dead = cls._is_driver_dead_error(exc) or 'connection refused' in str(exc).lower()
                if not is_dead or attempt >= retries:
                    raise
                logger.warning(
                    f"safe_get: Chrome died navigating to {url} "
                    f"(attempt {attempt + 1}/{retries + 1}); rebuilding driver"
                )
                cls.quit()
                time.sleep(2)
                new_driver = cls.get_driver(use_proxy=bool(cls._current_proxy))
                if new_driver is None:
                    logger.error("safe_get: could not re-acquire Chrome driver")
                    return None
                # Hot-swap the new session onto the caller's existing driver
                # reference so subsequent driver.* calls reach the new
                # chromedriver instead of the dead one.
                cls._hotswap_driver(driver, new_driver)
        if last_err:
            raise last_err
        return driver

    @classmethod
    def _install_auto_recovery_on(cls, driver):
        """Wrap ``driver.get`` so every navigation auto-recovers from cold-start
        Chrome crashes. Stores the original method as ``driver._raw_get``.

        This makes existing per-scraper ``driver.get(url)`` calls resilient
        without needing to edit each scraper.
        """
        if getattr(driver, '_auto_recovery_installed', False):
            return driver
        try:
            # Capture the *real* underlying get only if we haven't already.
            # If a hot-swap re-runs install on the same driver, ``driver.get``
            # is the previously-installed wrapper, not the raw method —
            # blindly overwriting ``_raw_get`` with that wrapper would
            # cause infinite recursion when safe_get calls ``raw_get(url)``.
            if not getattr(driver, '_raw_get', None):
                driver._raw_get = driver.get

            def _wrapped_get(url, *args, **kwargs):
                # If kwargs are passed (rare), defer to raw — Selenium's
                # WebDriver.get only takes url.
                if args or kwargs:
                    return driver._raw_get(url, *args, **kwargs)
                cls.safe_get(driver, url)
                return None

            driver.get = _wrapped_get
            driver._auto_recovery_installed = True
        except Exception as e:
            logger.debug(f"Could not install auto-recovery on driver: {e}")
        return driver


def cleanup_selenium():
    """Close the shared Selenium driver (call at end of scraping session)."""
    SeleniumDriverManager.quit()


class BaseScraper(ABC):
    """Base class for all scrapers"""

    # Class-level per-host throttle: enforces a minimum gap between hits
    # to the same domain across ALL scraper instances in this process.
    # Prevents hammering a single gov host even when one scraper makes
    # many small detail requests in a row.
    _host_last_hit = {}
    _host_lock = threading.Lock()

    # Per-host circuit breaker. If a host returns enough WAF rejections
    # (403/429/503) in a single run, additional requests to that host are
    # short-circuited for the rest of the process. This is the single most
    # important anti-flagging guard for a fixed-IP deployment (Chris server)
    # — once a gov WAF starts flagging us, every additional retry from the
    # same IP makes the eventual ban longer.
    _HOST_FAIL_THRESHOLD = 5
    _host_failures = {}
    _host_suspended = set()

    def __init__(self, source_name):
        self.source_name = source_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                     'image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
        self.opportunities = []
        self._new_count = 0
        self._dup_count = 0
        self._max_new = config.MAX_NEW_PER_SCRAPER

    @classmethod
    def _throttle_host(cls, url):
        """Enforce a minimum interval between hits to the same host."""
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return
        if not host:
            return
        with cls._host_lock:
            last = cls._host_last_hit.get(host, 0.0)
            elapsed = time.time() - last
            min_gap = config.PER_HOST_MIN_INTERVAL
            if elapsed < min_gap:
                wait = (min_gap - elapsed) + random.uniform(0.0, 0.5)
                time.sleep(wait)
            cls._host_last_hit[host] = time.time()

    @classmethod
    def _is_host_suspended(cls, url):
        """Check whether the host for ``url`` has been WAF-suspended this run."""
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return host in cls._host_suspended

    @classmethod
    def _record_host_failure(cls, url, status_code=None):
        """Bump the failure counter for ``url``'s host; suspend on threshold.

        Once a host reaches the threshold, subsequent ``fetch_page`` calls
        skip the network entirely and return ``None`` so we don't dig the
        IP-flag hole deeper. Status-only failures (network errors) and
        anti-bot statuses (403/429/503) both count.
        """
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return
        if not host:
            return
        with cls._host_lock:
            if host in cls._host_suspended:
                return
            count = cls._host_failures.get(host, 0) + 1
            cls._host_failures[host] = count
            if count >= cls._HOST_FAIL_THRESHOLD:
                cls._host_suspended.add(host)
                logger.warning(
                    f"Host circuit-breaker tripped for {host} after {count} "
                    f"WAF rejections (status={status_code}). Skipping further "
                    f"requests this run to avoid an IP ban."
                )

    @staticmethod
    def _polite_sleep():
        """Sleep SCRAPER_DELAY plus random jitter so traffic isn't robotic."""
        base = max(config.SCRAPER_DELAY, 0.5)
        time.sleep(base + random.uniform(0.3, 1.5))

    @staticmethod
    def _backoff_sleep(attempt, response=None):
        """Sleep with exponential backoff + jitter; honors Retry-After header."""
        retry_after = None
        if response is not None:
            ra = response.headers.get('Retry-After')
            if ra:
                try:
                    retry_after = float(ra)
                except (TypeError, ValueError):
                    retry_after = None

        if retry_after is not None:
            wait = min(retry_after, 90.0) + random.uniform(0.5, 2.0)
        else:
            base = max(config.SCRAPER_DELAY, 1.0)
            wait = (2 ** attempt) * base + random.uniform(1.0, 3.0)
            wait = min(wait, 60.0)
        time.sleep(wait)

    def reached_limit(self):
        """True when we've collected enough NEW opportunities for this run."""
        if self._max_new <= 0:
            return False
        return self._new_count >= self._max_new

    def add_opportunity(self, opp):
        """Store an opportunity to the DB immediately and track new vs dup.

        Every opportunity is written to the database the moment it is
        scraped, so nothing is lost if the process is interrupted.
        Only genuinely NEW records count toward the per-scraper limit.

        Returns True if the opportunity is NEW, False if duplicate/update.
        """
        from database.db import db
        
        source_url = opp.get('source_url', '')
        
        # Validation: Reject obviously invalid/dead links or generic noise
        NOISE_DOMAINS = [
            'denotificationservices.bbcportal.com',
            'bbcportal.com/registration',
            'public.govdelivery.com',
            'subscriberhelp.govdelivery.com',
        ]
        
        if source_url:
            url_lower = source_url.lower()
            if url_lower.startswith('javascript:'):
                logger.warning(f"{self.source_name}: Skipping invalid source_url: {source_url}")
                return False
            if any(domain in url_lower for domain in NOISE_DOMAINS):
                logger.info(f"{self.source_name}: Filtering out generic noise URL: {source_url}")
                return False

        is_new = not (source_url and db.opportunity_exists(source_url))

        opp.setdefault('opportunity_type', None)
        try:
            db.insert_opportunity(opp)
        except Exception as exc:
            logger.debug(f"{self.source_name}: DB write failed: {exc}")

        self.opportunities.append(opp)

        if is_new:
            self._new_count += 1
            if self._max_new > 0 and self._new_count >= self._max_new:
                logger.info(
                    f"{self.source_name}: reached {self._max_new} new opportunities limit — stopping early"
                )
        else:
            self._dup_count += 1

        return is_new


    def track_new(self):
        """Legacy counter — prefer add_opportunity() instead."""
        self._new_count += 1
        return self._new_count
    
    def fetch_page(self, url, method='GET', timeout=15, **kwargs):
        """Polite, retry-aware fetch with rate-limit defenses.

        Strategy:
          - Host circuit breaker: if a host has tripped the WAF threshold
            this run, skip immediately (don't bury the IP further).
          - Per-host throttle: never hit the same domain faster than
            ``config.PER_HOST_MIN_INTERVAL`` seconds (across all scrapers).
          - Rotate User-Agent on every attempt.
          - Polite delay (with jitter) after every successful fetch.
          - DNS / connection failures fail FAST (no retry burn).
          - 429 / 503: honour ``Retry-After`` header; otherwise exponential
            backoff with jitter, capped at 60s.
          - 403 Forbidden: try a single cloudscraper bypass before giving up.
          - All retries use exponential backoff + jitter, never a fixed sleep.
        """
        if self._is_host_suspended(url):
            logger.debug(f"Skipping {url} — host suspended this run")
            return None

        self._throttle_host(url)
        last_exc = None

        for attempt in range(config.MAX_RETRIES):
            self.session.headers['User-Agent'] = random.choice(config.USER_AGENTS)

            try:
                if method == 'GET':
                    response = self.session.get(url, timeout=timeout, **kwargs)
                else:
                    response = self.session.post(url, timeout=timeout, **kwargs)

                if response.status_code in (429, 503):
                    logger.warning(
                        f"Rate-limited ({response.status_code}) on {url} "
                        f"(attempt {attempt + 1}/{config.MAX_RETRIES})"
                    )
                    self._record_host_failure(url, response.status_code)
                    if self._is_host_suspended(url):
                        return None
                    if attempt < config.MAX_RETRIES - 1:
                        self._backoff_sleep(attempt, response)
                        continue
                    logger.error(f"Gave up on {url} after rate-limit retries")
                    return None

                if response.status_code == 403:
                    logger.debug(f"403 on {url}, trying cloudscraper bypass...")
                    cf_response = self._fetch_with_cloudscraper(
                        url, method, timeout, **kwargs
                    )
                    if cf_response is not None:
                        self._polite_sleep()
                        return cf_response
                    self._record_host_failure(url, 403)
                    return None

                response.raise_for_status()
                self._polite_sleep()
                return response

            except (requests.ConnectionError, requests.Timeout) as e:
                logger.warning(f"Network failure for {url}: {e}")
                self._record_host_failure(url, 'network')
                return None

            except requests.RequestException as e:
                last_exc = e
                logger.warning(
                    f"Attempt {attempt + 1}/{config.MAX_RETRIES} failed for {url}: {e}"
                )
                if attempt < config.MAX_RETRIES - 1:
                    self._backoff_sleep(attempt)

        logger.error(
            f"Failed to fetch {url} after {config.MAX_RETRIES} attempts: {last_exc}"
        )
        return None

    def _fetch_with_cloudscraper(self, url, method='GET', timeout=15, **kwargs):
        """Single cloudscraper attempt to bypass Cloudflare/basic 403 challenges."""
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
            )
            scraper.headers.update(self.session.headers)
            if method == 'GET':
                resp = scraper.get(url, timeout=timeout, **kwargs)
            else:
                resp = scraper.post(url, timeout=timeout, **kwargs)
            if resp.status_code == 200:
                return resp
        except Exception as e:
            logger.debug(f"Cloudscraper bypass failed for {url}: {e}")
        return None
    
    def parse_html(self, html_content):
        """Parse HTML content with BeautifulSoup"""
        return BeautifulSoup(html_content, 'lxml')
    
    @abstractmethod
    def scrape(self):
        """Main scraping method - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    def parse_opportunity(self, element):
        """Parse individual opportunity - must be implemented by subclasses"""
        pass
    
    def enrich_from_documents(self, opp):
        """Download PDFs listed in opp['document_urls'] and backfill empty fields."""
        from parsers.parser_utils import OpportunityEnricher
        try:
            OpportunityEnricher.enrich_with_documents(opp)
        except Exception as exc:
            logger.debug(f"{self.source_name}: PDF enrichment failed: {exc}")
        return opp

    def get_opportunities(self):
        """Return collected opportunities"""
        return self.opportunities
    
    def log_summary(self):
        """Log scraping summary"""
        total = len(self.opportunities)
        logger.info(
            f"{self.source_name}: {total} scraped | {self._new_count} new | {self._dup_count} duplicates"
        )

class BaseIvaluaScraper(BaseScraper):
    """Base class for Ivalua-based portals (Alabama, Arizona, Maryland, etc.)"""
    
    def __init__(self, source_name, base_url, location):
        super().__init__(source_name)
        self.base_url = base_url
        self.location = location

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper...")
        driver = SeleniumDriverManager.get_driver(use_proxy=True)
        if not driver: return self.opportunities
        
        try:
            driver.get(self.base_url)
            time.sleep(random.uniform(10, 15))
            
            # Check for Cloudflare
            if "Just a moment" in driver.page_source:
                logger.info(f"  {self.source_name}: Waiting for Cloudflare bypass...")
                time.sleep(15)
                
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Ivalua grids usually have 'body_x_grid_grd'
            table = soup.find('table', id='body_x_grid_grd')
            if not table:
                table = soup.find('table', class_='iv-grid-view')
                
            if not table:
                logger.warning(f"  {self.source_name}: No grid found")
                return self.opportunities
                
            tbody = table.find('tbody')
            if not tbody:
                # Some versions put rows directly in the table
                rows = table.find_all('tr', class_=lambda x: x and 'iv-grid-row' in x)
            else:
                rows = tbody.find_all('tr')
                
            for row in rows:
                if self.reached_limit(): break
                opp = self.parse_ivalua_row(row)
                if opp: self.add_opportunity(opp)
        except Exception as e:
            logger.error(f"  {self.source_name} error: {e}")
            
        self.log_summary()
        return self.opportunities

    def parse_opportunity(self, row):
        return self.parse_ivalua_row(row)

    def parse_ivalua_row(self, row):
        cells = row.find_all('td')
        if len(cells) < 4:
            return None
        try:
            row_id = row.get('data-id', '')
            opp_number = clean_text(cells[1].get_text(strip=True))
            title = clean_text(cells[2].get_text(strip=True))

            if not title or len(title) < 5:
                return None

            # Ivalua columns vary, but Agency is usually after title
            org = clean_text(cells[5].get_text(strip=True)) if len(cells) > 5 else ''
            deadline_str = clean_text(cells[-1].get_text(strip=True))

            # Detail URL
            domain = self.base_url.split('/page.aspx')[0]
            if row_id:
                source_url = f"{domain}/page.aspx/en/bpm/process_manage_extranet/{row_id}"
            else:
                source_url = self.base_url

            return {
                'title': title,
                'organization': org or f"State of {self.location}",
                'description': None,
                'eligibility': None,
                'funding_amount': None,
                'deadline': parse_date(deadline_str),
                'category': categorize_opportunity(title, ''),
                'location': self.location,
                'source': self.source_name,
                'source_url': source_url,
                'opportunity_number': opp_number,
                'posted_date': None,
                'document_urls': [],
                'opportunity_type': 'rfp',
            }
        except Exception as exc:
            logger.debug(f"{self.source_name}: Ivalua row parse failed: {exc}")
            return None
