import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Tabs, Tab, Button, CircularProgress, Breadcrumbs, Link,
  ToggleButtonGroup, ToggleButton, TextField, Pagination,
  Menu, MenuItem, ListItemIcon, ListItemText, Snackbar, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material'
import { ArrowBack, ViewList, ViewModule, Refresh, RestartAlt, Psychology, LinkedIn, AutoFixHigh, Warning } from '@mui/icons-material'
import api from '../api/client'
import StatusChip from '../components/StatusChip'
import ExportButton from '../components/ExportButton'
import PeopleTable from '../components/PeopleTable'
import PeopleCards from '../components/PeopleCards'
import SkillsMatrix from '../components/SkillsMatrix'
import PersonDetailModal from '../components/PersonDetailModal'
import { useCompany, usePeople } from '../api/hooks'

function PeopleCardView({ companyId }: { companyId: string }) {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)
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
          <PeopleCards
            people={data?.items || []}
            onPersonClick={(id) => setSelectedPersonId(id)}
          />
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
      <PersonDetailModal
        personId={selectedPersonId}
        onClose={() => setSelectedPersonId(null)}
      />
    </Box>
  )
}

export default function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table')

  const { company, loading } = useCompany(companyId || null)
  const [retryAnchor, setRetryAnchor] = useState<null | HTMLElement>(null)
  const [retryLoading, setRetryLoading] = useState(false)
  const [snack, setSnack] = useState<{ msg: string; severity: 'success' | 'error' } | null>(null)
  const [confirmMode, setConfirmMode] = useState<string | null>(null)

  const doRetry = async (mode: string) => {
    setRetryLoading(true)
    try {
      const { data } = await api.post(`/companies/${companyId}/retry`, { mode })
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
    </Box>
  )
}