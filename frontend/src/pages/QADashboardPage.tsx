import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Card, CardContent, Grid, Chip, CircularProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Select, MenuItem, FormControl, InputLabel, TablePagination,
  Collapse, IconButton, Tooltip, Stack, Button, Snackbar, Alert,
} from '@mui/material'
import { CheckCircle, Error, Warning, KeyboardArrowDown, KeyboardArrowUp, Refresh } from '@mui/icons-material'
import { useQASummary, useQAIssues, qaReanalyze } from '../api/hooks'
import type { QAIssueItem } from '../api/types'

const ISSUE_TYPE_LABELS: Record<string, string> = {
  taxonomy_violation: 'Taxonomy Violation',
  count_violation: 'Count Violation',
  verbatim_copy: 'Verbatim Copy (L2)',
  consistency: 'Consistency',
  missing_fields: 'Missing Fields',
  other: 'Other',
}

const STATUS_COLORS = {
  failed: 'error',
  flagged: 'warning',
  clean: 'success',
} as const

function StatCard({
  label,
  value,
  color,
  icon,
}: {
  label: string
  value: number
  color: string
  icon: React.ReactNode
}) {
  return (
    <Card variant="outlined" sx={{ borderColor: `${color}.main` }}>
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Box sx={{ color: `${color}.main` }}>{icon}</Box>
        <Box>
          <Typography variant="h4" fontWeight={700} color={`${color}.main`}>
            {value}
          </Typography>
          <Typography variant="body2" color="text.secondary">{label}</Typography>
        </Box>
      </CardContent>
    </Card>
  )
}

function IssueRow({ item }: { item: QAIssueItem }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const hasIssues = item.hard_failures.length + item.soft_warnings.length > 0

  return (
    <>
      <TableRow
        hover
        sx={{ cursor: hasIssues ? 'pointer' : 'default', '& > *': { borderBottom: 'unset' } }}
        onClick={() => hasIssues && setOpen((v) => !v)}
      >
        <TableCell>
          {hasIssues ? (
            <IconButton size="small">
              {open ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
            </IconButton>
          ) : null}
        </TableCell>
        <TableCell>
          <Typography
            variant="body2"
            fontWeight={500}
            sx={{ cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
            onClick={(e) => { e.stopPropagation(); navigate(`/people/${item.person_id}`) }}
          >
            {item.person_name}
          </Typography>
        </TableCell>
        <TableCell>
          <Typography
            variant="body2"
            sx={{ cursor: 'pointer', color: 'text.secondary', '&:hover': { textDecoration: 'underline' } }}
            onClick={(e) => { e.stopPropagation(); navigate(`/companies/${item.company_id}`) }}
          >
            {item.company_name ?? '—'}
          </Typography>
        </TableCell>
        <TableCell>
          <Chip
            size="small"
            label={item.status.charAt(0).toUpperCase() + item.status.slice(1)}
            color={STATUS_COLORS[item.status]}
          />
        </TableCell>
        <TableCell>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {item.hard_failures.map((msg, i) => (
              <Tooltip key={i} title={msg}>
                <Chip size="small" label={ISSUE_TYPE_LABELS[categorizeIssue(msg)] ?? 'Other'} color="error" variant="outlined" />
              </Tooltip>
            ))}
            {item.soft_warnings.map((msg, i) => (
              <Tooltip key={i} title={msg}>
                <Chip size="small" label={ISSUE_TYPE_LABELS[categorizeIssue(msg)] ?? 'Other'} color="warning" variant="outlined" />
              </Tooltip>
            ))}
          </Stack>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={5} sx={{ py: 0 }}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ py: 1.5, px: 2 }}>
              {item.hard_failures.length > 0 && (
                <Box mb={1}>
                  <Typography variant="caption" fontWeight={700} color="error.main">
                    Hard Failures
                  </Typography>
                  {item.hard_failures.map((msg, i) => (
                    <Typography key={i} variant="body2" color="error.main" sx={{ pl: 1 }}>
                      • {msg}
                    </Typography>
                  ))}
                </Box>
              )}
              {item.soft_warnings.length > 0 && (
                <Box>
                  <Typography variant="caption" fontWeight={700} color="warning.main">
                    Soft Warnings
                  </Typography>
                  {item.soft_warnings.map((msg, i) => (
                    <Typography key={i} variant="body2" color="warning.main" sx={{ pl: 1 }}>
                      • {msg}
                    </Typography>
                  ))}
                </Box>
              )}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  )
}

function categorizeIssue(msg: string): string {
  const m = msg.toLowerCase()
  if (m.includes('not a valid taxonomy') || m.includes('invalid values')) return 'taxonomy_violation'
  if (m.includes('items (max')) return 'count_violation'
  if (m.includes('verbatim')) return 'verbatim_copy'
  if (m.includes('evidence_map') || m.includes('not committed') || m.includes('not present in')) return 'consistency'
  if (m.includes('empty') || m.includes('not set')) return 'missing_fields'
  return 'other'
}

export default function QADashboardPage() {
  const [statusFilter, setStatusFilter] = useState('')
  const [issueTypeFilter, setIssueTypeFilter] = useState('')
  const [page, setPage] = useState(0)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>({
    open: false, message: '', severity: 'success',
  })
  const pageSize = 50

  const { data: summary, loading: summaryLoading } = useQASummary()
  const { data: issues, loading: issuesLoading, refresh } = useQAIssues(
    undefined,
    statusFilter || undefined,
    issueTypeFilter || undefined,
    page + 1,
    pageSize,
  )

  const handleStatusChange = (val: string) => { setStatusFilter(val); setPage(0) }
  const handleIssueTypeChange = (val: string) => { setIssueTypeFilter(val); setPage(0) }

  const canReanalyze = !!(statusFilter || issueTypeFilter)

  const handleReanalyze = async () => {
    if (!canReanalyze) return
    setReanalyzing(true)
    try {
      const result = await qaReanalyze({
        status: statusFilter || undefined,
        issue_type: issueTypeFilter || undefined,
      })
      setSnackbar({
        open: true,
        message: `Queued ${result.queued} profile(s) across ${result.companies.length} company(s) for re-analysis.`,
        severity: 'success',
      })
      refresh()
    } catch {
      setSnackbar({ open: true, message: 'Failed to queue re-analysis.', severity: 'error' })
    } finally {
      setReanalyzing(false)
    }
  }

  return (
    <Box>
      <Typography variant="h5" fontWeight={600} mb={3}>
        QA Dashboard
      </Typography>

      {/* Summary cards */}
      {summaryLoading ? (
        <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
      ) : summary ? (
        <Grid container spacing={2} mb={4}>
          <Grid item xs={6} sm={3}>
            <StatCard label="Analyzed" value={summary.total_analyzed} color="info" icon={<CheckCircle />} />
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard label="Failed" value={summary.total_failed} color="error" icon={<Error />} />
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard label="Flagged" value={summary.total_flagged} color="warning" icon={<Warning />} />
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard label="Clean" value={summary.total_clean} color="success" icon={<CheckCircle />} />
          </Grid>
        </Grid>
      ) : null}

      {/* Filters */}
      <Stack direction="row" spacing={2} mb={3} alignItems="center">
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => handleStatusChange(e.target.value)}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="failed">Failed</MenuItem>
            <MenuItem value="flagged">Flagged</MenuItem>
            <MenuItem value="clean">Clean</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Issue Type</InputLabel>
          <Select
            value={issueTypeFilter}
            label="Issue Type"
            onChange={(e) => handleIssueTypeChange(e.target.value)}
          >
            <MenuItem value="">All</MenuItem>
            {Object.entries(ISSUE_TYPE_LABELS).map(([key, label]) => (
              <MenuItem key={key} value={key}>{label}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Tooltip title={canReanalyze ? `Re-analyze all ${issues?.total ?? ''} matching profiles` : 'Select a status or issue type filter first'}>
          <span>
            <Button
              variant="contained"
              color="warning"
              startIcon={reanalyzing ? <CircularProgress size={16} color="inherit" /> : <Refresh />}
              disabled={!canReanalyze || reanalyzing}
              onClick={handleReanalyze}
            >
              Re-analyze All
            </Button>
          </span>
        </Tooltip>
      </Stack>

      {/* Issues table */}
      {issuesLoading ? (
        <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
      ) : (
        <Paper variant="outlined">
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: 'action.hover' }}>
                  <TableCell width={40} />
                  <TableCell>Name</TableCell>
                  <TableCell>Company</TableCell>
                  <TableCell width={100}>Status</TableCell>
                  <TableCell>Issues</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {issues?.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      No issues found
                    </TableCell>
                  </TableRow>
                ) : (
                  issues?.items.map((item) => (
                    <IssueRow key={item.person_id} item={item} />
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={issues?.total ?? 0}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={pageSize}
            rowsPerPageOptions={[pageSize]}
          />
        </Paper>
      )}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar((s) => ({ ...s, open: false }))}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  )
}