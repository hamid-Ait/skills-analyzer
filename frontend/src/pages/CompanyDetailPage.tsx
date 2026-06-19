import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Tabs, Tab, Button, CircularProgress, Breadcrumbs, Link,
  ToggleButtonGroup, ToggleButton, TextField, Pagination,
  Menu, MenuItem, ListItemIcon, ListItemText, Snackbar, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select,
} from '@mui/material'
import { ArrowBack, ViewList, ViewModule, Refresh, RestartAlt, Psychology, LinkedIn, AutoFixHigh, Warning, PlayArrow } from '@mui/icons-material'
import api from '../api/client'
import StatusChip from '../components/StatusChip'
import ExportButton from '../components/ExportButton'
import PeopleTable from '../components/PeopleTable'
import PeopleCards from '../components/PeopleCards'
import SkillsMatrix from '../components/SkillsMatrix'
import { useCompany, usePeople, useProviders } from '../api/hooks'

function PeopleCardView({ companyId }: { companyId: string }) {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const pageSize = 48

  const { data, loading } = usePeople(companyId, page, pageSize, search)

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        <TextField
          size="small"
          placeholder="Search by name or title..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          sx={{ width: 300 }}
        />
      </Box>
      {loading ? (
        <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress /></Box>
      ) : (
        <>
          <PeopleCards people={data?.items || []} companyId={companyId} />
          {data && data.total > pageSize && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={Math.ceil(data.total / pageSize)}
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

export default function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table')

  const { company, loading } = useCompany(companyId || null)
  const providerList = useProviders()
  const [retryAnchor, setRetryAnchor] = useState<null | HTMLElement>(null)
  const [retryLoading, setRetryLoading] = useState(false)
  const [snack, setSnack] = useState<{ msg: string; severity: 'success' | 'error' } | null>(null)
  const [confirmMode, setConfirmMode] = useState<string | null>(null)
  const [reanalyzeOpen, setReanalyzeOpen] = useState(false)
  const [reanalyzeProvider, setReanalyzeProvider] = useState('')
  const [reanalyzeModel, setReanalyzeModel] = useState('')

  useEffect(() => {
    if (providerList.length > 0 && !reanalyzeProvider) {
      const first = providerList[0]
      setReanalyzeProvider(first.provider)
      setReanalyzeModel(first.default_model ?? '')
    }
  }, [providerList])

  useEffect(() => {
    const info = providerList.find((p) => p.provider === reanalyzeProvider)
    setReanalyzeModel(info?.default_model ?? '')
  }, [reanalyzeProvider])

  const doRetry = async (mode: string, extra?: { provider?: string; model?: string }) => {
    setRetryLoading(true)
    try {
      const { data } = await api.post(`/companies/${companyId}/retry`, { mode, ...extra })
      setSnack({ msg: data.message, severity: 'success' })
    } catch (err: any) {
      setSnack({ msg: err.response?.data?.detail || 'Retry failed', severity: 'error' })
    } finally {
      setRetryLoading(false)
    }
  }

  const handleRetry = (mode: string) => {
    setRetryAnchor(null)
    if (mode === 'rescrape') {
      setConfirmMode(mode)
    } else if (mode === 'reanalyze') {
      setReanalyzeOpen(true)
    } else {
      doRetry(mode)
    }
  }

  if (loading || !company) {
    return (
      <Box sx={{ textAlign: 'center', mt: 8 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link
          component="button"
          underline="hover"
          onClick={() => navigate('/dashboard')}
          sx={{ cursor: 'pointer' }}
        >
          Dashboard
        </Link>
        <Typography color="text.primary">{company.name}</Typography>
      </Breadcrumbs>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
            <Typography variant="h4" fontWeight={600}>
              {company.name}
            </Typography>
            <StatusChip status={company.status} />
          </Box>
          <Typography variant="body2" color="text.secondary">
            {company.url}
            {company.team_url && ` | Team: ${company.team_url}`}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {company.people_count} people |   {company.pages_scraped > 0
              ? `${company.pages_scraped} pages`
              : 'Source: LinkedIn'}
            {company.waf_detected && ` | WAF: ${company.waf_name}`}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<ArrowBack />}
            onClick={() => navigate('/dashboard')}
          >
            Back
          </Button>
          <Button
            variant="outlined"
            color="warning"
            startIcon={retryLoading ? <CircularProgress size={16} /> : <Refresh />}
            onClick={(e) => setRetryAnchor(e.currentTarget)}
            disabled={retryLoading}
          >
            Retry
          </Button>
          <Menu anchorEl={retryAnchor} open={Boolean(retryAnchor)} onClose={() => setRetryAnchor(null)}>
            <MenuItem onClick={() => handleRetry('resume')}>
              <ListItemIcon><PlayArrow fontSize="small" /></ListItemIcon>
              <ListItemText primary="Resume scraping" secondary="Continue from where it stopped" />
            </MenuItem>
            <MenuItem onClick={() => handleRetry('rescrape')}>
              <ListItemIcon><RestartAlt fontSize="small" /></ListItemIcon>
              <ListItemText primary="Refresh" secondary="Delete people & start fresh" />
            </MenuItem>
            <MenuItem onClick={() => handleRetry('analyze_missing')}>
              <ListItemIcon><AutoFixHigh fontSize="small" /></ListItemIcon>
              <ListItemText primary="Analyze missing" secondary="Only unanalyzed profiles" />
            </MenuItem>
            <MenuItem onClick={() => handleRetry('reanalyze')}>
              <ListItemIcon><Psychology fontSize="small" /></ListItemIcon>
              <ListItemText primary="Re-analyze all" secondary="Clear & redo all expertise analysis" />
            </MenuItem>
            <MenuItem onClick={() => handleRetry('reenrich')}>
              <ListItemIcon><LinkedIn fontSize="small" /></ListItemIcon>
              <ListItemText primary="Re-enrich" secondary="Re-run LinkedIn + analysis" />
            </MenuItem>
          </Menu>
          <ExportButton companyId={companyId!} />
        </Box>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label={`People (${company.people_count})`} />
          <Tab label="Skills Matrix" />
        </Tabs>

        {tab === 0 && (
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, v) => v && setViewMode(v)}
            size="small"
          >
            <ToggleButton value="table">
              <ViewList fontSize="small" />
            </ToggleButton>
            <ToggleButton value="cards">
              <ViewModule fontSize="small" />
            </ToggleButton>
          </ToggleButtonGroup>
        )}
      </Box>

      {tab === 0 && viewMode === 'table' && <PeopleTable companyId={companyId!} />}
      {tab === 0 && viewMode === 'cards' && <PeopleCardView companyId={companyId!} />}
      {tab === 1 && <SkillsMatrix companyId={companyId!} />}

      <Snackbar
        open={Boolean(snack)}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snack?.severity} onClose={() => setSnack(null)} variant="filled">
          {snack?.msg}
        </Alert>
      </Snackbar>

      {/* Re-scrape confirmation dialog */}
      <Dialog open={confirmMode === 'rescrape'} onClose={() => setConfirmMode(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Warning color="warning" />
          Refresh {company?.name || 'company'}?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            This will delete all {company?.people_count || 0} existing people and their
            expertise analysis, then scrape the company from scratch.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmMode(null)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => { setConfirmMode(null); doRetry('rescrape') }}
          >
            Refresh
          </Button>
        </DialogActions>
      </Dialog>

      {/* Re-analyze with LLM selector dialog */}
      <Dialog open={reanalyzeOpen} onClose={() => setReanalyzeOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Psychology color="primary" />
          Re-analyze all profiles
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Choose the LLM to use for expertise classification of all {company?.people_count || 0} profiles.
            Existing analysis will be cleared.
          </Typography>
          <FormControl fullWidth size="small">
            <InputLabel>Provider</InputLabel>
            <Select
              value={reanalyzeProvider}
              label="Provider"
              onChange={(e) => setReanalyzeProvider(e.target.value)}
            >
              {providerList.map((p) => (
                <MenuItem key={p.provider} value={p.provider}>{p.provider}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Model (optional)"
            value={reanalyzeModel}
            onChange={(e) => setReanalyzeModel(e.target.value)}
            helperText="Leave as default or enter a specific model name"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReanalyzeOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              setReanalyzeOpen(false)
              doRetry('reanalyze', { provider: reanalyzeProvider, model: reanalyzeModel || undefined })
            }}
          >
            Re-analyze
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}