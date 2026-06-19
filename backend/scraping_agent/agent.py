"""ople/Team edition)
===========================================================
Specialised for scraping team / people / staff / leadership pages.

New in v4
---------
  - Team-page URL discovery: given 
AI-Powered Web Scraper Agent  -  v4  (Pea homepage the agent finds the team page
    automatically (/about, /team, /people, /leadership, /staff, /our-team …)
  - People-focused LLM prompt: extracts name, title, bio, email, phone,
    LinkedIn, Twitter, location, department, image_url — whatever is present
  - People normaliser: standardises field names across different site layouts
  - Dual export: JSON (existing) + CSV flat file per site
  - --discover flag: auto-find team pages from a list of homepages
"""
from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import logging
import os
import queue
import random
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse, quote

import requests

from waf_bypass import WafSession, WafInfo
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("../../scraper_agent.log")],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL          = "claude-opus-4-6"
MAX_HTML_CHARS  = 40_000
MAX_PAGES       = 200
REQUEST_DELAY   = 0.8
MIN_PAGE_HTML   = 5_000  # Pages below this are WAF/challenge residue — skip without repair
OUTPUT_DIR     = Path("../../scraped_data")
SCRIPTS_DIR    = Path("../../generated_scripts")
HTML_DIR       = Path("../../html")
PROGRESS_DIR   = Path("../../progress")
DEBUG_MODE     = False  # set to True via --debug flag

# ---------------------------------------------------------------------------
# LLM Client abstraction — supports multiple providers
# ---------------------------------------------------------------------------
class LLMClient:
    """Unified LLM interface for scraping/discovery. Wraps Anthropic, OpenAI,
    Gemini, and DeepSeek behind a single `.create()` method."""

    def __init__(self, provider: str = "claude", api_key: str | None = None,
                 model: str | None = None):
        self.provider = provider
        self._model = model or MODEL
        if provider == "claude":
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""))
        elif provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))
            self._model = model or "gpt-4o-mini"
        elif provider == "deepseek":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com",
            )
            self._model = model or "deepseek-chat"
        elif provider == "gemini":
            from google import genai
            self._genai_client = genai.Client(api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""))
            self._model = model or "gemini-2.5-flash"
        elif provider == "qwen":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=api_key or os.environ.get("QWEN_API_KEY", ""),
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                )
            self._model = model or "qwen3.6-plus"
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    @property
    def model_name(self) -> str:
        return self._model

    def create(self, system: str, messages: list[dict], max_tokens: int = 8192) -> tuple[str, dict]:
        """Call the LLM. Returns (response_text, usage_dict).
        usage_dict has keys: model, input_tokens, output_tokens."""
        if self.provider == "claude":
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            usage = {
                "model": self._model,
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
            return resp.content[0].text, usage

        elif self.provider in ("openai", "deepseek", "qwen"):
            oai_messages = [{"role": "system", "content": system}] + messages
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=oai_messages,
                max_tokens=max_tokens,
                temperature=0,
            )
            usage = {
                "model": self._model,
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
            }
            return resp.choices[0].message.content, usage

        elif self.provider == "gemini":
            from google.genai import types
            resp = self._genai_client.models.generate_content(
                model=self._model,
                contents=messages[0]["content"],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=0,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            usage = {
                "model": self._model,
                "input_tokens": getattr(resp.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", 0),
            }
            return resp.text, usage


# Accumulated LLM usage entries for cost tracking (drained by scrape_task.py)
_usage_log: list[dict] = []

OUTPUT_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR.mkdir(exist_ok=True)
PROGRESS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Progress / resume helpers
# ---------------------------------------------------------------------------
def _progress_state_path(slug: str) -> Path:
    return PROGRESS_DIR / f"{slug}_state.json"

def _progress_records_path(slug: str) -> Path:
    return PROGRESS_DIR / f"{slug}_records.jsonl"

def save_progress(slug: str, state: dict) -> None:
    _progress_state_path(slug).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def load_progress(slug: str) -> dict | None:
    p = _progress_state_path(slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def append_page_records(slug: str, records: list[dict]) -> None:
    with _progress_records_path(slug).open("a", encoding="utf-8") as f:
        f.write(json.dumps(records, ensure_ascii=False) + "\n")

def load_all_records(slug: str) -> list[dict]:
    p = _progress_records_path(slug)
    if not p.exists():
        return []
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.extend(json.loads(line))
            except Exception:
                pass  # Skip corrupted lines
    return records

def clear_progress(slug: str) -> None:
    for p in [_progress_state_path(slug), _progress_records_path(slug)]:
        p.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PaginationInfo:
    strategy:           str = "none"   # none|query_param|path_segment|next_link|cursor
    param_name:         str = ""
    param_step:         int = 1
    param_start:        int = 1
    next_link_selector: str = ""
    total_pages:        int = 0
    total_items:        int = 0
    items_per_page:     int = 0
    notes:              str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "PaginationInfo":
        p = cls()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p

    def is_paginated(self) -> bool:
        return self.strategy != "none"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _html_save_path(url: str) -> Path:
    """Build a human-readable save path: html/<domain>/<path_slug>.html"""
    parsed = urlparse(url)
    domain = re.sub(r"[^\w.-]", "_", parsed.netloc)
    slug   = parsed.path.strip("/").replace("/", "__") or "index"
    slug   = re.sub(r"[^\w-]", "_", slug)
    if parsed.query:
        qs   = re.sub(r"[^\w=&]", "_", parsed.query)[:60]
        slug = f"{slug}__{qs}"
    return HTML_DIR / domain / f"{slug}.html"


def fetch_html(url: str, session: WafSession) -> tuple[str, str]:
    """Fetch HTML and return (html, final_url) — final_url may differ from
    the requested url if the server issued a redirect."""
    log.info(f"  GET {url}")
    resp = session.get(url)
    resp.raise_for_status()
    html = resp.text
    final_url = getattr(session, 'last_final_url', url) or url

    if final_url != url:
        log.info(f"  REDIRECTED {url} -> {final_url}")

    if DEBUG_MODE:
        save_path = _html_save_path(final_url)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(html, encoding="utf-8")
        log.info(f"  HTML saved -> {save_path}")
    return html, final_url


def _collapse_repeated_groups(soup, keep: int = 3) -> int:
    """
    Find ALL groups of repeated sibling elements (same tag+class signature)
    across the entire tree and collapse each group to `keep` examples.

    Runs iteratively until no more groups are found — catches nested repetition
    such as modal dialogs (each person appearing twice) inside a listing container.

    Returns total number of elements removed.
    """
    from collections import Counter

    total_removed = 0
    changed = True

    while changed:
        changed = False
        for parent in soup.find_all(True):
            direct = [c for c in parent.children if getattr(c, "name", None)]
            if len(direct) <= keep:
                continue

            sigs = Counter(
                (c.name, tuple(sorted(c.get("class") or [])))
                for c in direct
            )
            for sig, count in sigs.items():
                if count <= keep:
                    continue
                matching = [
                    c for c in direct
                    if (c.name, tuple(sorted(c.get("class") or []))) == sig
                ]
                to_remove = matching[keep:]
                if not to_remove:
                    continue
                for child in to_remove:
                    child.decompose()
                total_removed += len(to_remove)
                changed = True
                break   # direct/sigs are stale after decompose — restart
            if changed:
                break   # restart soup.find_all scan with fresh tree

    return total_removed


def _extract_embedded_json(html: str) -> str | None:
    """Extract people data from embedded JSON in framework script tags.

    Many modern sites (Nuxt, Next.js) render only the active tab in the DOM
    but embed ALL data in a <script> tag.  We extract the JSON and pass it
    alongside the HTML so the LLM can use it.
    """
    from bs4 import BeautifulSoup as _BS

    soup = _BS(html, "lxml")

    # Look for common framework data script tags
    candidates = []
    for script in soup.find_all("script"):
        sid = script.get("id", "")
        stype = script.get("type", "")
        text = script.string or ""

        # Match known framework patterns
        if sid in ("__NUXT_DATA__", "__NEXT_DATA__") and text:
            candidates.append(text)
        elif stype == "application/json" and len(text) > 500:
            candidates.append(text)

    if not candidates:
        # Try inline assignment: window.__NUXT__ = {...}
        import re as _re
        m = _re.search(r"window\.__NUXT__\s*=\s*(\{.+?\});\s*</script>", html, _re.DOTALL)
        if m:
            candidates.append(m.group(1))

    # Pick the candidate with the most people-like signals
    best, best_score = None, 0
    for raw in candidates:
        people_signals = ("name", "firstName", "lastName", "people", "team",
                          "role", "position", "title")
        score = sum(raw.count(f'"{s}"') for s in people_signals)
        if score > best_score:
            best, best_score = raw, score

    if not best or best_score < 3:
        return None

    # Budget: keep enough for the LLM to see the full data structure.
    # The DOM HTML will be reduced when embedded data is present.
    max_json = 30_000
    if len(best) > max_json:
        best = best[:max_json] + "\n... [truncated]"

    return best


def simplify_html(html: str, max_chars: int = MAX_HTML_CHARS) -> str:
    from bs4 import BeautifulSoup

    # Extract embedded JSON data before stripping scripts
    embedded_json = _extract_embedded_json(html)

    soup = BeautifulSoup(html, "lxml")

    # Remove purely decorative / non-content tags (keep <img> for photo extraction)
    for tag in soup(["script", "style", "noscript", "svg", "video", "audio"]):
        tag.decompose()

    # Simplify <img> tags: keep only src attribute to preserve photo URLs
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            img.decompose()
        else:
            # Strip all attributes except src to save tokens
            for attr in list(img.attrs.keys()):
                if attr != "src":
                    del img[attr]

    # Strip <header> — always large mega-navigation with no person data.
    # Pagination is never inside <header> so this is safe.
    for tag in soup.find_all("header"):
        tag.decompose()

    # Strip <nav> elements — navigation menus can be huge (mega-menus with
    # hundreds of links) and never contain person data.
    for tag in soup.find_all("nav"):
        tag.decompose()

    # Strip <footer> — typically site-wide links, legal, social icons.
    for tag in soup.find_all("footer"):
        tag.decompose()

    # Strip common mobile-menu / off-canvas / mega-menu containers that
    # aren't wrapped in <nav> or <header> but still bloat the HTML.
    import re as _re
    for tag in soup.find_all(
        attrs={"class": _re.compile(
            r"mobile.?menu|off-canvas|mega.?menu|site.?nav|"
            r"menu--main|main.?navigation|nav.?wrapper|"
            r"header.?nav|flyout|dropdown.?menu",
            _re.I,
        )}
    ):
        # Don't strip if it contains person-like content (articles, views-rows)
        if not tag.find(["article"]) and not tag.select(".views-row"):
            tag.decompose()

    # Strip search filter / facet sidebars — these can contain hundreds of
    # filter links (e.g. BCG: 660 facet elements) that exhaust the token budget
    # before the actual person cards are reached. Facet widgets never contain
    # person data. Target: Algolia/SearchKit sk-* components, generic facet
    # containers, and custom elements like <ps-search-filters>.
    # Strip search filter / facet sidebars — these can hold hundreds of
    # filter links (BCG: 660 × 2 copies = 584k chars of facets) that exhaust
    # the token budget before the actual person cards are reached.
    # Target the FACET CONTAINERS, not their outer wrappers (which may also
    # contain the person card section as a sibling).
    _FACET_PATTERN = _re.compile(
        r"search.?facets?.?wrapper|facet.?panel|filter.?panel|filter.?sidebar|"
        r"sk-hierarchical|sk-numeric|sk-refinement|sk-range|"
        r"refinement.?list|facet.?list",
        _re.I,
    )
    # Collect matching tags first, then decompose (safe: pre-computed list)
    for tag in list(soup.find_all(class_=_FACET_PATTERN)):
        tag.decompose()

    # NOTE: We intentionally do NOT strip display:none elements here.
    # Many team pages hide bio/contact details in collapsed child elements
    # (modals, drawers, accordions) that are revealed on card click.
    # Those hidden elements are present in the HTML and must reach the LLM.
    # _collapse_repeated_groups below handles size reduction instead.

    # Collapse ALL repeated sibling groups (person cards, modal dialogs,
    # filter facets, nav items …) down to 3 examples each.
    # Iterative so nested repetition (each person appearing twice as
    # preview + modal) is also caught.
    removed = _collapse_repeated_groups(soup, keep=3)
    if removed:
        log.info(f"  HTML: collapsed {removed} repeated elements (kept 3 each)")

    clean = soup.prettify()

    # Append embedded JSON data (Nuxt/Next.js) so the LLM can extract from
    # all tabs/sections, not just the server-rendered active tab.
    if embedded_json:
        json_section = (
            "\n\n<!-- EMBEDDED PAGE DATA (from __NUXT_DATA__ / __NEXT_DATA__) —\n"
            "     This JSON contains ALL people across ALL tabs/sections.\n"
            "     The DOM above may only show the active tab. Use this data as primary source. -->\n"
            "<script type=\"application/json\" id=\"__PAGE_DATA__\">\n"
            f"{embedded_json}\n"
            "</script>\n"
        )
        # Reduce DOM budget to make room for the JSON data
        dom_budget = max_chars - len(json_section)
        if len(clean) > dom_budget:
            log.info(f"  HTML: trimming DOM from {len(clean):,} to {dom_budget:,} chars to fit embedded JSON")
            clean = clean[:dom_budget]
        clean += json_section
        log.info(f"  HTML: appended {len(embedded_json):,} chars of embedded JSON data")

    # Rescue pagination links before truncating — they often live at the very
    # end of large pages (e.g. BCG's 1.6 MB HTML has rel="next" at byte 1,596,248).
    # Extract them from the fully-parsed soup and append as a comment so the LLM
    # always sees the pagination signal even after the main content is cut.
    pagination_hint = ""
    next_tags = soup.find_all("a", rel=lambda r: r and "next" in r)
    next_tags += soup.find_all("link", rel=lambda r: r and "next" in r)
    if next_tags:
        hrefs = [t.get("href") for t in next_tags if t.get("href")]
        if hrefs:
            pagination_hint = (
                "\n\n<!-- PAGINATION HINT (extracted from full page before truncation):\n"
                + "\n".join(f'  <a rel="next" href="{h}"/>' for h in hrefs[:3])
                + "\n-->"
            )

    orig_len = len(clean)
    if len(clean) > max_chars:
        log.warning(f"  HTML truncated {orig_len:,} -> {max_chars:,} chars")
        clean = clean[:max_chars]

    if pagination_hint:
        clean += pagination_hint
        log.info(f"  HTML: injected rel=next pagination hint")

    log.info(f"  HTML: {orig_len:,} -> {len(clean):,} chars sent to LLM")
    return clean

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an expert web-scraping engineer specialised in extracting PEOPLE and
TEAM data from company/organisation websites.

Given a URL and a cleaned HTML snippet you will:

1. IDENTIFY every person profile on the page. People entries typically appear
   as cards, list items, rows, or sections containing a name and at least one
   of: job title, bio, photo, email, phone, LinkedIn/Twitter link.

   Extract every available field for each person:
   - name          Full name (required — skip entries without a name)
   - title         Job title / role / position
   - department    Team, division, or practice area if shown
   - bio           Biography or description text (full, not truncated).
                   IMPORTANT — a bio is a SENTENCE or PARAGRAPH about the person.
                   Short CTA / button labels like "Meet John", "View Profile",
                   "Read more", "Learn more", "About Jane" are NOT bios — set
                   bio to null if the only text found is a short label (< 80 chars)
                   that does not describe the person.
   - email         Email address
   - phone         Phone number
   - linkedin_url  LinkedIn profile URL
   - twitter_url   Twitter / X profile URL
   - other_url     Any other personal/profile URL (personal site, GitHub, etc.)
   - image_url     Absolute URL of the person's photo
   - location      Office, city, or country if shown
   - profile_url   Absolute URL of the person's individual detail/profile page.
                   IMPORTANT — decide based on the site's interaction pattern:

                   Pattern A — MODAL / DRAWER / ACCORDION (click opens overlay on same page):
                     • Set profile_url to null for EVERY person on the page.
                     • Set "has_profile_pages": false in the JSON metadata.
                     • Extract whatever detail is present in the modal/drawer.
                     • If a person's modal is empty, their profile_url is still
                       null — do NOT fall back to a profile URL for empty modals.
                     • Detection signals: cards with data-toggle="modal",
                       data-target="#id", href="#id", or aria-controls pointing
                       to an overlay; or hidden sibling divs/sections that expand
                       on click (class: modal, drawer, popup, overlay, collapse).

                   Pattern B — SEPARATE PAGE (click navigates to a new URL):
                     • Set profile_url to the destination URL and
                       "has_profile_pages": true only when the card has NO bio/detail
                       and following the link is the only way to get it.

                   NEVER mix patterns: if the site uses modals for ANY person,
                   profile_url is null and has_profile_pages is false for ALL
                   people, even if cards also have an <a href="/people/name">.
                   Detect profile links via: <a> wrapping the card/photo, <a> on
                   the name, or "Read more" / "View profile" / "Learn more" anchors.
                   Resolve relative hrefs to absolute using the page URL.

                   WRAPPING-A PATTERN (common on search/listing pages like BCG):
                   The ENTIRE card is wrapped in a single <a> element:
                     <a class="result-link" href="/people/john-smith">
                       <div class="result-header"><h2>John Smith</h2></div>
                     </a>
                   In this case:
                   • CARD SELECTOR: soup.select("a.result-link") — the <a> IS the card
                   • profile_url: urljoin(url, card.get("href")) — href is on the <a> itself
                   • name: card.select_one(".result-header h2") or card.select_one("h2")
                     DO NOT use .get_text() on the card itself — it concatenates all children
                   • DO NOT search for a nested <a> inside the card — there is none
                   BCG concrete example:
                     cards = soup.select('a.result-link')
                     for card in cards:
                         name_el = card.select_one(".result-header h2") or card.select_one("h2")
                         if not name_el: continue
                         name = name_el.get_text(strip=True)
                         profile_url = urljoin(url, card.get("href"))

                   CRITICAL — a profile_url must be about THIS specific person:
                   • The URL path typically contains part of the person's name
                     (e.g. /people/john-smith, /team/jane-doe)
                   • It lives under paths like /people/, /team/, /staff/,
                     /our-people/, /leadership/, /about/team/, /about/people/,
                     /consultants/, /experts/, etc.
                   • NEVER set profile_url to industry, service, capability,
                     insight, or topic pages (paths containing /industries/,
                     /services/, /insights/, /capabilities/, /sectors/, /work/,
                     /news/, /blog/, etc.) — those are NOT person profiles.
   - extra         Dict of any other interesting fields not listed above

   Rules:
   - Use null for missing fields, never omit the key.
   - Resolve relative URLs to absolute using the page URL.
   - If a card links to a detail page, capture the URL in profile_url and set
     has_profile_pages: true — do NOT follow it, the agent handles that.
   - Do not fabricate or infer data; only extract what is explicitly present.
   - NEVER use .get_text() on a whole card container to extract the name —
     this concatenates name + location + CTA text (e.g. "John SmithLondonMeet John").
     Always target the specific element that contains only the name
     (e.g. the <h2>, <h3>, or dedicated name <span>/<div> inside the card).
   - Same for title: target only the element with the job title text. Do NOT
     use .get_text() on a parent that also contains the name or location.
   - Bio selector regex must be NARROW — match classes like "bio", "description",
     "summary", "field--body", "field--bio". Do NOT match overly generic words
     like "content" or "text" — those catch buttons, navigation, and CTA labels.
   - Ignore navigation menus, filter widgets, and sidebar links — only extract
     records from the main people/team listing area of the page.
   - TESTIMONIAL / QUOTE CAROUSELS are marketing content, NOT people directories.
     Skip any container whose class or data attribute contains "testimonial",
     "quote", "swiper-testimonial", or has data-quote-carousel.  Even when
     these sliders show a person's name, photo, title and a "View Profile" link,
     they are promotional samples — not the authoritative staff listing.
     Detection: soup.select(".swiper-testimonial, [data-quote-carousel]") and
     similar — decompose() those before looking for person cards.

2. HIDDEN / CLICK-TO-EXPAND DETAIL PANELS
   Many team pages show only the name + photo in the visible card, and hide
   the bio, email, phone, and other details in an element that appears when
   the user clicks the card or photo. This hidden content IS present in the
   HTML — BeautifulSoup can read it directly without any JavaScript.

   Common patterns and how to handle them:

   a) Hidden child element inside the card:
        <div class="team-card">
          <img src="photo.jpg"><h3>Jane Smith</h3><p>Partner</p>
          <div class="bio hidden">Jane joined in …</div>  ← grab this
        </div>
      → Search ALL descendants of the card, not just visible ones:
          bio = card.find(class_=re.compile(r"bio|detail|desc|info|content|
                                              modal|drawer|popup|overlay|
                                              expand|more|full", re.I))

   b) data-* attributes on the card element itself:
        <div class="person" data-bio="Jane joined in …" data-email="j@co.com">
      → card.get("data-bio"), card.get("data-description"),
          card.get("data-content"), card.get("data-email"), etc.

   c) Page-level modal/overlay containers linked to a card by ID or index:
        <div class="card" data-target="#bio-1"><h3>Jane</h3></div>
        …
        <div id="bio-1" class="modal">Jane joined in …</div>
      → Resolve the data-target / href="#id" / data-id attribute from the card,
          then soup.find(id=target_id) to get the matching modal.
      → Alternatively match by position: cards[i] ↔ modals[i].

   Always check ALL THREE patterns before returning an empty bio.

   TABBED / SECTIONED TEAM PAGES & EMBEDDED JSON DATA
   Some team pages split people across client-side tabs (e.g. "Partners",
   "Senior Advisers", "Senior Team").  The server-rendered HTML may only
   contain the ACTIVE tab's people — the other tabs are populated by JS.

   If the HTML snippet includes an EMBEDDED PAGE DATA section at the bottom
   (inside a <script> tag), it contains embedded JSON from the page's JS
   framework.  This JSON has ALL people across ALL tabs.  When you see this:

   IMPORTANT — your scrape_page function must look for the embedded data
   in the REAL page HTML using these IDs (try each):
     soup.find("script", id="__NUXT_DATA__")   ← Nuxt 3
     soup.find("script", id="__NEXT_DATA__")   ← Next.js
   Then json.loads() its text content.

   The embedded data may use a flat indexed-array format (Nuxt 3):
     [["ShallowReactive",1],{"data":2,...},...]
   where dict values are indices into the top-level array.  To resolve:
     def resolve(data, idx, depth=0):
         if depth > 15 or not isinstance(idx, int) or idx >= len(data):
             return idx
         val = data[idx]
         if isinstance(val, (str, int, float, bool)) or val is None:
             return val
         if isinstance(val, list):
             return [resolve(data, i, depth+1) for i in val]
         if isinstance(val, dict):
             return {k: resolve(data, v, depth+1) for k, v in val.items()}
         return val

   Look for objects with "people" or "team" keys — those are tab groups.
   Each group has a "title" and a "people" array of person indices.
   Resolve each person to get "name", "role", "image", "link", etc.

   Extract people from ALL groups/tabs — not just the first one.

   If no embedded JSON is found, fall back to DOM parsing:
   - Use soup.find_all() to select ALL person cards across the ENTIRE page
   - Do NOT scope selectors to a single tab container
   - Do NOT filter by "active", "show", "is-active", or "display:none"

3. Detect pagination using ONE strategy:
   - "none"         -- single page / all people on one page
   - "query_param"  -- ?page=2, ?p=3, ?start=20, ?offset=40
   - "path_segment" -- /team/page/2 or /team/start/24
   - "next_link"    -- <a rel="next"> or visible "Next" / "Load more" anchor
   - "cursor"       -- ?cursor=<token> from page body

   IMPORTANT: The HTML may have been truncated to save tokens. A comment block at
   the very end like <!-- PAGINATION HINT ... <a rel="next" href="..."/> ... -->
   contains pagination links rescued from the full page. If you see it, use the
   href to determine the strategy and param_name/param_step/param_start.

   For "query_param": param_start is the page value of the FIRST paginated URL
   (the one that matches the already-fetched base page). Check whether pagination
   is 0-based (?page=0 is first) or 1-based (?page=1 is first) by inspecting
   the actual links or pagination controls in the HTML.
   Examples:
     /team?page=0 → /team?page=1 → /team?page=2: param_name="page", param_step=1, param_start=0
     /team?page=1 → /team?page=2 → /team?page=3: param_name="page", param_step=1, param_start=1
     /team?start=0 → /team?start=20 → /team?start=40: param_name="start", param_step=20, param_start=0

   For "path_segment": set param_name to the path segment label (e.g. "page",
   "start", "offset"). param_step is the increment per page, param_start is the
   value for the SECOND page (since the first page is the base URL without the
   segment).
   Examples:
     /team → /team/page/2 → /team/page/3: param_name="page", param_step=1, param_start=2
     /team → /team/start/24 → /team/start/48: param_name="start", param_step=24, param_start=24

4. Write a complete, self-contained Python scraping function:
   - Named exactly: scrape_page(url: str, session) -> list[dict]
   - Uses BeautifulSoup(session.get(url).text, "lxml") for parsing.
   - Do NOT import requests at module level; use the session parameter.
   - Extracts people from ONE page only (no internal loops).
   - Returns a list of person dicts following the schema above.
   - Returns [] on empty/not-found pages.
   - Handles missing elements gracefully with try/except and .get().
   - For hidden-detail patterns (see point 2): iterate card elements and for
     each card check hidden child elements, data-* attributes, AND linked
     page-level modals to assemble the complete person record.
   - For profile-link patterns: extract the href from the card's anchor
     (wrapping <a>, image <a>, name <a>, or "View profile" link), resolve it
     to an absolute URL, store it in profile_url, and ensure
     has_profile_pages is true in the JSON.

5. If strategy is "next_link" or "cursor", also write:
   get_next_url(html: str, current_url: str) -> str | None

Reply EXACTLY in this format — no extra prose:

```python
<scraping code here>
```
```json
{
  "fields": ["name", "title", ...],
  "has_profile_pages": true,
  "pagination": {
    "strategy": "none",
    "param_name": "",
    "param_step": 1,
    "param_start": 1,
    "next_link_selector": "",
    "total_pages": 0,
    "total_items": 0,
    "items_per_page": 0,
    "notes": ""
  }
}
```
"""

REPAIR_PROMPT = """\
The previously generated scraping script returned 0 person records on this page,
but the page appears to contain team/people data.

Examine the HTML snapshot carefully. Common reasons for failure:

1. Wrong CSS selector — the card container class/tag changed. Inspect the
   actual HTML structure and update the selector.

2. Hidden-detail pattern — name/title are in the visible card but bio/email
   are in a HIDDEN child element (class contains "bio", "detail", "modal",
   "popup", "drawer", "hidden", "collapse", etc.) or in data-* attributes
   (data-bio, data-description, data-content, data-email …) on the card
   element. BeautifulSoup reads hidden elements — use find() on all
   descendants, not just visible ones.

3. Page-level modals — detail panels live outside the card (e.g. at the bottom
   of the page), linked by data-target="#id", data-person-id, or card index.
   Match cards[i] to modals[i] or resolve the id reference.

4. Overly broad selectors — regex patterns like r"content|text" match CTA
   buttons and navigation instead of actual bio text. Use narrow class
   matches: "bio", "description", "summary", "field--body", "field--bio".

5. CTA labels mistaken for bios — "Meet John", "View Profile", "Read more"
   are button labels, not bios. If the only text found is < 80 chars and
   does not describe the person, set bio to null.

6. Concatenated text in title/name — using .get_text() on a parent element
   that wraps name + location + CTA produces garbage like
   "John SmithLondonMeet John". Target the specific child element instead.

Rewrite scrape_page (and get_next_url if relevant) to correctly extract people.
Use the same reply format as before.
"""

PROFILE_PAGE_PROMPT = """\
You are an expert web-scraping engineer specialised in extracting PEOPLE data.

This is an INDIVIDUAL PROFILE PAGE for a single person.
Extract every available field and return a single-element list.

Fields to extract (use null for missing):
  name, title, department, bio, email, phone,
  linkedin_url, twitter_url, other_url, image_url, location, extra

━━━ EXTRACTION GUIDANCE ━━━

name
  The person's full name is almost always in the only <h1> on the page.
  BCG: h1.PersonHeader__name__non-local inside div.PersonHeader__name

title / department
  Typically in a <h2>, <h3>, or <p> immediately following the <h1>, or
  inside a dedicated header/intro section. May be split: job title on one
  line, department/practice on another — capture both.
  BCG: span.PersonHeader__name__primaryTitle (e.g. "Senior Advisor")

location
  Often a <p> or <span> just below the title (city, country, office).
  May be labelled with "Location", "Office", or "Based in".
  BCG: a.PersonHeader__officeTitle span (e.g. "Detroit")

bio
  Look for a rich-text / content container. Try selectors in order with
  sequential or-chained select_one calls — NEVER combine them into a single
  comma-separated string like select_one("A, B, C") because that returns the
  first DOM element matching ANY selector regardless of which selector you
  listed first. On Drupal sites the navigation has class field--name-body and
  appears before the actual bio, so a combined selector would return the nav.

  Correct pattern:
    bio_container = (
        soup.select_one(".field--name-field-body .field__item") or
        soup.select_one(".field--name-field-bio .field__item") or
        soup.select_one("div.rte") or
        soup.select_one("div.rich-text") or
        soup.select_one("div.bio")
    )
    # NOTE: Never include .field--name-body — it matches Drupal navigation
    # blocks that contain industry lists, not the person's biography.

  Collect ALL <p> tags inside and join with "\\n\\n" to preserve paragraphs.
  Strip HTML tags; use .get_text(separator=" ", strip=True) on each <p>.

expertise (consulting / professional-services sites)
  Find the expertise section in this priority order:
    exp_section = (
        soup.select_one(".PersonExpertise") or        # BCG
        soup.select_one(".profile-expertise") or
        soup.select_one("[class*='expertise']")
    )

  BCG pattern — flat <ul><li><a class="tag"> list, split by URL path:
    industries:   <a> whose href contains "/industries/"
    capabilities: <a> whose href contains "/capabilities/"

    ind_tags = [a.get_text(strip=True) for a in exp_section.select("a.tag")
                if "/industries/" in (a.get("href") or "")]
    cap_tags = [a.get_text(strip=True) for a in exp_section.select("a.tag")
                if "/capabilities/" in (a.get("href") or "")]
    # anything not matching either bucket goes into capabilities
    other_tags = [a.get_text(strip=True) for a in exp_section.select("a.tag")
                  if "/industries/" not in (a.get("href") or "")
                  and "/capabilities/" not in (a.get("href") or "")]
    cap_tags += other_tags
    if ind_tags:
        extra["expertise_industries"]   = ind_tags
    if cap_tags:
        extra["expertise_capabilities"] = cap_tags

  Generic fallback (other sites with named sub-sections):
    ind_sub  = exp_section.select_one("[class*='industr'], [class*='sector']") if exp_section else None
    cap_sub  = exp_section.select_one("[class*='capabilit'], [class*='function']") if exp_section else None
    If sub-sections found, extract <a>/<li> labels from each and store as
    extra["expertise_industries"] / extra["expertise_capabilities"].
    If no sub-sections, store all labels as extra["expertise_capabilities"].

  Always skip <a>/<li> whose text is empty, "Read more", or "Read less".

education
  Find the education section in this priority order:
    edu_section = (
        soup.select_one(".PersonEducation") or        # BCG
        soup.select_one(".profile-education") or
        soup.select_one("[class*='education']") or
        soup.find(lambda tag: tag.name in ("h2","h3","h4") and
                  "education" in tag.get_text(strip=True).lower())
    )

  BCG pattern — each <li> inside .List-items-item is one raw qualification string:
    "MBA, finance and sales and marketing, Northwestern University, Kellogg School of Management"
  Store each as: { "degree": null, "institution": null, "year": null, "raw": "<full text>" }

  Generic pattern — same: iterate li/div items, store raw text as "raw" field.

  Full pattern:
    education = []
    if edu_section:
        for item in edu_section.select("li"):
            text = item.get_text(" ", strip=True)
            if text:
                education.append({"degree": None, "institution": None, "year": None, "raw": text})
    if education:
        extra["education"] = education

image_url  — extraction priority order:
  1. Locate the main portrait/photo <img> (look for class names containing
     "photo", "portrait", "headshot", "avatar", "profile", "hero", "picture").
  2. If the <img> has a srcset attribute, extract the URL of the largest
     size (last entry after splitting by comma):
       parts = [p.strip() for p in img["srcset"].split(",") if p.strip()]
       image_url = parts[-1].split()[0]   # last srcset entry, strip width
  3. Fallback to src attribute.
  4. Lazy-loaded images: check data-src or data-srcset when src is a
     blank/placeholder (e.g. "data:image/gif;base64,...").
  Always resolve to an absolute URL.

email / phone
  Check: <a href="mailto:..."> links, <a href="tel:..."> links, and plain
  text matching email or phone patterns in the contact/header section.

linkedin_url / twitter_url
  Look for <a> whose href contains "linkedin.com/in/" (personal profile only —
  do NOT use company pages like linkedin.com/company/...) or
  "twitter.com/" / "x.com/". Also check SVG icon links in social sections.

other_url
  Any other personal URL present (GitHub, personal site, company profile).

━━━ RULES ━━━
  - Use null for missing fields, never omit the key.
  - Resolve ALL relative URLs to absolute using urljoin(url, href).
  - Do not fabricate data; only extract what is explicitly present.
  - Handle missing elements with try/except and .get().

Write a function:
  scrape_page(url: str, session) -> list[dict]

Reply EXACTLY in this format — no extra prose:

```python
<scraping code here>
```
```json
{"fields": ["name", "title", ...], "has_profile_pages": false,
 "pagination": {"strategy": "none", "param_name": "", "param_step": 1,
                "param_start": 1, "next_link_selector": "",
                "total_pages": 0, "total_items": 0, "items_per_page": 0,
                "notes": "individual profile page"}}
```
"""

PROFILE_FUNCTION_PROMPT = """\
You are extending an existing web-scraping script for a team/people website.

The script already contains scrape_page() for the listing page.
Now write ONE additional function to extract data from an INDIVIDUAL PROFILE PAGE:

  scrape_profile_page(url: str, session) -> dict

Rules:
  - Returns a SINGLE person dict (not a list).
  - Same field schema: name, title, department, bio, email, phone,
    linkedin_url, twitter_url, other_url, image_url, location, extra
  - Use null for missing fields, never omit the key.
  - Uses BeautifulSoup(session.get(url).text, "lxml") for parsing.
  - Resolves relative URLs to absolute with urljoin(url, href).
  - Handles missing elements gracefully with try/except and .get().

Extraction guidance (same patterns as PROFILE_PAGE_PROMPT):
  name       → first <h1> on the page
  title      → <h2>/<h3>/<p> immediately after <h1>
  location   → <p>/<span> below the title (city/country/office)
  bio        → use sequential or-chained select_one calls (NOT a comma
               selector string — document order determines which wins):
                 soup.select_one(".field--name-field-body .field__item") or
                 soup.select_one(".field--name-field-bio .field__item") or
                 soup.select_one("div.rte") or soup.select_one("div.rich-text")
               NEVER include .field--name-body — matches Drupal nav blocks;
               join all <p> tags with "\\n\\n"
  image_url  → main portrait <img>; prefer srcset last entry (largest);
               fall back to src; check data-src for lazy-loaded images
  email      → <a href="mailto:...">
  phone      → <a href="tel:...">
  linkedin_url / twitter_url → <a> whose href contains "linkedin.com/in/"
               (personal profile only — skip linkedin.com/company/... pages) or
               "twitter.com/" / "x.com/"
  extra      → expertise: exp_section = soup.select_one(".PersonExpertise") or
                 soup.select_one(".profile-expertise") or soup.select_one("[class*='expertise']")
               BCG: split a.tag links by href — "/industries/" → expertise_industries,
               "/capabilities/" → expertise_capabilities (remaining go into capabilities).
               Other sites: look for [class*='industr'] / [class*='capabilit'] sub-sections;
               if absent, store all labels as expertise_capabilities.
             → education: edu_section = soup.select_one(".PersonEducation") or
                 soup.select_one(".profile-education") or soup.select_one("[class*='education']")
               Iterate edu_section.select("li"), store each as:
               {"degree": None, "institution": None, "year": None, "raw": <text>}
               Store as extra["education"] = [list]. Omit key if list is empty.

Reply with ONLY the function — no imports, no JSON block, no extra prose:

```python
def scrape_profile_page(url: str, session) -> dict:
    ...
```
"""

DISCOVER_PROMPT = """\
You are given the HTML of a website homepage or navigation area.
Your job is to find the URL of the TEAM / PEOPLE / STAFF / LEADERSHIP page.

A valid team page is one that lists MULTIPLE people who work at the organisation,
typically showing their names, titles/roles, and often photos or short bios.
Examples of good matches:
  "Our Team", "Meet the Team", "Our People", "Leadership", "Staff",
  "About Us > Team", "Who We Are", "Partners", "Experts", "Faculty", etc.

IMPORTANT — the following are NOT team pages and must be excluded:
  - Individual stories or spotlights ("Meet John", "Talk to our experts", "Our Story")
  - Sales or contact pages ("Talk to Sales", "Book a Demo", "Contact Us")
  - Customer testimonials or case studies
  - Blog posts or articles about specific people
  - Career/jobs pages
A team page gives a structured OVERVIEW of MULTIPLE employees, not a narrative
about one or two individuals.

Return ONLY a JSON object — no prose:
{
  "found": true,
  "url": "<absolute URL of the team page>",
  "link_text": "<text of the anchor>",
  "confidence": "high|medium|low"
}

If no such page is found return:
{"found": false, "url": null, "link_text": null, "confidence": null}
"""


def call_llm(client: LLMClient, url: str, html: str,
             repair: bool = False, profile_page: bool = False,
             profile_function: bool = False) -> str:
    if repair:
        system = REPAIR_PROMPT
    elif profile_function:
        system = PROFILE_FUNCTION_PROMPT
    elif profile_page:
        system = PROFILE_PAGE_PROMPT
    else:
        system = SYSTEM_PROMPT
    label = "[REPAIR] " if repair else ("[PROFILE-FN] " if profile_function else ("[PROFILE] " if profile_page else ""))
    log.info(f"  {label}Calling LLM ({client.provider}/{client.model_name}) ...")
    text, usage = client.create(
        system=system,
        messages=[{"role": "user", "content": f"URL: {url}\n\nHTML SNIPPET:\n{html}"}],
        max_tokens=8192,
    )
    _usage_log.append({**usage, "step": "scraping"})
    return text


# ---------------------------------------------------------------------------
# Heuristic team-page discovery (no LLM tokens consumed)
# ---------------------------------------------------------------------------

# (substring, score) checked against lowercased link text — first match wins
_TEXT_PATTERNS: list[tuple[str, int]] = [
    ("our team",         5),
    ("meet the team",    5),
    ("meet our team",    5),
    ("our people",       5),
    ("the team",         4),
    ("leadership team",  4),
    ("management team",  4),
    ("team members",     4),
    ("team",             3),
    ("people",           3),
    ("our staff",        4),
    ("staff",            3),
    ("leadership",       3),
    ("management",       3),
    ("executives",       3),
    ("board",            2),
    ("faculty",          3),
    ("experts",          3),
    ("partners",         2),
    ("advisors",         3),
    ("who we are",       3),
    ("about us",         1),
]

# (substring, score) checked against lowercased URL path — first match wins
_PATH_PATTERNS: list[tuple[str, int]] = [
    ("/our-team",         4),
    ("/our-people",       4),
    ("/meet-the-team",    4),
    ("/the-team",         4),
    ("/team",             3),
    ("/people",           3),
    ("/staff",            3),
    ("/leadership",       3),
    ("/management",       3),
    ("/management-team",  3),
    ("/executives",       3),
    ("/exec-team",        3),
    ("/faculty",          3),
    ("/experts",          3),
    ("/advisors",         3),
    ("/who-we-are",       3),
    ("/about/team",       4),
    ("/about/people",     4),
    ("/about/leadership", 4),
    ("/about/staff",      4),
    ("/about/management", 3),
]

# Links whose path contains any of these strings are almost certainly not team pages
_PATH_BLOCKLIST: frozenset[str] = frozenset({
    "careers", "jobs", "news", "blog", "press", "contact", "login",
    "signup", "register", "privacy", "terms", "sitemap", "faq",
    "search", "events", "resources", "services", "product", "pricing",
    "story", "stories", "testimonial", "case-study", "case-studies",
    "demo", "book-a-demo", "talk-to", "meet-with", "spotlight",
    # Content/capability pages that may contain consultant profiles but are NOT team listings
    "capabilities", "capability", "insights", "insight", "industries",
    "industry", "solutions", "solution", "sectors", "sector",
    "work", "case-studies", "case-study",
    # Generic "about the company" narrative pages — never a people listing
    "who-we-are", "our-story", "our-mission", "our-values", "about-us",
    "our-purpose", "our-history", "our-culture",
})

# Link text patterns that indicate story/sales pages, not team pages
_TEXT_BLOCKLIST: frozenset[str] = frozenset({
    "talk to sales", "book a demo", "contact us", "our story",
    "customer stories", "meet john", "talk to an expert",
    "schedule a call", "get in touch", "request a demo",
})

_MIN_HEURISTIC_SCORE = 3   # anything below this is too ambiguous
MAX_RETRIES = 3
BASE_DELAY = 2  # seconds
def fetch_via_scrapedo(url: str) -> str | None:
    """Fetch URL via Scrape.do with exponential backoff retries."""
    encoded_target = quote(url, safe="")
    SCRAPEDO_API_KEY = os.environ.get("SCRAPEDO_API_KEY")
    if not SCRAPEDO_API_KEY:
        raise EnvironmentError("SCRAPEDO_API_KEY environment variable is not set.")
    api_url = (
        f"https://api.scrape.do/"
        f"?url={encoded_target}"
        f"&token={SCRAPEDO_API_KEY}"
        f"&super=true"
        f"&render=true"
    )

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()

            # Guard against error pages returned with HTTP 200
            if len(response.text) < 500:
                raise ValueError(f"Response suspiciously short ({len(response.text)} chars)")

            return response.text

        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt <= MAX_RETRIES:
                sleep_time = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                log.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt, MAX_RETRIES + 1, e, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                log.error("All %d attempts failed for %s: %s", MAX_RETRIES + 1, url, e)
                return None


def _score_anchor(a, base_url: str) -> tuple[int, str]:
    """Score a single <a> tag as a potential team-page link. Returns (score, abs_url)."""
    href = (a.get("href") or "").strip()
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return 0, ""

    abs_url    = urljoin(base_url, href)
    parsed     = urlparse(abs_url)
    path_lower = parsed.path.lower()
    text_lower = a.get_text(separator=" ", strip=True).lower()

    # Same domain only (strip www. to handle redirects like leshabank.com → www.leshabank.com)
    base_netloc = urlparse(base_url).netloc.removeprefix("www.")
    link_netloc = parsed.netloc.removeprefix("www.")
    if link_netloc != base_netloc:
        return 0, ""

    # Skip obvious non-team paths — match on full path segments so that compound
    # slugs like "search-people" or "our-insights" are not accidentally blocked
    # by a term ("search", "insights") that appears only as a substring.
    path_segments = set(path_lower.strip("/").split("/"))
    if path_segments & _PATH_BLOCKLIST:
        return 0, ""

    # Skip story/sales/contact link text
    if any(bl in text_lower for bl in _TEXT_BLOCKLIST):
        return 0, ""

    score = 0

    for pattern, pts in _TEXT_PATTERNS:
        if pattern in text_lower:
            score += pts
            break   # only best text match

    for pattern, pts in _PATH_PATTERNS:
        if path_lower.startswith(pattern) or f"{pattern}/" in path_lower:
            score += pts
            break   # only best path match

    # DOM context bonus
    for parent in a.parents:
        tag = getattr(parent, "name", None)
        if tag in ("nav", "header"):
            score += 2
            break
        if tag == "footer":
            score += 1
            break
        if tag == "body":
            break

    return score, abs_url


def discover_team_url_local(base_url: str, html: str) -> str | None:
    """
    Scan all anchors in the page and return the highest-scored team/people URL.
    Returns None if no candidate reaches _MIN_HEURISTIC_SCORE.
    No LLM involved — runs entirely locally.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    best_score, best_url = 0, ""
    for a in soup.find_all("a", href=True):
        score, url = _score_anchor(a, base_url)
        if score > best_score:
            best_score, best_url = score, url

    if best_score >= _MIN_HEURISTIC_SCORE and best_url:
        log.info(f"  [DISCOVER] Heuristic match: {best_url!r} (score={best_score})")
        return best_url

    log.info(f"  [DISCOVER] Heuristic: no confident match (best score={best_score})")
    return None


def discover_team_url(client: LLMClient, base_url: str,
                      session: WafSession) -> str | None:
    """
    Find the team/people page URL from a homepage.

    Tier 1 — local heuristic: score every anchor by text, path and DOM context.
              Free, instant, no API call.
    Tier 2 — LLM fallback: only fires when heuristic finds nothing.
              Reuses the already-fetched HTML so no extra HTTP round-trip.

    Returns absolute URL or None.
    """
    log.info(f"  [DISCOVER] Looking for team page on {base_url}")
    try:
        html, final_url = fetch_html(base_url, session)
    except Exception as exc:
        log.warning(f"  [DISCOVER] Could not fetch {base_url}: {exc}")
        return None

    # If we were redirected to a different domain, use the final URL as base
    if final_url != base_url:
        log.info(f"  [DISCOVER] Redirected to {final_url}, using as base")
        base_url = final_url

    # Tier 1 — heuristic (no LLM)
    url = discover_team_url_local(base_url, html)
    if url:
        # Validate: fetch the candidate and check if it links to a more specific
        # people/leadership page. Sites with JS-rendered navs often surface a
        # generic "about" page from the homepage HTML; the real team listing is
        # one level deeper. If the candidate page itself contains a higher-scoring
        # people link, use that instead.
        try:
            candidate_html, _ = fetch_html(url, session)
            deeper = discover_team_url_local(url, candidate_html)
            if deeper and deeper != url:
                log.info(f"  [DISCOVER] Refined heuristic: {url!r} -> {deeper!r}")
                url = deeper
        except Exception:
            pass  # if candidate fetch fails, proceed with original heuristic result
        return url

    # Tier 2 — LLM fallback (reuses already-fetched html, no re-fetch)
    log.info(f"  [DISCOVER] Falling back to LLM ({client.provider}/{client.model_name}) ...")
    clean = simplify_html(html, max_chars=20_000)
    raw_text, usage = client.create(
        system=DISCOVER_PROMPT,
        messages=[{"role": "user", "content": f"Base URL: {base_url}\n\nHTML:\n{clean}"}],
        max_tokens=512,
    )
    _usage_log.append({**usage, "step": "team_discovery"})
    raw = raw_text.strip()
    raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(f"  [DISCOVER] Could not parse LLM response: {raw[:200]}")
        return None

    if result.get("found") and result.get("url"):
        url = result["url"]
        if not url.startswith("http"):
            url = urljoin(base_url, url)
        log.info(f"  [DISCOVER] LLM found: {url!r} (confidence={result.get('confidence')}, text={result.get('link_text')!r})")
        return url

    log.info("  [DISCOVER] No team page found")
    return None


def discover_category_urls(html: str, base_url: str) -> list[str]:
    """
    Detect if a people/team page is a category index (shows sub-section links
    instead of actual person listings).

    Looks for anchor links that are direct sub-paths of base_url, share the same
    path depth, and are not in the non-person path blocklist.  Returns the list
    of category URLs when ≥2 are found, otherwise returns [].

    Examples:
      base_url = https://www.teneo.com/people
      finds /people/financial-advisory, /people/management-consulting, … → returns all 5
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    parsed_base = urlparse(base_url)
    base_path   = parsed_base.path.rstrip("/")

    candidates: dict[str, str] = {}  # abs_url → sub-segment

    for a in soup.find_all("a", href=True):
        abs_url = urljoin(base_url, a["href"])
        parsed  = urlparse(abs_url)

        # Same scheme + domain only (strip www. to tolerate redirects)
        if parsed.netloc.removeprefix("www.") != parsed_base.netloc.removeprefix("www."):
            continue

        link_path = parsed.path.rstrip("/")

        # Must be exactly one level deeper than base_path
        if not link_path.startswith(base_path + "/"):
            continue
        sub = link_path[len(base_path):].strip("/")
        if "/" in sub or not sub:
            continue  # skip deeper or identical paths

        # Skip non-person path segments — exact segment match only, not substring
        if sub.lower() in _PATH_BLOCKLIST:
            continue

        candidates[abs_url] = sub

    if len(candidates) < 2:
        return []

    log.info(
        f"  [CATEGORY] Category index detected — {len(candidates)} sub-sections: "
        + ", ".join(candidates.values())
    )
    return list(candidates.keys())


def parse_llm_response(text: str) -> tuple[str, dict]:
    py_m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    js_m = re.search(r"```json\s*(.*?)```",   text, re.DOTALL)
    code = py_m.group(1).strip() if py_m else ""
    meta: dict = {}
    if js_m:
        try:
            meta = json.loads(js_m.group(1).strip())
        except json.JSONDecodeError:
            pass
    if not code:
        raise ValueError("LLM returned no Python code block.")
    return code, meta


# ---------------------------------------------------------------------------
# People normaliser
# ---------------------------------------------------------------------------

# Canonical field set for every person record
PERSON_FIELDS = [
    "name", "title", "department", "bio",
    "email", "phone", "linkedin_url", "twitter_url",
    "other_url", "image_url", "location", "profile_url", "extra",
]

# Common aliases used by LLM-generated scripts across different sites
_FIELD_ALIASES: dict[str, str] = {
    # name
    "full_name": "name", "person_name": "name", "member_name": "name",
    "employee_name": "name", "staff_name": "name",
    # title
    "job_title": "title", "role": "title", "position": "title",
    "job_role": "title", "designation": "title", "job_position": "title",
    # department
    "team": "department", "division": "department", "group": "department",
    "practice": "department", "area": "department", "unit": "department",
    # bio
    "description": "bio", "about": "bio", "summary": "bio",
    "biography": "bio", "profile_text": "bio", "overview": "bio",
    "excerpt": "bio", "text": "bio",
    # contact
    "email_address": "email", "mail": "email",
    "telephone": "phone", "tel": "phone", "mobile": "phone",
    "phone_number": "phone", "contact_number": "phone",
    # social
    "linkedin": "linkedin_url", "linkedin_profile": "linkedin_url",
    "twitter": "twitter_url", "x_url": "twitter_url",
    "website": "other_url", "personal_website": "other_url",
    "github": "other_url", "url": "other_url",
    # image
    "photo": "image_url", "avatar": "image_url", "picture": "image_url",
    "headshot": "image_url", "img": "image_url", "photo_url": "image_url",
    # location
    "office": "location", "city": "location", "country": "location",
    "region": "location",
    # profile page link
    "profile_link": "profile_url", "page_url": "profile_url",
    "detail_url": "profile_url", "link": "profile_url",
}


def normalise_person(raw: dict, source_url: str) -> dict:
    """
    Standardise a raw person dict:
    - Remap aliased keys to canonical names
    - Ensure every canonical field exists (null if missing)
    - Resolve relative URLs to absolute
    - Deduplicate 'extra' from known fields
    """
    person: dict[str, Any] = {}
    extra: dict[str, Any]  = {}

    for raw_key, value in raw.items():
        key = raw_key.lower().strip().replace(" ", "_").replace("-", "_")
        canonical = _FIELD_ALIASES.get(key, key)
        if canonical in PERSON_FIELDS:
            person[canonical] = value
        else:
            extra[raw_key] = value

    # Merge existing extra dict with spill-over
    if "extra" in person and isinstance(person["extra"], dict):
        person["extra"] = {**person["extra"], **extra}
    else:
        person["extra"] = extra or None

    # Ensure all canonical fields present
    for f in PERSON_FIELDS:
        person.setdefault(f, None)

    # Resolve relative and protocol-relative URLs
    for url_field in ("image_url", "profile_url", "linkedin_url",
                      "twitter_url", "other_url"):
        val = person.get(url_field)
        if val and isinstance(val, str) and not val.startswith(("http://", "https://")):
            person[url_field] = urljoin(source_url, val)

    # Clean up name: strip location + "Meet [FirstName]" CTA text that some
    # scrapers concatenate when using .get_text() on the whole card element.
    # Pattern: "John SmithNew YorkMeet John"
    name = person.get("name") or ""
    if name:
        # Strip "Meet <Word>" suffix (CTA link text)
        name = re.sub(r"\s*Meet\s+\w[\w\-']*\s*$", "", name).strip()
        # Strip a trailing location if it appears literally inside the name
        loc = person.get("location") or ""
        if loc and name.endswith(loc):
            name = name[: -len(loc)].strip()
        person["name"] = name or None

    # Split name + title concatenations caused by .get_text() on card elements
    # that contain both name and title as child elements without a separator.
    # E.g. "Ahmed Abou ElelaHead of Corporate" → name + title split.
    # Detection: lowercase letter immediately followed by a known title keyword.
    _CONCAT_TITLE_RE = re.compile(
        r"(?<=[a-z])"
        r"((?:Head\s+of|Group\s+Chief|Deputy\s+Chief|Chief|"
        r"Managing\s+Director|Executive\s+Director|"
        r"Senior\s+Vice\s+President|Executive\s+Vice\s+President|"
        r"Vice\s+President|President|Director|Partner|"
        r"General\s+Manager|Senior\s+Manager|Manager|"
        r"Senior\s+Associate|Associate|Officer|Counsel|"
        r"Advisor|Specialist|Coordinator|Supervisor|"
        r"Head\b|Lead\b)"
        r".*)",
        re.DOTALL,
    )
    name = person.get("name") or ""
    if name:
        m = _CONCAT_TITLE_RE.search(name)
        if m:
            extracted_title = m.group(1).strip()
            clean_name = name[: m.start(1)].strip()
            if clean_name:
                person["name"] = clean_name
                # Only set title if not already populated
                if not person.get("title"):
                    person["title"] = extracted_title

    # Drop company LinkedIn pages — only personal profiles (/in/) are valid
    li = person.get("linkedin_url")
    if li and "linkedin.com" in li and "/in/" not in li:
        person["linkedin_url"] = None

    # Drop company Twitter/X accounts (contain no personal path segment)
    # Personal URLs look like twitter.com/handle — company ones often end at
    # twitter.com/CompanyName with no further path or are the same across records.
    # We detect the most common pattern: twitter.com/<OrgName> (single path segment
    # matching CamelCase / all-caps org name) vs twitter.com/<lowercase_handle>
    tw = person.get("twitter_url")
    if tw:
        tw_path = urlparse(tw).path.strip("/")
        # Heuristic: org accounts use CamelCase or contain underscore+uppercase
        # Personal handles are typically lowercase. Flag if it looks like an org.
        if tw_path and re.match(r"[A-Z]", tw_path):
            person["twitter_url"] = None

    # Drop profile_url values that point to non-person pages
    # (industry, service, insight, capability, topic pages, etc.)
    # NOTE: "about" is intentionally excluded — many firms put their people
    # under /about/people/... or /about/us/team/... (e.g. BCG: /about/people/experts/)
    _NON_PERSON_PATH_SEGMENTS = {
        "industries", "industry", "services", "service", "insights", "insight",
        "capabilities", "capability", "sectors", "sector", "solutions",
        "work", "news", "blog", "press", "events", "resources", "publications",
        "media", "contact", "careers", "jobs",
    }
    purl = person.get("profile_url")
    if purl:
        path_parts = set(urlparse(purl).path.strip("/").split("/"))
        if path_parts & _NON_PERSON_PATH_SEGMENTS:
            person["profile_url"] = None

    # Cross-field sanity: detect when location was filled with a job title.
    # LLM-generated scrapers sometimes mislabel a "position" field as "location".
    # Real locations contain geographic keywords; titles contain role keywords.
    _TITLE_INDICATORS = re.compile(
        r"\b(director|partner|manager|president|officer|board\s+member|"
        r"vice\s+president|associate|analyst|consultant|counsel|"
        r"head\s+of|chief|ceo|cfo|coo|cto|cio|svp|evp|avp|"
        r"managing|senior|junior|principal|leader|chair)\b",
        re.IGNORECASE,
    )
    _GEO_INDICATORS = re.compile(
        r"\b(new\s+york|london|paris|chicago|los\s+angeles|tokyo|dubai|"
        r"singapore|hong\s+kong|sydney|usa|uk|us|europe|asia|"
        r"north\s+america|middle\s+east|africa|australia|germany|"
        r"france|india|canada|china|brazil|california|texas|"
        r"massachusetts|illinois|city|state|county)\b",
        re.IGNORECASE,
    )
    loc = person.get("location") or ""
    if loc and _TITLE_INDICATORS.search(loc) and not _GEO_INDICATORS.search(loc):
        # Location looks like a job title — clear it
        person["location"] = None

    # Annotate source
    person["_source_url"] = source_url
    return person


def normalise_people(records: list[dict], source_url: str) -> list[dict]:
    normalised = []
    seen: set = set()
    for r in records:
        if not isinstance(r, dict):
            continue
        p = normalise_person(r, source_url)
        if not p.get("name"):
            continue
        # Discard ghost records — nav items / category labels that have only a
        # name and no corroborating data (no image, title, bio, email, urls…)
        _SUBSTANTIVE = ("title", "bio", "email", "phone", "linkedin_url",
                        "image_url", "profile_url", "location")
        if not any(p.get(f) for f in _SUBSTANTIVE):
            continue
        # Deduplicate by profile_url (most precise) or (name, title) pair
        key = p.get("profile_url") or (p["name"].lower(), (p.get("title") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        normalised.append(p)
    return normalised


# ---------------------------------------------------------------------------
# Profile page follower
# ---------------------------------------------------------------------------

def enrich_from_profile_pages(
    people:       list[dict],
    scraper:      "ScraperModule",
    client:       LLMClient,
    session:      WafSession,
    script_path:  Path,
    max_profiles: int = 10000,
    workers:      int = 6,
) -> list[dict]:
    """
    For every person that has a profile_url, fetch the detail page and
    merge any additional fields into the record.

    Uses `scraper.scrape_profile_page()` which calls the `scrape_profile_page()`
    function already appended to the listing script (Step 3.5).  If it returns
    nothing, the LLM is asked to generate/regenerate the function and the script
    is updated in place.

    Skips people who already have bio extracted from a modal.
    For modal-based sites (detected when any people already have bio from the
    listing/modal page), also skips people whose modals were empty — the profile
    page exists as an incidental link but the site uses Pattern A (modal), so
    falling back to the profile page is not desirable.

    Fetches up to `workers` profiles in parallel for speed.
    """
    import concurrent.futures

    enriched       = 0
    total_with_url = sum(1 for p in people if p.get("profile_url"))

    # Detect modal-based sites: if ≥10% of people already have bio extracted
    # from the listing/modal page (not from a prior profile enrichment), this
    # site uses Pattern A.  For such sites, skip people with no bio — their
    # modal was empty and we should not fall back to their profile page.
    # A "real" bio must be >80 chars — short strings like "Meet John" or
    # "View Profile" are button labels, not bios.
    _MIN_BIO_LEN = 80
    bio_from_listing = sum(
        1 for p in people
        if p.get("bio") and len(p["bio"]) >= _MIN_BIO_LEN
        and not p.get("_profile_enriched")
    )
    is_modal_site = bio_from_listing > 0 and bio_from_listing >= len(people) * 0.10
    if is_modal_site:
        log.info(
            f"  Modal-based site detected ({bio_from_listing}/{len(people)} people "
            "have bio from listing/modal). Skipping profile enrichment for people "
            "who already have bios."
        )

    # Build the list of (index, person, url) to enrich.
    # People who already have a bio (≥80 chars) are skipped — whether from
    # modal extraction or the listing page.  On "modal sites" we used to skip
    # ALL remaining people, but that was too aggressive — people whose modals
    # were empty or who have bios on a separate detail page were missed.
    to_enrich: list[tuple[int, dict, str]] = []
    for idx, person in enumerate(people):
        if len(to_enrich) >= max_profiles:
            break
        purl = person.get("profile_url")
        if not purl:
            continue
        if person.get("bio") and len(person["bio"]) >= _MIN_BIO_LEN:
            continue
        to_enrich.append((idx, person, purl))

    if not to_enrich:
        log.info(f"  [PROFILE] Enriched 0/{total_with_url} profiles")
        return people

    log.info(f"  [PROFILE] Enriching {len(to_enrich)} profiles with {workers} workers ...")

    # Track whether the scraper function has been regenerated (only do once)
    _regen_done = False

    def _enrich_one(idx: int, person: dict, purl: str) -> tuple[int, dict | None]:
        """Fetch + scrape a single profile page. Returns (idx, merged_detail)."""
        nonlocal _regen_done
        try:
            detail = scraper.scrape_profile_page(purl, session)

            # Script returned nothing — regenerate once then retry
            if not detail and not _regen_done:
                _regen_done = True
                log.warning("  [PROFILE] Script returned empty — calling LLM to (re)generate profile function ...")
                html, _     = fetch_html(purl, session)
                clean       = simplify_html(html)
                fn_txt      = call_llm(client, purl, clean, profile_function=True)
                fn_code, _  = parse_llm_response(fn_txt)
                existing    = script_path.read_text(encoding="utf-8")
                if "def scrape_profile_page(" in existing:
                    new_code = re.sub(
                        r"\n\ndef scrape_profile_page\(.*",
                        "\n\n" + fn_code,
                        existing,
                        flags=re.DOTALL,
                    )
                else:
                    new_code = existing + "\n\n" + fn_code
                script_path.write_text(new_code, encoding="utf-8")
                scraper.reload(new_code)
                log.info(f"  [PROFILE] scrape_profile_page() regenerated in {script_path.name}")
                detail = scraper.scrape_profile_page(purl, session)

            if detail and isinstance(detail, dict):
                return idx, normalise_person(detail, purl)
        except Exception as exc:
            log.warning(f"  [PROFILE] Failed to enrich {purl}: {exc}")
        return idx, None

    # Parallel fetch with thread pool — WafSession._rate_limit already
    # enforces per-domain delays, so concurrent requests are staggered.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_enrich_one, idx, person, purl): (idx, person)
            for idx, person, purl in to_enrich
        }
        for future in concurrent.futures.as_completed(futures):
            idx, merged = future.result()
            if merged:
                person = people[idx]
                for f in PERSON_FIELDS:
                    if not person.get(f) and merged.get(f):
                        person[f] = merged[f]
                person["_profile_enriched"] = True
                enriched += 1
                log.info(f"  [PROFILE] Enriched {person.get('name')!r}")

    log.info(f"  [PROFILE] Enriched {enriched}/{total_with_url} profiles")
    return people

# ---------------------------------------------------------------------------
# Dynamic script loader
# ---------------------------------------------------------------------------
class ScraperModule:
    def __init__(self, code: str):
        self._mod = self._load(code)

    def _load(self, code: str):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        try:
            spec = importlib.util.spec_from_file_location("_dyn_scraper", path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            Path(path).unlink(missing_ok=True)

    def scrape_page(self, url: str, session: WafSession) -> list[dict]:
        if not hasattr(self._mod, "scrape_page"):
            raise AttributeError("Generated script has no scrape_page() function.")
        result = self._mod.scrape_page(url, session)
        return result if isinstance(result, list) else []

    def scrape_profile_page(self, url: str, session: WafSession) -> dict | None:
        """Call scrape_profile_page() if present, else fall back to scrape_page()[0]."""
        if hasattr(self._mod, "scrape_profile_page"):
            result = self._mod.scrape_profile_page(url, session)
            return result if isinstance(result, dict) else None
        # Fallback for scripts that don't have the dedicated function yet
        results = self.scrape_page(url, session)
        return results[0] if results else None

    def has_profile_function(self) -> bool:
        return hasattr(self._mod, "scrape_profile_page")

    def get_next_url(self, html: str, current_url: str) -> str | None:
        if hasattr(self._mod, "get_next_url"):
            return self._mod.get_next_url(html, current_url)
        return None

    def reload(self, new_code: str):
        self._mod = self._load(new_code)

# ---------------------------------------------------------------------------
# Pagination Engine
# ---------------------------------------------------------------------------
class PaginationEngine:
    """Drives multi-page scraping. Yields (page_url, raw_html) per page.

    For strategies with predictable URLs (query_param, path_segment), a
    background thread prefetches the next PREFETCH_AHEAD pages while the
    caller processes the current one.  This overlaps network I/O with
    scraping CPU work and typically halves wall-clock time.
    """

    PREFETCH_AHEAD = 3  # how many pages to fetch ahead

    def __init__(self, start_url: str, info: PaginationInfo, session: WafSession):
        self.start_url = start_url
        self.info      = info
        self.session   = session
        self._stop     = threading.Event()

    def pages(self):
        s = self.info.strategy
        if   s == "none":                      yield from self._single()
        elif s == "query_param":               yield from self._prefetch_pages(self._qp_url_gen)
        elif s == "path_segment":              yield from self._prefetch_pages(self._path_url_gen)
        elif s in ("next_link", "cursor"):     yield from self._next_link_pages()
        else:                                  yield from self._single()

    # ── URL generators (yield url strings) ─────────────────────────────
    def _qp_url_gen(self):
        param   = self.info.param_name or "page"
        step    = self.info.param_step  or 1
        current = self.info.param_start if self.info.param_start is not None else 1
        total_p = self.info.total_pages or 0
        seen: set[str] = set()
        for n in range(MAX_PAGES):
            url = self._set_qp(self.start_url, param, current)
            if url in seen: return
            seen.add(url)
            yield url
            if total_p and (n + 1) >= total_p: return
            current += step

    def _path_url_gen(self):
        step    = self.info.param_step  or 1
        current = self.info.param_start if self.info.param_start is not None else 1
        total_p = self.info.total_pages or 0
        param   = self.info.param_name or ""
        seen: set[str] = set()

        # When param_name is set (e.g. "start"), the base URL is page 1
        # (no path segment), and param_start is the value for page 2.
        # Yield the base URL first, then start generating segment URLs.
        if param:
            base = self.start_url.rstrip("/") + "/"
            if base not in seen:
                seen.add(base)
                yield self.start_url
                if total_p and total_p <= 1:
                    return

        for n in range(MAX_PAGES):
            url = self._set_path(self.start_url, current, param)
            if url in seen: return
            seen.add(url)
            yield url
            pages_so_far = n + 1 + (1 if param else 0)
            if total_p and pages_so_far >= total_p: return
            current += step

    # ── Prefetch-based iteration ───────────────────────────────────────
    def _prefetch_pages(self, url_gen_fn):
        """Fetch pages using a background prefetch thread."""
        buf: queue.Queue[tuple[str, str] | None] = queue.Queue(
            maxsize=self.PREFETCH_AHEAD
        )
        self._stop.clear()

        def _producer():
            try:
                for url in url_gen_fn():
                    if self._stop.is_set():
                        return
                    html, _ = fetch_html(url, self.session)
                    self.session.prime_cache(url, html)
                    # Use timeout so we can check _stop if consumer quit
                    while not self._stop.is_set():
                        try:
                            buf.put((url, html), timeout=0.5)
                            break
                        except queue.Full:
                            continue
            except Exception as e:
                log.warning(f"  [PREFETCH] Error: {e}")
            finally:
                buf.put(None)  # sentinel

        t = threading.Thread(target=_producer, daemon=True)
        t.start()
        try:
            while True:
                item = buf.get()
                if item is None:
                    break
                yield item
        finally:
            self._stop.set()
            t.join(timeout=5)

    def _single(self):
        html, _ = fetch_html(self.start_url, self.session)
        self.session.prime_cache(self.start_url, html)
        yield self.start_url, html

    def _next_link_pages(self):
        current = self.start_url
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            if current in seen: break
            seen.add(current)
            html, _ = fetch_html(current, self.session)
            self.session.prime_cache(current, html)
            yield current, html
            nxt = self._find_next(html, current)
            if not nxt or nxt in seen: break
            current = nxt
            # WafSession._rate_limit already enforces per-domain delays

    # ── URL builders ────────────────────────────────────────────────────
    @staticmethod
    def _set_qp(url: str, param: str, value: int) -> str:
        parts = urlparse(url)
        qs    = parse_qs(parts.query, keep_blank_values=True)
        qs[param] = [str(value)]
        return urlunparse(parts._replace(query=urlencode({k: v[0] for k, v in qs.items()})))

    @staticmethod
    def _set_path(url: str, page: int, param_name: str = "") -> str:
        parsed   = urlparse(url)
        trailing = "/" if parsed.path.endswith("/") else ""
        path     = parsed.path.rstrip("/")

        if param_name:
            # Named path segment: /team/start/24 where param_name="start"
            pattern = rf"/{re.escape(param_name)}/\d+"
            new_path, n = re.subn(pattern, f"/{param_name}/{page}", path)
            if not n:
                new_path = path + f"/{param_name}/{page}"
        else:
            new_path, n = re.subn(r"/(\d+)$", f"/{page}", path)
            if not n:
                if re.search(r"/page/?$", path, re.I):
                    new_path = path.rstrip("/") + f"/{page}"
                else:
                    new_path = path + f"/{page}"
        return urlunparse(parsed._replace(path=new_path + trailing))

    def _find_next(self, html: str, current_url: str) -> str | None:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # LLM-provided selector first
        if self.info.next_link_selector:
            el = soup.select_one(self.info.next_link_selector)
            if el and el.get("href"):
                return urljoin(current_url, el["href"])

        # Common CSS patterns
        for sel in [
            'a[rel="next"]', 'a.next', 'a.next-page', 'a#next',
            'a[aria-label="Next"]', 'li.next a', '.pagination a:last-child',
        ]:
            el = soup.select_one(sel)
            if el and el.get("href") not in (None, "#", "javascript:void(0)", ""):
                return urljoin(current_url, el["href"])

        # Text-based fallback
        for a in soup.find_all("a", href=True):
            if a.get_text(strip=True).lower() in ("next", "next page", ">", ">>", "next >>", "next >"):
                href = a["href"]
                if href not in ("#", "javascript:void(0)", ""):
                    return urljoin(current_url, href)

        return None

# ---------------------------------------------------------------------------
# Main scraping orchestrator
# ---------------------------------------------------------------------------
def scrape_site(
    url: str,
    client: LLMClient,
    session: WafSession,
    follow_profiles: bool = False,
    no_follow_profiles: bool = False,
    max_profiles: int = 10000,
    resume_state: dict | None = None,
    _category_depth: int = 0,
) -> tuple[list[dict], dict]:
    """Full pipeline for one site: fetch -> LLM -> paginate -> normalise -> (optionally enrich)."""

    slug        = re.sub(r"[^\w]", "_", urlparse(url).netloc)[:40]
    script_path = SCRIPTS_DIR / f"scrape_{slug}.py"

    # Pre-determine output paths so they are stable across resume runs
    if resume_state and resume_state.get("json_path"):
        json_path_out = Path(resume_state["json_path"])
        csv_path_out  = Path(resume_state["csv_path"])
    else:
        ts = int(time.time())
        json_path_out = OUTPUT_DIR / f"{slug}_{ts}.json"
        csv_path_out  = OUTPUT_DIR / f"{slug}_{ts}.csv"

    meta_path = SCRIPTS_DIR / f"scrape_{slug}.meta.json"

    if resume_state and script_path.exists():
        # ── RESUME PATH ──────────────────────────────────────────────────
        log.info(f"  [RESUME] Loading saved script from {script_path}")
        code           = script_path.read_text(encoding="utf-8")
        pagination_raw = resume_state.get("pagination", {})
        pinfo          = PaginationInfo.from_dict(pagination_raw)
        meta_raw       = resume_state.get("meta_raw", {})
        html1          = None  # Not re-fetched on resume
    elif script_path.exists() and not resume_state:
        # ── REUSE PATH — existing script, no resume ──────────────────────
        log.info(f"  [REUSE] Loading existing script from {script_path}")
        code = script_path.read_text(encoding="utf-8")
        html1, final_url = fetch_html(url, session)  # Still needed for pagination + page data
        if final_url != url:
            log.info(f"  [REUSE] Redirected {url} -> {final_url}, updating base URL")
            url = final_url

        # Load pagination metadata from companion file
        if meta_path.exists():
            try:
                saved_meta     = json.loads(meta_path.read_text(encoding="utf-8"))
                pagination_raw = saved_meta.get("pagination", {})
                meta_raw       = saved_meta.get("meta_raw", {})
                log.info(f"  [REUSE] Loaded pagination metadata from {meta_path}")
            except (json.JSONDecodeError, KeyError):
                log.warning(f"  [REUSE] Could not read {meta_path}, re-detecting pagination")
                pagination_raw = {}
                meta_raw       = {}
        else:
            pagination_raw = {}
            meta_raw       = {}

        if isinstance(pagination_raw, bool):
            pagination_raw = {"strategy": "query_param" if pagination_raw else "none"}
        pinfo = PaginationInfo.from_dict(pagination_raw)

        # Ensure meta file exists (backfill for scripts created before meta persistence)
        if not meta_path.exists():
            meta_path.write_text(json.dumps({
                "team_url":   url,
                "pagination": pagination_raw,
                "meta_raw":   meta_raw,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # ── FRESH PATH ───────────────────────────────────────────────────
        html1, final_url = fetch_html(url, session)
        if final_url != url:
            log.info(f"  [SCRAPE] Redirected {url} -> {final_url}, updating base URL")
            url = final_url
        clean1         = simplify_html(html1)
        llm_txt        = call_llm(client, url, clean1)
        code, meta_raw = parse_llm_response(llm_txt)
        pagination_raw = meta_raw.get("pagination", {})
        if isinstance(pagination_raw, bool):
            pagination_raw = {"strategy": "query_param" if pagination_raw else "none"}
        pinfo = PaginationInfo.from_dict(pagination_raw)
        script_path.write_text(code, encoding="utf-8")
        log.info(f"  Script -> {script_path}")

        # Save companion metadata file for future reuse
        meta_path.write_text(json.dumps({
            "team_url":   url,
            "pagination": pagination_raw,
            "meta_raw":   meta_raw,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(
        f"  Pagination: {pinfo.strategy}"
        + (f" | param={pinfo.param_name}" if pinfo.param_name else "")
        + (f" | ~{pinfo.total_pages} pages" if pinfo.total_pages else "")
    )

    # On resume: adjust starting position
    resume_start_url = url
    if resume_state:
        pages_already = resume_state.get("pages_scraped", 0)
        if pinfo.strategy in ("query_param", "path_segment") and pages_already:
            step = pinfo.param_step or 1
            # For named path segments (e.g. /start/24), page 1 is the base URL,
            # so only (pages_already - 1) segment-pages have been scraped.
            segment_pages = max(0, pages_already - 1) if pinfo.param_name else pages_already
            pinfo.param_start = (pinfo.param_start or 1) + segment_pages * step
        elif pinfo.strategy in ("next_link", "cursor"):
            resume_start_url = resume_state.get("last_next_url") or url

    engine_start = resume_start_url if pinfo.strategy in ("next_link", "cursor") else url
    scraper = ScraperModule(code)
    engine  = PaginationEngine(engine_start, pinfo, session)

    # Load already-collected records on resume
    all_records: list[dict] = load_all_records(slug) if resume_state else []

    # Pre-load the cache with the already-fetched first page so the engine
    # doesn't make a redundant HTTP request for page 1.
    # Only cache if html1 is real content (not WAF challenge residue).
    if html1 is not None and len(html1) >= MIN_PAGE_HTML:
        if pinfo.strategy == "query_param":
            first_paged = PaginationEngine._set_qp(
                url, pinfo.param_name or "page",
                pinfo.param_start if pinfo.param_start is not None else 1,
            )
            session.prime_cache(first_paged, html1)
        elif pinfo.strategy == "path_segment":
            if pinfo.param_name:
                # Named segment (e.g. /start/24) — page 1 is the base URL
                session.prime_cache(url, html1)
            else:
                first_paged = PaginationEngine._set_path(
                    url, pinfo.param_start if pinfo.param_start is not None else 1,
                )
                session.prime_cache(first_paged, html1)
        elif pinfo.strategy in ("none", "next_link", "cursor"):
            session.prime_cache(url, html1)

    # Repair fires immediately for single-page sites; after 2 misses for paginated
    repair_threshold = 1 if pinfo.strategy == "none" else 2

    # Step 2 — walk all pages
    consecutive_empty   = 0
    page_num            = 0
    completed_naturally = False
    seen_page_fingerprints: set[frozenset] = set()  # duplicate-page detection
    waf_skipped_pages: list[str] = []  # pages skipped due to WAF — retry later

    try:
        for page_url, page_html in engine.pages():
            page_num += 1
            log.info(f"  Page {page_num}: {page_url}")

            # WAF/challenge residue — don't run the scraper, don't count as
            # empty (which would trigger self-repair on garbage HTML).
            if len(page_html) < MIN_PAGE_HTML:
                log.warning(
                    f"  Skipped — HTML too short ({len(page_html)} chars), "
                    "WAF/challenge residue"
                )
                waf_skipped_pages.append(page_url)
                continue

            try:
                records = scraper.scrape_page(page_url, session)
            except Exception as exc:
                log.warning(f"  scrape_page error: {exc}")
                records = []

            if not records:
                consecutive_empty += 1
                log.warning(f"  Empty ({consecutive_empty} consecutive)")

                # If the very first paginated page is empty but we have the
                # original un-paginated HTML, fall back to single-page mode.
                if (page_num == 1
                        and pinfo.strategy != "none"
                        and html1 is not None
                        and len(html1) >= MIN_PAGE_HTML):
                    log.info("  First paginated page empty — falling back to "
                             "single-page mode with original HTML")
                    # Prime cache so scrape_page can fetch the base URL
                    session.prime_cache(url, html1)
                    try:
                        records = scraper.scrape_page(url, session)
                    except Exception:
                        records = []
                    if not records:
                        # Full re-generation (not repair) for the original page
                        log.info("  Calling LLM for single-page re-gen ...")
                        try:
                            clean_p  = simplify_html(html1)
                            rep_txt  = call_llm(client, url, clean_p)
                            new_code, _ = parse_llm_response(rep_txt)
                            scraper.reload(new_code)
                            session.prime_cache(url, html1)
                            records = scraper.scrape_page(url, session)
                            if records:
                                script_path.write_text(new_code, encoding="utf-8")
                        except Exception as e:
                            log.error(f"  Single-page re-gen failed: {e}")
                    if records:
                        log.info(f"  Single-page fallback OK: {len(records)} records")
                        all_records.extend(records)
                        append_page_records(slug, records)
                    break

                if consecutive_empty >= repair_threshold:
                    successful_pages = page_num - consecutive_empty - len(waf_skipped_pages)
                    success_ratio = successful_pages / max(page_num, 1)
                    if successful_pages > 5 and success_ratio > 0.8:
                        log.info(
                            f"  {successful_pages}/{page_num} pages succeeded "
                            f"({success_ratio:.0%}) — treating empty as end-of-content"
                        )
                        break
                    # Low success ratio — likely WAF/transient failure, not
                    # a selector issue.  Skip and keep paginating; resume
                    # logic handles permanent failures at the task level.
                    max_consecutive = 5
                    if consecutive_empty >= max_consecutive:
                        log.warning(
                            f"  {consecutive_empty} consecutive empty pages "
                            f"(success ratio {success_ratio:.0%}) — stopping"
                        )
                        break
                    log.info(
                        f"  Empty page — skipping "
                        f"({consecutive_empty}/{max_consecutive} before stop)"
                    )
                    continue
            else:
                consecutive_empty = 0
                log.info(f"  {len(records)} records extracted")

                # Duplicate-page detection: same set of names = pagination param
                # has no effect (e.g. single-page lister with filters)
                fp = frozenset(r.get("name", "") for r in records)
                if fp in seen_page_fingerprints:
                    log.warning("  Duplicate page detected — pagination has no effect, stopping")
                    break
                seen_page_fingerprints.add(fp)

            # Extend and persist any records found this page
            if records:
                remaining = max_profiles - len(all_records)
                to_add = records[:remaining]
                all_records.extend(to_add)
                append_page_records(slug, to_add)
                if len(all_records) >= max_profiles:
                    log.info(f"  Reached max_profiles={max_profiles} — stopping pagination")
                    completed_naturally = True
                    break

            # Save incremental state after every page
            last_next_url = None
            if pinfo.strategy in ("next_link", "cursor"):
                last_next_url = engine._find_next(page_html, page_url)

            total_pages_so_far   = (resume_state.get("pages_scraped", 0) if resume_state else 0) + page_num
            original_param_start = (resume_state.get("original_param_start", pinfo.param_start)
                                    if resume_state else pinfo.param_start)
            next_param = None
            if pinfo.strategy in ("query_param", "path_segment"):
                step       = pinfo.param_step or 1
                next_param = original_param_start + total_pages_so_far * step

            save_progress(slug, {
                "url":                  url,
                "slug":                 slug,
                "script_path":          str(script_path),
                "pagination":           pagination_raw,
                "meta_raw":             meta_raw,
                "pages_scraped":        total_pages_so_far,
                "last_page_param":      next_param,
                "last_next_url":        last_next_url,
                "original_param_start": original_param_start,
                "records_count":        len(all_records),
                "json_path":            str(json_path_out),
                "csv_path":             str(csv_path_out),
                "status":               "in_progress",
            })
        else:
            completed_naturally = True

    except Exception as exc:
        log.warning(
            f"  Fetch error on page {page_num + 1} — stopping pagination early: {exc}\n"
            f"  Saving {len(all_records)} records collected so far."
        )
        total_pages_so_far   = (resume_state.get("pages_scraped", 0) if resume_state else 0) + page_num
        original_param_start = (resume_state.get("original_param_start", pinfo.param_start)
                                if resume_state else pinfo.param_start)
        save_progress(slug, {
            "url":                  url,
            "slug":                 slug,
            "script_path":          str(script_path),
            "pagination":           pagination_raw,
            "meta_raw":             meta_raw,
            "pages_scraped":        total_pages_so_far,
            "last_page_param":      None,
            "last_next_url":        None,
            "original_param_start": original_param_start,
            "records_count":        len(all_records),
            "json_path":            str(json_path_out),
            "csv_path":             str(csv_path_out),
            "status":               "interrupted",
        })

    # Step 2.5 — retry WAF-skipped pages
    if waf_skipped_pages:
        log.info(f"  [RETRY] Retrying {len(waf_skipped_pages)} WAF-skipped pages ...")
        for retry_url in waf_skipped_pages:
            log.info(f"  [RETRY] {retry_url}")
            try:
                retry_html, _ = fetch_html(retry_url, session)
                if len(retry_html) < MIN_PAGE_HTML:
                    log.warning(f"  [RETRY] Still blocked ({len(retry_html)} chars)")
                    continue
                records = scraper.scrape_page(retry_url, session)
                if records:
                    log.info(f"  [RETRY] Recovered {len(records)} records")
                    all_records.extend(records)
                    append_page_records(slug, records)
                else:
                    log.warning(f"  [RETRY] Page fetched but no records extracted")
            except Exception as exc:
                log.warning(f"  [RETRY] Failed: {exc}")

    # Step 2.6 — Category index detection
    # When we finish with 0 people at the top level (not a recursive call), check
    # whether the page is a category index that links to sub-sections with people.
    # This handles sites like teneo.com where /people shows 5 category cards
    # (financial-advisory, management-consulting, …) with no people directly listed.
    if len(all_records) <= 5 and html1 is not None and _category_depth == 0:
        cat_urls = discover_category_urls(html1, url)
        if cat_urls:
            log.info(f"  [CATEGORY] Scraping {len(cat_urls)} category sub-sections ...")
            # Delete the script generated for the (useless) category index page so
            # the first category page triggers a fresh LLM generation.  Subsequent
            # categories will reuse that script (same page layout).
            if script_path.exists():
                script_path.unlink(missing_ok=True)
                log.info(f"  [CATEGORY] Removed category-index script {script_path.name}")
            for i, cat_url in enumerate(cat_urls):
                log.info(f"  [CATEGORY] → {cat_url} ({i + 1}/{len(cat_urls)})")
                try:
                    cat_people, _ = scrape_site(
                        cat_url, client, session,
                        follow_profiles=follow_profiles,
                        no_follow_profiles=no_follow_profiles,
                        max_profiles=max(0, max_profiles - len(all_records)),
                        _category_depth=1,
                    )
                    all_records.extend(cat_people)
                    log.info(f"  [CATEGORY] Got {len(cat_people)} people from {cat_url}")
                except Exception as exc:
                    log.warning(f"  [CATEGORY] Failed to scrape {cat_url}: {exc}")

    # Step 3 — normalise to canonical people schema
    all_records = normalise_people(all_records, url)
    log.info(f"  {len(all_records)} valid people after normalisation")

    # Step 3.1 — fallback: extract bios from Bootstrap modals in page HTML.
    # Many sites use data-bs-toggle="modal" / data-target="#id" cards linked to
    # page-level <div class="modal" id="..."> containers.  If the LLM-generated
    # scraper missed the modal→bio link, this deterministic fallback catches it.
    _MIN_BIO_LEN_MODAL = 80
    people_missing_bio = [p for p in all_records if not p.get("bio") or len(p.get("bio", "")) < _MIN_BIO_LEN_MODAL]
    if people_missing_bio and len(people_missing_bio) >= len(all_records) * 0.5 and html1:
        try:
            from bs4 import BeautifulSoup as _BS
            soup = _BS(html1, "html.parser")
            # Find modal containers (Bootstrap 4/5 pattern)
            modals = soup.select("div.modal[id]")
            if modals:
                # Build id → bio text map from modal containers
                modal_bios: dict[str, str] = {}
                for modal in modals:
                    mid = modal.get("id", "")
                    # Look for bio text in common content containers
                    bio_el = modal.select_one(
                        ".about-self, .bio, .description, .modal-body .content, "
                        ".detail, .person-bio, .member-bio, .team-bio, .text-content"
                    )
                    if not bio_el:
                        # Fallback: grab all <p> tags inside modal-body
                        body = modal.select_one(".modal-body")
                        if body:
                            paragraphs = body.find_all("p")
                            if paragraphs:
                                bio_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                                if len(bio_text) >= _MIN_BIO_LEN_MODAL:
                                    modal_bios[mid] = bio_text
                                continue
                    if bio_el:
                        bio_text = "\n\n".join(
                            p.get_text(strip=True) for p in bio_el.find_all("p")
                            if p.get_text(strip=True)
                        ) or bio_el.get_text(strip=True)
                        if len(bio_text) >= _MIN_BIO_LEN_MODAL:
                            modal_bios[mid] = bio_text

                if modal_bios:
                    # Match each person to a modal bio by name (full → last → first).
                    # Track used modals to avoid assigning the same bio to two people.
                    used_modals: set[str] = set()
                    modal_matched = 0

                    def _find_modal(pname: str) -> str | None:
                        parts = pname.split()
                        if not parts:
                            return None
                        # 1. Full name match (most specific)
                        for mid, bio in modal_bios.items():
                            if mid not in used_modals and pname.lower() in bio.lower():
                                return mid
                        # 2. Last name ≥3 chars (avoids "Al", "El", "De")
                        if len(parts) >= 2:
                            last = parts[-1]
                            if len(last) >= 3:
                                for mid, bio in modal_bios.items():
                                    if mid not in used_modals and last.lower() in bio.lower():
                                        return mid
                        # 3. First name fallback
                        first = parts[0]
                        for mid, bio in modal_bios.items():
                            if mid not in used_modals and first.lower() in bio.lower():
                                return mid
                        return None

                    for person in all_records:
                        if person.get("bio") and len(person["bio"]) >= _MIN_BIO_LEN_MODAL:
                            continue
                        pname = person.get("name", "")
                        if not pname:
                            continue
                        mid = _find_modal(pname)
                        if mid:
                            person["bio"] = modal_bios[mid]
                            used_modals.add(mid)
                            modal_matched += 1

                    if modal_matched:
                        log.info(f"  [MODAL-FALLBACK] Extracted bios from {modal_matched} page-level modals")
        except Exception as exc:
            log.warning(f"  [MODAL-FALLBACK] Failed: {exc}")

    # Step 3.5 — probe first profile page to generate scrape_profile_page()
    # Only runs when: LLM detected profile links AND the function isn't already
    # in the script (fresh run or resumed without a prior probe).
    has_profiles = meta_raw.get("has_profile_pages", False)
    # When reusing a script without meta, infer from extracted records
    if not has_profiles and any(r.get("profile_url") for r in all_records):
        has_profiles = True
        log.info("  [REUSE] Detected profile URLs in extracted records")
    if has_profiles and not scraper.has_profile_function():
        first_purl = next(
            (r.get("profile_url") for r in all_records if r.get("profile_url")), None
        )
        if first_purl:
            log.info(f"  [PROFILE-FN] Probing first profile page: {first_purl}")
            try:
                probe_html, _  = fetch_html(first_purl, session)
                probe_clean = simplify_html(probe_html)
                fn_txt      = call_llm(client, first_purl, probe_clean, profile_function=True)
                fn_code, _  = parse_llm_response(fn_txt)
                # Append the new function to the existing listing script
                combined = script_path.read_text(encoding="utf-8") + "\n\n" + fn_code
                script_path.write_text(combined, encoding="utf-8")
                scraper.reload(combined)
                log.info(f"  [PROFILE-FN] scrape_profile_page() added to {script_path.name}")
            except Exception as exc:
                log.warning(f"  [PROFILE-FN] Probe failed — enrichment will use fallback: {exc}")

    # Cap total records before enrichment
    if len(all_records) > max_profiles:
        all_records = all_records[:max_profiles]

    # Step 4 — enrich from individual profile pages
    # Auto-triggered when the LLM detected profile links (has_profile_pages=True).
    # --follow-profiles forces it even when the LLM didn't detect them.
    # --no-follow-profiles disables enrichment entirely.
    should_follow = (has_profiles or follow_profiles) and not no_follow_profiles
    if should_follow:
        reason = "LLM detected profile pages" if has_profiles else "forced by --follow-profiles"
        log.info(f"  Following profile pages (max {max_profiles}, reason: {reason}) ...")
        all_records = enrich_from_profile_pages(
            all_records, scraper, client, session, script_path, max_profiles
        )

    total_pages_scraped = (resume_state.get("pages_scraped", 0) if resume_state else 0) + page_num
    meta = {
        "fields":            meta_raw.get("fields", []),
        "has_profile_pages": has_profiles,
        "pagination":        pagination_raw,
        "pages_scraped":     total_pages_scraped,
        "total_records":     len(all_records),
        "waf":               session.last_waf_info.to_dict(),
        "final_url":         url,  # may differ from original if redirected
        "_json_path":        str(json_path_out),
        "_csv_path":         str(csv_path_out),
    }

    # Clear progress files on natural (non-break, non-exception) completion
    if completed_naturally:
        clear_progress(slug)

    return all_records, meta

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_results(
    data: list[dict],
    url: str,
    meta: dict,
    json_path: Path | None = None,
    csv_path:  Path | None = None,
) -> tuple[Path, Path]:
    """Save people data as JSON + flat CSV. Returns (json_path, csv_path)."""
    slug = re.sub(r"[^\w]", "_", urlparse(url).netloc)[:40]
    if json_path is None:
        ts        = int(time.time())
        json_path = OUTPUT_DIR / f"{slug}_{ts}.json"
        csv_path  = OUTPUT_DIR / f"{slug}_{ts}.csv"

    # JSON — full nested data
    json_path.write_text(
        json.dumps({"url": url, "meta": meta, "count": len(data), "people": data},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV — flat, one row per person (extra dict serialised as JSON string)
    if data:
        # Collect all keys across all records for consistent header
        all_keys = list(dict.fromkeys(
            k for p in data for k in p.keys()
        ))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for person in data:
                row = {k: (json.dumps(v) if isinstance(v, dict) else v)
                       for k, v in person.items()}
                writer.writerow(row)

    log.info(
        f"  Saved -> {json_path.name}  ({len(data)} people, {meta['pages_scraped']} pages)"
    )
    return json_path, csv_path

# ---------------------------------------------------------------------------
# URL loader
# ---------------------------------------------------------------------------
def load_urls(filepath: str) -> list[str]:
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(filepath)
    urls: list[str] = []

    if p.suffix.lower() == ".json":
        raw   = json.loads(p.read_text())
        items = raw if isinstance(raw, list) else raw.get("urls", raw.get("URLs", []))
        for item in items:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                for k in ("url", "URL", "link", "href", "website"):
                    if k in item:
                        urls.append(item[k])
                        break

    elif p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            sample = f.read(1024); f.seek(0)
            if any(h in sample.lower() for h in ("url", "link", "href", "website")):
                for row in csv.DictReader(f):
                    for k in ("url", "URL", "link", "href", "website"):
                        if k in row:
                            urls.append(row[k].strip())
                            break
            else:
                for row in csv.reader(f):
                    if row:
                        urls.append(row[0].strip())
    else:
        raise ValueError(f"Unsupported file type: {p.suffix}")

    urls = [u for u in urls if u.startswith("http")]
    log.info(f"Loaded {len(urls)} URLs from {filepath}")
    return urls

# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------
def run_agent(
    urls:               list[str],
    api_key:            str | None       = None,
    proxies:            list[str] | None = None,

    web_unlocker:       bool             = False,
    discover:           bool             = False,
    follow_profiles:    bool             = False,
    no_follow_profiles: bool             = False,
    max_profiles:       int              = 10000,
    resume:             bool             = False,
) -> list[dict]:
    """
    Parameters
    ----------
    urls               : team-page URLs (or homepage URLs when discover=True)
    discover           : if True, auto-find the team page from each homepage first
    follow_profiles    : force profile-page enrichment even when LLM didn't detect links
    no_follow_profiles : disable profile-page enrichment entirely
    max_profiles       : max individual profile pages to fetch per site
    web_unlocker       : if True, proxy is a Bright Data Web Unlocker — skip challenge detection
    resume             : if True, load progress state and resume interrupted runs
    """
    llm_provider = os.environ.get("LLM_PROVIDER_SCRAPING", os.environ.get("LLM_PROVIDER", "claude"))
    client = LLMClient(provider=llm_provider, api_key=api_key)

    # CLI --proxies takes precedence; fall back to PROXY_URLS from .env
    if not proxies:
        env_proxies = os.environ.get("PROXY_URLS", "")
        if env_proxies.strip():
            proxies = [p.strip() for p in env_proxies.split(",") if p.strip()]
            log.info(f"Loaded {len(proxies)} proxies from PROXY_URLS env var")

    session = WafSession(
        proxies=proxies or [],

        web_unlocker=web_unlocker,
        min_delay=REQUEST_DELAY,
        max_delay=REQUEST_DELAY * 2.5,
    )
    summary: list[dict] = []

    for i, raw_url in enumerate(urls, 1):
        log.info(f"\n{'='*64}\n[{i}/{len(urls)}]  {raw_url}\n{'='*64}")

        # Auto-discover team page if requested
        team_url = raw_url
        if discover:
            # Check if we already have a saved team URL from a previous run
            domain_slug = re.sub(r"[^\w]", "_", urlparse(raw_url).netloc)[:40]
            cached_meta_path = SCRIPTS_DIR / f"scrape_{domain_slug}.meta.json"
            cached_team_url = None
            if cached_meta_path.exists():
                try:
                    cached_meta = json.loads(cached_meta_path.read_text(encoding="utf-8"))
                    cached_team_url = cached_meta.get("team_url")
                except (json.JSONDecodeError, KeyError):
                    pass

            if cached_team_url:
                team_url = cached_team_url
                log.info(f"  [DISCOVER] Reusing saved team URL: {team_url}")
            else:
                found = discover_team_url(client, raw_url, session)
                if found:
                    team_url = found
                else:
                    log.warning(f"  [DISCOVER] No team page found for {raw_url} — skipping")
                    summary.append({"url": raw_url, "status": "skipped",
                                     "reason": "team page not found"})
                    continue

        # Load resume state for this URL
        slug = re.sub(r"[^\w]", "_", urlparse(team_url).netloc)[:40]
        resume_state = None
        if resume:
            resume_state = load_progress(slug)
            if resume_state:
                st = resume_state.get("status")
                if st == "completed":
                    log.info(f"  [RESUME] {team_url} already completed — skipping")
                    summary.append({"url": team_url, "status": "skipped",
                                    "reason": "already completed"})
                    continue
                pages_done = resume_state.get("pages_scraped", 0)
                log.info(f"  [RESUME] Resuming {team_url} from page {pages_done + 1} "
                         f"({resume_state.get('records_count', 0)} records so far)")
            else:
                log.info(f"  [RESUME] No progress file found for {team_url} — starting fresh")

        entry: dict[str, Any] = {"url": team_url, "original_url": raw_url, "status": "pending"}

        try:
            data, meta = scrape_site(
                team_url, client, session,
                follow_profiles=follow_profiles,
                no_follow_profiles=no_follow_profiles,
                max_profiles=max_profiles,
                resume_state=resume_state,
            )
            _json_path = meta.pop("_json_path", None)
            _csv_path  = meta.pop("_csv_path", None)
            json_path, csv_path = save_results(
                data, team_url, meta,
                json_path=Path(_json_path) if _json_path else None,
                csv_path=Path(_csv_path)  if _csv_path  else None,
            )
            entry.update({
                "status":           "success",
                "people":           len(data),
                "pages_scraped":    meta["pages_scraped"],
                "json_file":        str(json_path),
                "csv_file":         str(csv_path),
                "fields_found":     meta.get("fields", []),
                "has_profile_pages": meta.get("has_profile_pages", False),
                "waf":              meta.get("waf", {}),
            })
            log.info(f"SUCCESS  {len(data)} people / {meta['pages_scraped']} pages")

        except Exception as exc:
            log.error(f"FAILED  {team_url} -> {exc}", exc_info=True)
            entry.update({
                "status": "error",
                "error":  str(exc),
                "waf":    session.last_waf_info.to_dict(),
            })

        summary.append(entry)
        time.sleep(REQUEST_DELAY)

    report = OUTPUT_DIR / f"run_summary_{int(time.time())}.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    log.info(f"\nSummary -> {report}")
    return summary

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    global MODEL, MAX_PAGES, REQUEST_DELAY
    ap = argparse.ArgumentParser(
        description="AI Team/People Scraper Agent v4 — WAF-aware, people-focused"
    )
    ap.add_argument("urls_file",    help="CSV or JSON file with URLs to scrape")
    ap.add_argument("--api-key",    default=None,   help="LLM API key (or set via env var)")
    ap.add_argument("--model",      default=MODEL,  help=f"LLM model (default: {MODEL})")
    ap.add_argument("--llm-provider", default=None,
                    choices=["claude", "openai", "deepseek", "gemini"],
                    help="LLM provider for scraping/discovery (default: from LLM_PROVIDER_SCRAPING or LLM_PROVIDER env var)")
    ap.add_argument("--max-pages",  type=int,   default=MAX_PAGES,      help="Max pages per site")
    ap.add_argument("--delay",      type=float, default=REQUEST_DELAY,  help="Base delay between requests (s)")
    ap.add_argument("--proxies",    nargs="*",  default=[],
                    metavar="PROXY", help="Proxy URLs e.g. http://user:pass@host:port")
    ap.add_argument("--web-unlocker", action="store_true",
                    help="Proxy is a Bright Data Web Unlocker — skips client-side challenge detection")
    ap.add_argument("--discover",   action="store_true",
                    help="Auto-discover team/people page from homepage URLs")
    ap.add_argument("--follow-profiles", action="store_true",
                    help="Force profile-page enrichment even when the scraper did not detect "
                         "profile links (profile pages are followed automatically when detected)")
    ap.add_argument("--no-follow-profiles", action="store_true",
                    help="Disable profile-page enrichment entirely, even when profile links are detected")
    ap.add_argument("--max-profiles", type=int, default=10000,
                    help="Max profile pages to follow per site (default: 100)")
    ap.add_argument("--resume", action="store_true",
                    help="Resume from last saved progress (skip completed sites, continue interrupted ones)")
    ap.add_argument("--debug", action="store_true",
                    help="Save raw HTML pages to html/ for inspection")
    args = ap.parse_args()

    global DEBUG_MODE
    DEBUG_MODE = args.debug

    MODEL, MAX_PAGES, REQUEST_DELAY = args.model, args.max_pages, args.delay
    if args.llm_provider:
        os.environ["LLM_PROVIDER_SCRAPING"] = args.llm_provider

    urls = load_urls(args.urls_file)
    if not urls:
        log.error("No valid URLs found.")
        sys.exit(1)

    summary = run_agent(
        urls,
        api_key=args.api_key,
        proxies=args.proxies,

        web_unlocker=args.web_unlocker,
        discover=args.discover,
        follow_profiles=args.follow_profiles,
        no_follow_profiles=args.no_follow_profiles,
        max_profiles=args.max_profiles,
        resume=args.resume,
    )

    ok     = sum(1 for s in summary if s["status"] == "success")
    people = sum(s.get("people", 0) for s in summary)
    pages  = sum(s.get("pages_scraped", 0) for s in summary)
    print(f"\nDone -- {ok}/{len(summary)} sites OK")
    print(f"  {people:,} people extracted across {pages:,} pages")
    print(f"  Results (JSON + CSV) in: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
