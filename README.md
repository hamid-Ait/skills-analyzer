# People Intelligence Platform

A full-stack platform that discovers, scrapes, and analyzes people from company websites. Upload company URLs, automatically extract team members, enrich profiles via LinkedIn, and analyze expertise using LLM — all through an interactive web dashboard with analytics, search, and data export.

## Architecture

```
                   ┌─────────────┐
                   │   Frontend   │  React + TypeScript + MUI + Recharts
                   │  :5173       │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │   Backend    │  FastAPI + SQLAlchemy
                   │  :8000       │
                   └──┬───────┬──┘
                      │       │
               ┌──────▼──┐ ┌──▼──────────┐
               │ Postgres │ │ Celery      │  Background task processing
               │  :5432   │ │ + Redis     │
               └──────────┘ │  :6379      │
                            └─────────────┘
```

- **Backend**: FastAPI + PostgreSQL 16 + Celery + Redis
- **Frontend**: React 18 + TypeScript + Vite + Material-UI + Recharts
- **LLM Providers**: Claude (Anthropic), OpenAI, or Gemini (Google) — configurable
- **LinkedIn Enrichment**: Apify (company employees actor + profile scraper)
- **Scraping Engine**: AI-powered with Claude + 5-tier WAF evasion

## Quick Start

### 1. Environment variables

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude — powers scraping agent + expertise analysis |
| `GOOGLE_API_KEY` | No | Gemini — alternative LLM for expertise analysis |
| `OPENAI_API_KEY` | No | OpenAI — alternative LLM for expertise analysis |
| `LLM_PROVIDER` | No | `claude`, `openai`, or `gemini` (default: `gemini`) |
| `APIFY_API_TOKEN` | No | LinkedIn enrichment via Apify actors |
| `SCRAPEDO_API_KEY` | No | Proxy service for scraping |
| `PROXY_URLS` | No | Comma-separated proxy URLs |

### 2. Start with Docker Compose

```bash
docker-compose up --build
```

Services launched:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **pgAdmin** on port 5050 (database UI)
- **FastAPI backend** on http://localhost:8000
- **Celery worker** (2 concurrent workers)
- **React frontend** on http://localhost:5173

### 3. Use the app

Open http://localhost:5173

1. **Upload** a JSON/CSV/TXT file with company URLs
2. **Watch** the dashboard as companies progress through the pipeline
3. **Explore** people data, expertise analysis, and skills matrices
4. **Analyze** cross-company insights on the Analytics page
5. **Search** across all people globally
6. **Export** data as CSV, JSON, XLSX, or ZIP (with photos)

## Processing Pipeline

Each company goes through a 6-stage pipeline:

```
Discover → Scrape → Search → Resolve → Enrich → Analyze
```

| Stage | Status | Description |
|-------|--------|-------------|
| **Discover** | `discovering` | Find the team/people page from the homepage using Claude |
| **Scrape** | `scraping` | Extract people from team pages with AI-generated scrapers |
| **Search** | `searching` | Fallback: find employees via LinkedIn company search (Apify) |
| **Resolve** | `resolving` | Match people to LinkedIn profiles via company employees actor + fuzzy name matching |
| **Enrich** | `enriching` | Fetch full LinkedIn profiles (headline, experience, education, skills) |
| **Analyze** | `analyzing` | LLM expertise analysis in batches — primary expertise, categories, sector, geography |

LinkedIn enrichment happens **before** LLM analysis so the LLM has access to rich profile data (experience, skills, education) for better expertise classification.

### LinkedIn Enrichment — How It Works

There are two Apify actors involved, each used at a different stage:

#### 1. Company Employees Actor (`harvestapi/linkedin-company-employees`)
Used during the **Resolve** stage for people who don't have a LinkedIn URL yet.

- Searches LinkedIn for all employees of a given company
- Returns up to 2,500 profiles with rich data (headline, experience, education, skills, photo)
- People are matched to scraped records by **fuzzy name matching** (threshold: 0.8 similarity)
- Matched profiles are marked as enriched immediately — no need for a second API call
- Unmatched people without URLs fall back to individual Google search (`site:linkedin.com/in "name" "company"`)

#### 2. Profile Scraper (`harvestapi/linkedin-profile-scraper`)
Used during the **Enrich** stage for people who already have a LinkedIn URL but haven't been enriched.

- Takes a list of LinkedIn profile URLs directly
- Processes in batches of 50 profiles per Apify call
- Extracts: headline, summary/about, experience, education, skills, location, photo
- Input format: `{ "profileScraperMode": "Profile details no email ($4 per 1k)", "queries": ["https://linkedin.com/in/..."] }`

#### Which path a person takes

```
Person scraped from website
  ├── Has LinkedIn URL? ──YES──→ Profile Scraper (enrich)
  │                                  ↓
  └── No URL? ─────────────────→ Company Employees Actor (resolve + enrich)
                                     │
                                     ├── Name matched? ──→ Enriched (done)
                                     └── Not matched? ───→ Google search for URL
                                                              │
                                                              ├── URL found? → Profile Scraper
                                                              └── No URL ───→ Skipped
```

All paths converge on the **Analyze** stage, where the LLM receives the enriched LinkedIn data (experience, skills, headline) alongside the original website data for expertise classification.

### Retry Modes

Companies with errors or incomplete data can be retried via the UI:

- **Re-scrape** — Delete all people, start the full pipeline from scratch
- **Re-analyze** — Keep people, re-run LLM expertise analysis only
- **Re-enrich** — Clear LinkedIn enrichment + expertise data, then:
  - People **with** LinkedIn URLs → go straight to Profile Scraper (skip resolve)
  - People **without** URLs → go through Resolve first

## Features

### Dashboard
- **Summary bar** — total companies, people, analyzed %, LinkedIn enriched %
- **In-progress cards** — live pipeline step indicator with progress dots
- **Company cards** — top 3 expertise categories, mini donut charts (analyzed/LinkedIn/photo completeness)
- Pagination and auto-refresh for active jobs

### Company Detail
- **People table** — sortable, searchable, with category filters
- **People cards** — visual card grid with avatars and expertise chips
- **Skills matrix** — bar charts (categories, sectors, geographies) + expertise pie chart
- **Retry button** — dropdown with re-scrape / re-analyze / re-enrich
- **Export** — CSV, JSON, XLSX, or ZIP with photos

### Analytics
- **Overview stats** — global counts across all completed companies
- **Data completeness table** — per-company analysis/enrichment coverage, sorted worst-first
- **Expertise heatmap** — companies x categories matrix
- **Charts** — category distribution, top expertise, sectors, geographies

### Global Search
- Search across all people by name, title, or expertise
- Filter by category, sector, or geography
- Results show company affiliation, LinkedIn links, and avatars

## API Endpoints

### Upload & Jobs
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload file with company URLs |
| `GET` | `/api/jobs` | List all jobs (paginated) |
| `GET` | `/api/jobs/{id}` | Job detail with company statuses |

### Companies
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/companies` | List companies (deduped by URL, filterable) |
| `GET` | `/api/companies/{id}` | Company detail |
| `POST` | `/api/companies/{id}/retry` | Retry processing (`rescrape`, `reanalyze`, `reenrich`) |

### People
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/companies/{id}/people` | Paginated people list (search, category filter) |
| `GET` | `/api/people/{id}` | Person detail |
| `GET` | `/api/companies/{id}/skills-matrix` | Expertise aggregations |

### Analytics
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/analytics/overview` | Global stats across all companies |
| `GET` | `/api/analytics/heatmap` | Companies x categories matrix |
| `GET` | `/api/analytics/search` | Global people search (q, category, sector, geography) |

### Export
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/export/{id}?format=csv` | Export as CSV, JSON, XLSX, or ZIP |

## Expertise Analysis

The LLM analyzes each person and produces:

| Field | Description |
|-------|-------------|
| `primary_expertise` | Main area of expertise (free text) |
| `justification` | Why this expertise was assigned |
| `matched_13_categories` | Mapped to 13 standard categories |
| `sector` | Industry sector |
| `geography` | Where expertise was applied (not just location) |
| `inferred_expertise_functional` | Functional expertise area |
| `matched_inferred_expertise_topics` | Matched topic tags |

The 13 categories: Artificial Intelligence & Data Science, Blockchain & Web3, Cybersecurity, Cloud & Infrastructure, Digital Transformation, Enterprise Software, FinTech, HealthTech, IoT & Hardware, Marketing & AdTech, Product & UX, SaaS & Platform, Sustainability & CleanTech.

## Project Structure

```
people-intelligence/
├── agent.py                  # AI scraping agent (v4) — Claude-powered
├── waf_bypass.py             # 5-tier WAF evasion layer
├── docker-compose.yml
├── requirements.txt
├── .env.example
│
├── backend/
│   └── app/
│       ├── main.py           # FastAPI entry point
│       ├── database.py       # SQLAlchemy session
│       ├── config.py         # Settings (env vars)
│       ├── models/           # ORM models
│       │   ├── job.py        #   Job (upload batch)
│       │   ├── company.py    #   Company (URL target)
│       │   └── person.py     #   Person (extracted profile)
│       ├── schemas/          # Pydantic response schemas
│       ├── api/              # Route handlers
│       │   ├── upload.py     #   File upload
│       │   ├── jobs.py       #   Job management
│       │   ├── companies.py  #   Company CRUD + retry
│       │   ├── people.py     #   People list + detail
│       │   ├── skills.py     #   Skills matrix
│       │   ├── export.py     #   Data export (CSV/JSON/XLSX/ZIP)
│       │   ├── analytics.py  #   Cross-company analytics
│       │   └── image_proxy.py#   Image proxy
│       ├── services/         # Business logic
│       │   ├── expertise_analyzer.py  # LLM expertise analysis
│       │   ├── apify_linkedin.py      # LinkedIn profile enrichment
│       │   └── apify_google_search.py # Company employees search
│       └── tasks/            # Celery background tasks
│           ├── celery_app.py          # Celery config
│           ├── scrape_task.py         # Scraping orchestration
│           ├── analyze_task.py        # LLM analysis batches
│           ├── linkedin_task.py       # LinkedIn enrichment
│           ├── resolve_linkedin_task.py # LinkedIn URL resolution
│           └── google_search_task.py  # Fallback employee search
│
└── frontend/
    └── src/
        ├── App.tsx               # Routes
        ├── api/
        │   ├── client.ts         # Axios instance
        │   ├── hooks.ts          # React data hooks
        │   └── types.ts          # TypeScript interfaces
        ├── pages/
        │   ├── UploadPage.tsx    # File upload form
        │   ├── DashboardPage.tsx # Company overview + summary bar
        │   ├── CompanyDetailPage.tsx # People + skills + retry
        │   ├── AnalyticsPage.tsx # Cross-company analytics
        │   └── GlobalSearchPage.tsx # Global people search
        └── components/
            ├── Layout.tsx           # App shell + navigation
            ├── PeopleTable.tsx      # Data grid
            ├── PeopleCards.tsx      # Card grid view
            ├── SkillsMatrix.tsx     # Charts + visualizations
            ├── PersonDetailModal.tsx # Profile modal
            ├── PipelineProgress.tsx  # Step progress indicator
            ├── StatusChip.tsx       # Status badge
            └── ExportButton.tsx     # Download menu
```

## Data Model

### Person fields extracted

| Source | Fields |
|--------|--------|
| **Website scraping** | name, title, department, bio, email, phone, location, image_url, profile_url, linkedin_url |
| **LinkedIn enrichment** | headline, summary, experience, education, skills, experience_summary, photo |
| **LLM analysis** | primary_expertise, justification, matched_13_categories, sector, geography |

### WAF Evasion

The scraping agent includes a 5-tier WAF evasion system:

| Tier | Method |
|------|--------|
| Headers | Full browser fingerprint (Sec-CH-UA, Sec-Fetch-*) |
| Timing | Jittered delays, per-domain rate limiting, back-off |
| Cookies | Persistent jar, Akamai ghost-token replay |
| Identity | UA rotation + fresh cookie jar on 403/503 |
| Playwright | Real headless Chrome for JS challenges |

Detects: Akamai, Cloudflare, Imperva, DataDome, PerimeterX, AWS WAF.