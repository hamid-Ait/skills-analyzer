import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Card, CardContent, CardActionArea,
  Alert, CircularProgress, Pagination, LinearProgress,
} from '@mui/material'
import { People, Language } from '@mui/icons-material'
import StatusChip from '../components/StatusChip'
import api from '../api/client'
import type { CompanyBrief } from '../api/types'

interface CompanyList {
  items: CompanyBrief[]
  total: number
  page: number
  page_size: number
}

function CompanyCard({ company, onClick }: { company: CompanyBrief; onClick: () => void }) {
  return (
    <Card
      sx={{
        height: '100%',
        transition: 'box-shadow 0.2s',
        '&:hover': { boxShadow: 4 },
      }}
    >
      <CardActionArea onClick={onClick}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="h6" noWrap sx={{ maxWidth: '70%' }}>
              {company.name || 'Unknown'}
            </Typography>
            <StatusChip status={company.status} />
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
            <Language fontSize="small" color="action" />
            <Typography variant="body2" color="text.secondary" noWrap>
              {company.url}
            </Typography>
          </Box>

          {company.team_url && (
            <Typography variant="caption" color="text.secondary" display="block" mb={1}>
              Team page: {company.team_url}
            </Typography>
          )}

          <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <People fontSize="small" color="primary" />
              <Typography variant="body2">{company.people_count} people</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {company.pages_scraped > 0
                ? `${company.pages_scraped} pages`
                : 'Source: LinkedIn'}
            </Typography>
          </Box>

          {company.error_message && (
            <Alert severity="error" sx={{ mt: 1, py: 0, fontSize: '0.75rem' }}>
              {company.error_message.substring(0, 100)}
            </Alert>
          )}
        </CardContent>
      </CardActionArea>
    </Card>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [companies, setCompanies] = useState<CompanyList | null>(null)
  const [activeCompanies, setActiveCompanies] = useState<CompanyBrief[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const pageSize = 24
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Fetch completed companies
  useEffect(() => {
    setLoading(true)
    api
      .get<CompanyList>('/companies', { params: { status: 'completed', page, page_size: pageSize } })
      .then(({ data }) => setCompanies(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [page])

  // Fetch and poll active companies
  useEffect(() => {
    const fetchActive = () => {
      api
        .get<CompanyList>('/companies', { params: { active: true, page_size: 100 } })
        .then(({ data }) => {
          setActiveCompanies(data.items)
          // If no active companies, stop polling and refresh completed list
          if (data.items.length === 0 && intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
            // Refresh completed companies
            api
              .get<CompanyList>('/companies', { params: { status: 'completed', page, page_size: pageSize } })
              .then(({ data }) => setCompanies(data))
              .catch(console.error)
          }
        })
        .catch(console.error)
    }

    fetchActive()
    intervalRef.current = setInterval(fetchActive, 10000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [page])

  if (loading && !companies) {
    return (
      <Box sx={{ textAlign: 'center', mt: 8 }}>
        <CircularProgress />
        <Typography mt={2}>Loading...</Typography>
      </Box>
    )
  }

  const hasCompleted = companies && companies.items.length > 0
  const hasActive = activeCompanies.length > 0

  if (!hasCompleted && !hasActive) {
    return (
      <Box sx={{ textAlign: 'center', mt: 8 }}>
        <Typography variant="h5" color="text.secondary">No companies yet</Typography>
        <Typography color="text.secondary" mt={1}>
          Upload a file with company URLs to get started.
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" fontWeight={600}>Dashboard</Typography>
      </Box>

      {/* Active / In-Progress Section */}
      {hasActive && (
        <Box sx={{ mb: 4 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>
              In Progress ({activeCompanies.length})
            </Typography>
            <CircularProgress size={16} />
          </Box>
          <Grid container spacing={2}>
            {activeCompanies.map((company) => (
              <Grid item xs={12} sm={6} md={4} key={company.id}>
                <Card sx={{ height: '100%', border: '1px solid', borderColor: 'warning.light' }}>
                  <LinearProgress
                    color="warning"
                    sx={{ height: 3 }}
                  />
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="h6" noWrap sx={{ maxWidth: '70%' }}>
                        {company.name || 'Unknown'}
                      </Typography>
                      <StatusChip status={company.status} />
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Language fontSize="small" color="action" />
                      <Typography variant="body2" color="text.secondary" noWrap>
                        {company.url}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* Completed Section */}
      {hasCompleted && (
        <>
          <Box sx={{ mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>
              Completed ({companies!.total})
            </Typography>
          </Box>

          <Grid container spacing={2}>
            {companies!.items.map((company) => (
              <Grid item xs={12} sm={6} md={4} key={company.id}>
                <CompanyCard
                  company={company}
                  onClick={() => navigate(`/companies/${company.id}`)}
                />
              </Grid>
            ))}
          </Grid>

          {companies!.total > pageSize && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={Math.ceil(companies!.total / pageSize)}
                page={page}
                onChange={(_, p) => setPage(p)}
                color="primary"
              />
            </Box>
          )}
        </>
      )}
    </Box>
  )
}
