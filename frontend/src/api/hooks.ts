import { useState, useEffect, useCallback, useRef } from 'react'
import api from './client'
import type { JobDetail, CompanyDetail, PersonDetail, PersonList, SkillsMatrix, AnalyticsOverview, HeatmapData, GlobalPersonList, CostSummary, AnalysisRun } from './types'

export function usePollingJob(jobId: string | null, intervalMs = 60000) {
  const [job, setJob] = useState<JobDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchJob = useCallback(async () => {
    if (!jobId) return
    try {
      const { data } = await api.get<JobDetail>(`/jobs/${jobId}`)
      setJob((prev) => {
        const isTerminal = data.status === 'completed' || data.status === 'error'
        const allCompaniesTerminal = data.companies.every(
          (c: any) => c.status === 'completed' || c.status === 'error'
        )
        if (isTerminal && allCompaniesTerminal && intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        return data
      })
    } catch (err) {
      console.error('Failed to fetch job:', err)
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    setLoading(true)
    fetchJob().then(() => setLoading(false))

    intervalRef.current = setInterval(fetchJob, intervalMs)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [jobId, fetchJob, intervalMs])

  return { job, loading }
}

export function useCompany(companyId: string | null) {
  const [company, setCompany] = useState<CompanyDetail | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    api
      .get<CompanyDetail>(`/companies/${companyId}`)
      .then(({ data }) => setCompany(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [companyId])

  return { company, loading }
}

export function usePeople(companyId: string | null, page = 1, pageSize = 50, search = '') {
  const [data, setData] = useState<PersonList | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })
    if (search) params.set('search', search)
    api
      .get<PersonList>(`/companies/${companyId}/people?${params}`)
      .then(({ data }) => setData(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [companyId, page, pageSize, search])

  return { data, loading }
}

export function usePerson(personId: string | null) {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!personId) { setPerson(null); return }
    setLoading(true)
    api
      .get<PersonDetail>(`/people/${personId}`)
      .then(({ data }) => setPerson(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [personId])

  return { person, loading }
}

export function useSkillsMatrix(companyId: string | null) {
  const [matrix, setMatrix] = useState<SkillsMatrix | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!companyId) return
    setLoading(true)
    api
      .get<SkillsMatrix>(`/companies/${companyId}/skills-matrix`)
      .then(({ data }) => setMatrix(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [companyId])

  return { matrix, loading }
}

export function useAnalyticsOverview() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api
      .get<AnalyticsOverview>('/analytics/overview')
      .then(({ data }) => setData(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return { data, loading }
}

export function useHeatmap() {
  const [data, setData] = useState<HeatmapData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api
      .get<HeatmapData>('/analytics/heatmap')
      .then(({ data }) => setData(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return { data, loading }
}

export function useGlobalSearch(
  q: string,
  category: string,
  sector: string,
  geography: string,
  page: number,
  pageSize: number,
) {
  const [data, setData] = useState<GlobalPersonList | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const params: Record<string, string | number> = { page, page_size: pageSize }
    if (q) params.q = q
    if (category) params.category = category
    if (sector) params.sector = sector
    if (geography) params.geography = geography

    api
      .get<GlobalPersonList>('/analytics/search', { params })
      .then(({ data }) => setData(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [q, category, sector, geography, page, pageSize])

  return { data, loading }
}

export async function reanalyzePerson(personId: string): Promise<{ status: string; person_id: string }> {
  const { data } = await api.post(`/people/${personId}/reanalyze`)
  return data
}

export async function analyzePersonWith(personId: string, provider: string, model?: string): Promise<AnalysisRun> {
  const { data } = await api.post(`/people/${personId}/analyze-with`, { provider, model: model || undefined })
  return data
}

export interface ProviderInfo {
  provider: string
  default_model: string
}

export function useProviders() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])

  useEffect(() => {
    api
      .get<ProviderInfo[]>('/providers')
      .then(({ data }) => setProviders(data))
      .catch(console.error)
  }, [])

  return providers
}

export function useAnalysisRuns(personId: string | null) {
  const [runs, setRuns] = useState<AnalysisRun[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(() => {
    if (!personId) return
    setLoading(true)
    api
      .get<AnalysisRun[]>(`/people/${personId}/analysis-runs`)
      .then(({ data }) => setRuns(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [personId])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { runs, loading, refresh }
}

export function useCostSummary(days = 30) {
  const [data, setData] = useState<CostSummary | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api
      .get<CostSummary>('/costs/summary', { params: { days } })
      .then(({ data }) => setData(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [days])

  return { data, loading }
}
