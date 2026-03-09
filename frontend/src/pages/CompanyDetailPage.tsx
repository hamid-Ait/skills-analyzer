import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Tabs, Tab, Button, CircularProgress, Breadcrumbs, Link,
  ToggleButtonGroup, ToggleButton, TextField, Pagination,
} from '@mui/material'
import { ArrowBack, ViewList, ViewModule } from '@mui/icons-material'
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
    </Box>
  )
}