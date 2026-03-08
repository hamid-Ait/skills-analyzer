# AI Team/People Scraper Agent  v4

Intelligently scrapes **team, people, staff, leadership, and faculty pages** from any website.
Powered by Claude Opus — adapts to any HTML structure automatically.

---

## What it extracts

For every person found it extracts (whatever is present on the page):

| Field | Description |
|---|---|
| `name` | Full name |
| `title` | Job title / role / position |
| `department` | Team, division, or practice area |
| `bio` | Biography or description text |
| `email` | Email address |
| `phone` | Phone / mobile number |
| `linkedin_url` | LinkedIn profile URL |
| `twitter_url` | Twitter / X profile URL |
| `other_url` | Personal site, GitHub, etc. |
| `image_url` | Photo / headshot URL |
| `location` | Office, city, or country |
| `profile_url` | Link to individual profile page |
| `extra` | Any other fields found |

All records are normalised to this schema regardless of how different sites label their fields.

---

## Installation

```bash
pip install -r requirements.txt

# Optional: for JS-protected sites (Cloudflare, Akamai)
pip install playwright && playwright install chromium
```

---

## Usage

### You already know the team page URL
```bash
python agent.py team_urls.json
```

### You only have homepages — let the agent find the team page
```bash
python agent.py homepages.json --discover
```

### Follow individual profile pages for richer data (bio, email, etc.)
```bash
python agent.py team_urls.json --follow-profiles
```

### Full power mode
```bash
python agent.py homepages.json \
  --discover \
  --follow-profiles \
  --max-profiles 50 \
  --playwright \
  --proxies http://user:pass@proxy1:8080 http://user:pass@proxy2:8080 \
  --delay 2.0
```

---

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `urls_file` | — | CSV or JSON with URLs (required) |
| `--discover` | off | Auto-find team page from homepage URLs |
| `--follow-profiles` | off | Fetch each person's profile page for richer data |
| `--max-profiles` | 100 | Max profile pages per site |
| `--playwright` | off | Headless Chrome fallback for JS challenges |
| `--proxies` | none | Proxy URLs (space-separated) |
| `--delay` | 1.5 | Base seconds between requests |
| `--max-pages` | 200 | Safety cap per site |
| `--model` | `claude-opus-4-5` | Claude model |
| `--api-key` | env var | Anthropic API key |

---

## How `--discover` works

When you pass a list of **homepages**, the agent:
1. Fetches the homepage HTML
2. Asks Claude to scan all navigation and footer links
3. Claude identifies the most likely team/people/leadership URL
4. The agent proceeds to scrape that URL

Recognised page types: "Our Team", "Meet the Team", "Our People", "Leadership",
"Staff", "Partners", "Experts", "Faculty", "About Us > Team", "Who We Are", etc.

---

## How `--follow-profiles` works

Many team pages show only name + title on the listing page, with the full bio, email,
and contact info on a separate profile page. With `--follow-profiles`:
1. Listing page is scraped normally (name, title, photo, profile_url)
2. For each person that has a `profile_url` and is missing bio/email,
   the agent fetches that page and asks Claude to extract the remaining fields
3. Fields are merged back — existing values are never overwritten

---

## Output

```
scraped_data/
  mysite_com_1700000000.json     ← full nested JSON (all fields including extra)
  mysite_com_1700000000.csv      ← flat CSV, one row per person
  run_summary_1700000001.json    ← batch run summary

generated_scripts/
  scrape_mysite_com.py           ← reusable auto-generated scraper
```

### JSON structure
```json
{
  "url": "https://mysite.com/team",
  "meta": {
    "fields": ["name","title","bio","email","linkedin_url"],
    "has_profile_pages": true,
    "pagination": {"strategy": "query_param", "param_name": "page", "total_pages": 3},
    "pages_scraped": 3,
    "total_records": 47,
    "waf": {"waf_detected": false, "waf_name": "none", "bypassed": true}
  },
  "count": 47,
  "people": [
    {
      "name": "Jane Smith",
      "title": "Chief Executive Officer",
      "department": "Leadership",
      "bio": "Jane has 20 years of experience...",
      "email": "jane@mysite.com",
      "phone": null,
      "linkedin_url": "https://linkedin.com/in/janesmith",
      "twitter_url": null,
      "other_url": null,
      "image_url": "https://mysite.com/images/jane.jpg",
      "location": "New York",
      "profile_url": "https://mysite.com/team/jane-smith",
      "extra": null,
      "_source_url": "https://mysite.com/team",
      "_profile_enriched": true
    }
  ]
}
```

---

## WAF Evasion

| Tier | Handles |
|---|---|
| Headers | Full browser fingerprint, Sec-CH-UA, Sec-Fetch-* |
| Timing | Jittered delays, per-domain rate limiting, back-off |
| Cookies | Persistent jar, Akamai ghost-token replay |
| Identity rotation | New UA + fresh cookie jar on 403/503 |
| Playwright | Real headless Chrome for JS challenges |

Detects: Akamai, Cloudflare, Imperva, DataDome, PerimeterX, AWS WAF.

---

## Project Files

```
agent.py          Main agent (v4) — people/team focused
waf_bypass.py     5-tier WAF evasion layer
requirements.txt
example_urls.json
example_urls.csv
```
