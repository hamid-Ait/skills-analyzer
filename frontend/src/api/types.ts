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
  justification: string | null
  geography: string | null
  inferred_expertise_functional: string | null
  matched_inferred_expertise_topics: string[] | null
  linkedin_headline: string | null
  linkedin_experience_summary: string | null
  data_source: string | null
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
