import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Tabs, Tab, Button, CircularProgress, Breadcrumbs, Link,
} from '@mui/material'
import { ArrowBack } from '@mui/icons-material'
import StatusChip from '../components/StatusChip'
import ExportButton from '../components/ExportButton'
import PeopleTable from '../components/PeopleTable'
import SkillsMatrix from '../components/SkillsMatrix'
import { useCompany } from '../api/hooks'

export default function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)

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
            {company.people_count} people | {company.pages_scraped} pages scraped
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

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label={`People (${company.people_count})`} />
        <Tab label="Skills Matrix" />
      </Tabs>

      {tab === 0 && <PeopleTable companyId={companyId!} />}
      {tab === 1 && <SkillsMatrix companyId={companyId!} />}
    </Box>
  )
}
