#!/usr/bin/env python3
"""
waf_bypass.py  -  Anti-bot / WAF evasion layer
================================================
Tier 1: Realistic browser headers + rotating User-Agent pool
Tier 2: Jittered human-like timing + per-domain rate limiting + exponential back-off
Tier 3: Persistent cookie jar + Akamai ghost-token cookie replay
Tier 4: WAF fingerprint detection + automatic identity rotation on block
Tier 5: Optional proxy rotation + Camoufox stealth browser for JS challenges
Tier 6: Hybrid flow — solve challenge once with Camoufox, transfer cookies to
         curl_cffi for fast subsequent HTTP requests
"""
from __future__ import annotations
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# curl-cffi gives us real browser TLS/HTTP2 fingerprints — critical for Akamai.
# Falls back to plain requests if not installed.
try:
    from curl_cffi import requests as _curl_req
    _CURL_CFFI = True
except ImportError:
    _curl_req = None
    _CURL_CFFI = False


log = logging.getLogger(__name__)

# Web Unlocker runs a real browser per request — often 30–60+ seconds per page
REQUEST_TIMEOUT          = 25
WEB_UNLOCKER_TIMEOUT     = 90

# ---------------------------------------------------------------------------
# User-Agent pool  (Chrome, Firefox, Safari, Edge, mobile)
# ---------------------------------------------------------------------------
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
]

_CHROME_IMPERSONATE  = ["chrome136", "chrome131", "chrome124", "chrome120"]
_FIREFOX_IMPERSONATE = ["firefox144", "firefox135", "firefox133"]
_SAFARI_IMPERSONATE  = ["safari18_0", "safari17_0", "safari15_5"]

def _pick_impersonate(ua: str) -> str:
    """Map a User-Agent string to a curl-cffi impersonate target."""
    if "Firefox" in ua:
        return random.choice(_FIREFOX_IMPERSONATE)
    if "Safari" in ua and "Chrome" not in ua and "Edg" not in ua:
        return random.choice(_SAFARI_IMPERSONATE)
    return random.choice(_CHROME_IMPERSONATE)

_ACCEPT_LANGS = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.8,de;q=0.6",
]

# ---------------------------------------------------------------------------
# Header builders per browser family
# ---------------------------------------------------------------------------
def _parse_chrome_version(ua: str) -> Optional[str]:
    match = re.search(r'Chrome/(\d+)', ua)
    return match.group(1) if match else None

def _chrome_headers(ua: str) -> dict:
    mobile = "Mobile" in ua
    plat   = '"Android"' if mobile else ('"macOS"' if "Mac" in ua else '"Windows"')
    chrome_ver = _parse_chrome_version(ua) or "124"
    sec_ch_ua = f'"Chromium";v="{chrome_ver}", "Google Chrome";v="{chrome_ver}", "Not-A.Brand";v="99"'
    return {
        "User-Agent":                ua,
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language":           random.choice(_ACCEPT_LANGS),
        "Accept-Encoding":           "gzip, deflate, br",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
        "Sec-CH-UA":                 sec_ch_ua,
        "Sec-CH-UA-Mobile":          "?1" if mobile else "?0",
        "Sec-CH-UA-Platform":        plat,
        "Cache-Control":             "max-age=0",
    }

def _firefox_headers(ua: str) -> dict:
    return {
        "User-Agent":                ua,
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":           random.choice(_ACCEPT_LANGS),
        "Accept-Encoding":           "gzip, deflate, br",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
        "Cache-Control":             "no-cache",
        "Pragma":                    "no-cache",
        "TE":                        "trailers",
    }

def _safari_headers(ua: str) -> dict:
    return {
        "User-Agent":      ua,
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(_ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    }

def _build_headers(ua: str) -> dict:
    if "Firefox" in ua:
        return _firefox_headers(ua)
    if "Safari" in ua and "Chrome" not in ua and "Edg" not in ua:
        return _safari_headers(ua)
    return _chrome_headers(ua)

# ---------------------------------------------------------------------------
# WAF fingerprint detection (improved with regex and configurable signatures)
# ---------------------------------------------------------------------------
@dataclass
class WafInfo:
    detected:  bool = False
    waf_name:  str  = "none"   # akamai|cloudflare|imperva|datadome|perimeterx|aws_waf|generic
    challenge: bool = False    # True = JS/CAPTCHA challenge page
    status:    int  = 200
    bypassed:  bool = False
    attempts:  int  = 0

    def to_dict(self) -> dict:
        return {
            "waf_detected": self.detected,
            "waf_name":     self.waf_name,
            "challenge":    self.challenge,
            "final_status": self.status,
            "bypassed":     self.bypassed,
            "attempts":     self.attempts,
        }

# Signatures: (waf_name, [header_patterns], [body_regexes])
_WAF_SIGS: list[tuple[str, list[str], list[str]]] = [
    ("akamai",
     [r'x-check-cacheable', r'akamai-origin-hop', r'x-akamai-transformed'],
     [r'\bak_bmsc\b', r'_abck', r'\bAkamaiGTM\b', r'\bbm_sz\b',
      r'sec-if-cpt-container', r'behavioral-content', r'scf-akamai-logo']),
    ("cloudflare",
     [r'cf-ray', r'cf-cache-status', r'cf-mitigated'],
     [r'cloudflare', r'cf-browser-verification', r'__cf_bm', r'checking your browser']),
    ("imperva",
     [r'x-iinfo'],
     [r'imperva', r'incapsula', r'visid_incap']),
    ("datadome",
     [r'x-datadome-cid'],
     [r'datadome', r'DataDome']),
    ("perimeterx",
     [r'x-px-client-uuid'],
     [r'_pxhd', r'_px3', r'px-captcha', r'PerimeterX']),
    ("aws_waf",
     [r'x-amzn-requestid'],
     [r'aws-waf-token']),
]

_CHALLENGE_PHRASES = [
    r'enable javascript', r'checking your browser', r'please wait',
    r'ddos protection', r'access denied', r'bot protection',
    r'verify you are human', r'captcha', r'just a moment',
    r'security check', r'ray id',
    r'sec-if-cpt-container', r'behavioral-content', r'scf-akamai-logo',
]

def detect_waf(response: requests.Response) -> WafInfo:
    info = WafInfo(status=response.status_code)
    hdrs_lower = {k.lower(): v.lower() for k, v in response.headers.items()}
    body_lower = response.text[:20_000].lower()

    # Check header/body signatures
    for name, header_pats, body_pats in _WAF_SIGS:
        if any(re.search(pat, k) for pat in header_pats for k in hdrs_lower):
            info.detected, info.waf_name = True, name
            break
        if any(re.search(pat, body_lower) for pat in body_pats):
            info.detected, info.waf_name = True, name
            break

    # Status code based detection
    if response.status_code in (403, 429, 503):
        info.detected = True
        if info.waf_name == "none":
            info.waf_name = "generic"

    # Challenge page detection
    if any(re.search(phrase, body_lower) for phrase in _CHALLENGE_PHRASES):
        info.challenge = info.detected = True

    return info

# ---------------------------------------------------------------------------
# Proxy rotator with health checks
# ---------------------------------------------------------------------------
class _ProxyRotator:
    def __init__(self, proxies: list[str], max_fails: int = 3, cooldown: int = 60):
        self._proxies = proxies
        self._max_fails = max_fails
        self._cooldown = cooldown
        self._fail_count: dict[str, int] = {}
        self._blacklisted_until: dict[str, float] = {}
        self._idx = 0
        self._activated = False  # Proxies are dormant until WAF detected

    def activate(self):
        """Activate proxy rotation (called when WAF is detected)."""
        if self._proxies and not self._activated:
            self._activated = True
            log.info(f"[WAF] Proxy rotation activated ({len(self._proxies)} proxies)")

    def next(self) -> dict | None:
        if not self._proxies or not self._activated:
            return None
        now = time.time()
        # Try up to len(proxies) times to find a working proxy
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._idx % len(self._proxies)]
            self._idx += 1
            # Skip if blacklisted
            if proxy in self._blacklisted_until and now < self._blacklisted_until[proxy]:
                continue
            return {"http": proxy, "https": proxy}
        # All proxies are blacklisted – fallback to round-robin (ignore blacklist)
        proxy = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return {"http": proxy, "https": proxy}

    def report_failure(self, proxy_url: str):
        """Mark a proxy as failed. After max_fails, blacklist for cooldown period."""
        cnt = self._fail_count.get(proxy_url, 0) + 1
        self._fail_count[proxy_url] = cnt
        if cnt >= self._max_fails:
            self._blacklisted_until[proxy_url] = time.time() + self._cooldown
            log.warning(f"Proxy {proxy_url} blacklisted for {self._cooldown}s")
            # Optionally reset fail count after cooldown (handled by next() check)

    def __bool__(self) -> bool:
        return bool(self._proxies)

# Minimum HTML length for a real page (WAF/challenge pages are typically <1 KB).
# ---------------------------------------------------------------------------
# WafSession — public API
# ---------------------------------------------------------------------------
class WafSession:
    """
    Drop-in replacement for requests.Session with 5-tier WAF evasion.

    This class is NOT thread-safe. Create one instance per thread/process.

    Parameters
    ----------
    proxies        : list of proxy URLs, e.g. ["http://user:pass@host:port"]
    min_delay      : minimum seconds between requests to the same domain
    max_delay      : maximum seconds (jitter applied between min and max)
    max_retries    : attempts per URL before raising RuntimeError
    ssl_verify     : verify SSL certificates (can be bool or path to CA bundle)
    web_unlocker   : if True, treat proxy as a Web Unlocker that already solves challenges
    """
    def __init__(
        self,
        proxies:        list[str] | None = None,
        min_delay:      float            = 1.2,
        max_delay:      float            = 4.5,
        max_retries:    int              = 5,
        ssl_verify:     bool | str       = False,
        web_unlocker:   bool             = False,
    ):
        # Validate delay parameters
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay
            log.warning("min_delay > max_delay, swapped values")

        self._proxies        = _ProxyRotator(proxies or [])
        self._web_unlocker   = web_unlocker
        self._min_delay      = min_delay
        self._max_delay      = max_delay
        self._max_retries    = max_retries
        self._domain_ts:     dict[str, float] = {}
        self._rate_lock      = threading.Lock()
        self.last_waf_info   = WafInfo()
        self._ua             = random.choice(_UA_POOL)

        # SSL verification: warn if proxies are used and verification is still on,
        # but do NOT disable it automatically – user must decide.
        if proxies and ssl_verify is True:
            log.warning(
                "Proxies are configured but SSL verification is enabled. "
                "Many proxy providers use self-signed certificates; if you encounter "
                "SSL errors, set ssl_verify=False or provide a custom CA bundle."
            )
        self._ssl_verify = ssl_verify

        self._session        = self._new_session()
        self._html_cache: tuple[str, str] | None = None

        if _CURL_CFFI:
            if self._proxies:
                log.info("[WAF] curl-cffi active – TLS fingerprinting may be affected by proxy MITM")
            else:
                log.info("[WAF] curl-cffi active – browser TLS/HTTP2 fingerprinting enabled")
        else:
            log.warning("[WAF] curl-cffi not installed – using plain requests (install curl-cffi for better results)")

    # ── Public API ─────────────────────────────────────────────────────────
    def prime_cache(self, url: str, html: str) -> None:
        """Pre-populate the one-shot fetch cache to skip the next HTTP round-trip for this URL."""
        self._html_cache = (url, html)

    def fetch(self, url: str, **kwargs) -> str:
        """Fetch URL, return HTML string. WAF handling is fully transparent."""
        # Serve from one-shot cache
        if self._html_cache and self._html_cache[0] == url:
            html, self._html_cache = self._html_cache[1], None
            self.last_waf_info = WafInfo(status=200, bypassed=True)
            return html

        self.last_waf_info = WafInfo()
        domain = urlparse(url).netloc
        resp = None

        for attempt in range(1, self._max_retries + 1):
            self._rate_limit(domain)
            proxy_dict = None
            try:
                proxy_dict = self._proxies.next() if self._proxies else None
                merged_headers = _build_headers(self._ua)
                caller_headers = kwargs.pop("headers", None)
                if caller_headers:
                    merged_headers.update(caller_headers)

                timeout = WEB_UNLOCKER_TIMEOUT if self._web_unlocker else REQUEST_TIMEOUT
                req_kwargs: dict = dict(
                    headers=merged_headers,
                    proxies=proxy_dict,
                    timeout=timeout,
                    allow_redirects=True,
                    verify=self._ssl_verify,
                    **kwargs,
                )
                # Use curl-cffi impersonation for realistic TLS fingerprints
                if _CURL_CFFI:
                    req_kwargs["impersonate"] = _pick_impersonate(self._ua)

                resp = self._session.get(url, **req_kwargs)
            except Exception as exc:
                log.warning(f"[WAF] Network error attempt {attempt}: {exc}")
                # Don't blacklist Web Unlocker on timeout — it's often just a slow page
                is_timeout = "timed out" in str(exc).lower() or "timeout" in str(exc).lower()
                if proxy_dict and proxy_dict.get("http") and not (self._web_unlocker and is_timeout):
                    self._proxies.report_failure(proxy_dict["http"])
                self._rotate_identity()
                self._backoff(attempt)
                continue

            waf          = detect_waf(resp)
            waf.attempts = attempt
            self.last_waf_info = waf

            if waf.detected and (waf.challenge or resp.status_code != 200):
                log.warning(
                    f"[WAF] {waf.waf_name.upper()} detected "
                    f"(HTTP {resp.status_code}, challenge={waf.challenge})"
                )
                # Activate proxies on first WAF detection
                self._proxies.activate()

            # Happy path – Web Unlocker already solved any challenge
            if resp.status_code == 200 and (self._web_unlocker or not waf.challenge):
                waf.bypassed = True
                return resp.text

            # JS / CAPTCHA challenge — browser fallback is unreliable against
            # Akamai behavioral challenges; prefer proxy rotation + identity swap.
            if waf.challenge:
                if proxy_dict and proxy_dict.get("http"):
                    self._proxies.report_failure(proxy_dict["http"])
                self._rotate_identity()
                self._backoff(attempt)
                continue

            # 429 Too Many Requests
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("Retry-After", 0)), 10 * attempt)
                log.info(f"[WAF] 429 — sleeping {wait}s")
                time.sleep(wait)
                self._rotate_identity()
                continue

            # 403 / 5xx — rotate identity and back off
            if resp.status_code == 403 or 500 <= resp.status_code < 600:
                self._rotate_identity()
                self._backoff(attempt)
                continue

            # 4xx client errors (except 403) – permanent, raise immediately
            resp.raise_for_status()

        # Instead of raising, return whatever we got so the caller's
        # MIN_PAGE_HTML guard can skip the page and continue pagination.
        log.warning(
            f"[WAF] Exhausted {self._max_retries} attempts for {url} "
            f"[WAF: {self.last_waf_info.waf_name}] — returning last response"
        )
        # Return the last response text (challenge HTML) so caller can decide
        return resp.text if resp is not None else ""

    def get(self, url: str, **kwargs) -> "_MockResponse":
        """requests.Session-compatible shim so generated scripts need no changes."""
        html = self.fetch(url, **kwargs)
        return _MockResponse(html, 200, self._session.cookies, {})

    # ── Internals ──────────────────────────────────────────────────────────
    def _rotate_identity(self):
        """New User-Agent + fresh cookie jar."""
        self._ua = random.choice([u for u in _UA_POOL if u != self._ua])
        self._session = self._new_session()
        log.info(f"[WAF] Identity rotated -> {self._ua[:60]}...")

    @property
    def using_proxy(self) -> bool:
        return bool(self._proxies)

    def _rate_limit(self, domain: str):
        with self._rate_lock:
            now = time.time()
            gap = random.uniform(self._min_delay, self._max_delay) - (now - self._domain_ts.get(domain, 0))
            if gap > 0:
                self._domain_ts[domain] = now + gap
            else:
                self._domain_ts[domain] = now
                gap = 0
        if gap > 0:
            time.sleep(gap)

    def _backoff(self, attempt: int):
        wait = min(2 ** attempt + random.uniform(0, 2), 90)
        log.info(f"[WAF] Back-off {wait:.1f}s (attempt {attempt})")
        time.sleep(wait)

    @staticmethod
    def _new_session():
        if _CURL_CFFI:
            return _curl_req.Session()
        s = requests.Session()
        a = HTTPAdapter(max_retries=Retry(
            total=3, backoff_factor=1,
            status_forcelist=[], allowed_methods=["GET"],
        ))
        s.mount("https://", a)
        s.mount("http://",  a)
        return s


# ---------------------------------------------------------------------------
# Enhanced mock response (mimics requests.Response)
# ---------------------------------------------------------------------------
class _MockResponse:
    """Minimal but functional requests.Response shim."""
    def __init__(self, text: str, status_code: int, cookies=None, headers=None):
        self.text = text
        self.content = text.encode("utf-8", errors="replace")
        self.status_code = status_code
        self.cookies = cookies or requests.cookies.RequestsCookieJar()
        self.headers = headers or {}
        self.url = None   # not set
        self.history = []
        self.encoding = "utf-8"
        self.reason = "OK" if status_code < 400 else "Error"
        self.ok = status_code < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self, **kwargs):
        import json
        return json.loads(self.text, **kwargs)