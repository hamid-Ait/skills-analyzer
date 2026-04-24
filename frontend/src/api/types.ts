export interface CompanyBrief {
  id: string
  url: string
  name: string | null
  team_url: string | null
  status: string
  error_message: string | null
  people_count: number
  pages_scraped: number
  created_at: string
  updated_at: string
  top_categories: string[]
  analyzed_pct: number
  linkedin_pct: number
  photo_pct: number
}

export interface CompanyDetail extends CompanyBrief {
  job_id: string
  waf_detected: boolean
  waf_name: string | null
  scrape_meta: Record<string, unknown> | null
}

export interface JobBrief {
  id: string
  filename: string | null
  total_urls: number
  completed_urls: number
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface JobDetail extends JobBrief {
  companies: CompanyBrief[]
}

export interface PersonBrief {
  id: string
  name: string
  title: string | null
  department: string | null
  location: string | null
  image_url: string | null
  linkedin_url: string | null
  primary_expertise: string | null
  matched_13_categories: string[] | null
  sector: string | null
}

export interface PersonDetail extends PersonBrief {
  company_id: string
  bio: string | null
  email: string | null
  phone: string | null
  twitter_url: string | null
  other_url: string | null
  profile_url: string | null
  source_url: string | null
  extra: Record<string, unknown> | null
  justification: string | null
  matched_sector: string[] | null
  geography: string | null
  inferred_expertise_functional: string[] | null
  inference_reasoning: string | null
  matched_inferred_expertise_topics: string[] | null
  linkedin_headline: string | null
  linkedin_summary: string | null
  linkedin_experience_summary: string | null
  linkedin_skills: string[] | null
  linkedin_enriched: boolean
  data_source: string | null
  profile_enriched: boolean
  created_at: string
  updated_at: string
}

export interface PersonList {
  items: PersonBrief[]
  total: number
  page: number
  page_size: number
}

export interface CategoryCount {
  name: string
  count: number
  percentage: number
}

export interface ExpertiseCount {
  name: string
  count: number
}

export interface SkillsMatrix {
  total_people: number
  total_analyzed: number
  categories: CategoryCount[]
  top_expertise: ExpertiseCount[]
  sectors: ExpertiseCount[]
  geographies: ExpertiseCount[]
}

export interface UploadResponse {
  job_id: string
  total_urls: number
  companies: CompanyBrief[]
}

// Analytics types

export interface CompanyStat {
  id: string
  name: string | null
  url: string
  people_count: number
  analyzed_count: number
  linkedin_enriched_count: number
  photo_count: number
}

export interface AnalyticsOverview {
  total_companies: number
  total_people: number
  total_analyzed: number
  total_linkedin_enriched: number
  total_with_photo: number
  categories: CategoryCount[]
  top_expertise: ExpertiseCount[]
  sectors: ExpertiseCount[]
  geographies: ExpertiseCount[]
  company_stats: CompanyStat[]
}

export interface HeatmapCompany {
  id: string
  name: string | null
  categories: Record<string, number>
}

export interface HeatmapData {
  companies: HeatmapCompany[]
  category_names: string[]
}

export interface GlobalPersonResult {
  id: string
  name: string
  title: string | null
  location: string | null
  image_url: string | null
  linkedin_url: string | null
  primary_expertise: string | null
  matched_13_categories: string[] | null
  sector: string | null
  geography: string | null
  company_id: string
  company_name: string | null
}

export interface GlobalPersonList {
  items: GlobalPersonResult[]
  total: number
  page: number
  page_size: number
}
