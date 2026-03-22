import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Paper, Grid, CircularProgress, LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Tabs, Tab, Tooltip,
} from '@mui/material'
import {
  Business, People, Analytics, LinkedIn, PhotoCamera,
  AttachMoney, Token,
} from '@mui/icons-material'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
  LineChart, Line,
} from 'recharts'
import { useAnalyticsOverview, useHeatmap, useCostSummary } from '../api/hooks'
import type { CompanyStat } from '../api/types'

const COLORS = [
  '#1976d2', '#7c4dff', '#00bcd4', '#4caf50', '#ff9800',
  '#f44336', '#9c27b0', '#3f51b5', '#009688', '#ff5722',
  '#607d8b', '#795548', '#e91e63',
]

function StatCard({ icon, label, value, subtitle, color }: {
  icon: React.ReactNode; label: string; value: number | string;
  subtitle?: string; color: string;
}) {
  return (
    <Paper sx={{ p: 2.5, textAlign: 'center', height: '100%' }} elevation={2}>
      <Box sx={{ color, mb: 1 }}>{icon}</Box>
      <Typography variant="h4" fontWeight={700}>{value}</Typography>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      {subtitle && (
        <Typography variant="caption" color="text.secondary">{subtitle}</Typography>
      )}
    </Paper>
  )
}

function completenessColor(pct: number) {
  if (pct >= 80) return 'success' as const
  if (pct >= 50) return 'warning' as const
  return 'error' as const
}

function CompletenessTable({ stats }: { stats: CompanyStat[] }) {
  const navigate = useNavigate()

  // Sort by worst completeness first
  const sorted = [...stats].sort((a, b) => {
    const aScore = a.people_count > 0
      ? (a.analyzed_count + a.linkedin_enriched_count + a.photo_count) / (a.people_count * 3) * 100
      : 0
    const bScore = b.people_count > 0
      ? (b.analyzed_count + b.linkedin_enriched_count + b.photo_count) / (b.people_count * 3) * 100
      : 0
    return aScore - bScore
  })

  return (
    <TableContainer component={Paper} elevation={1}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell><strong>Company</strong></TableCell>
            <TableCell align="center"><strong>People</strong></TableCell>
            <TableCell><strong>Analyzed</strong></TableCell>
            <TableCell><strong>LinkedIn Enriched</strong></TableCell>
            <TableCell><strong>With Photo</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sorted.map((c) => {
            const pctAnalyzed = c.people_count > 0 ? Math.round(c.analyzed_count / c.people_count * 100) : 0
            const pctLinkedin = c.people_count > 0 ? Math.round(c.linkedin_enriched_count / c.people_count * 100) : 0
            const pctPhoto = c.people_count > 0 ? Math.round(c.photo_count / c.people_count * 100) : 0
            return (
              <TableRow
                key={c.id}
                hover
                sx={{ cursor: 'pointer' }}
                onClick={() => navigate(`/companies/${c.id}`)}
              >
                <TableCell>
                  <Typography variant="body2" fontWeight={500}>{c.name || c.url}</Typography>
                </TableCell>
                <TableCell align="center">{c.people_count}</TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={pctAnalyzed}
                        color={completenessColor(pctAnalyzed)}
                        sx={{ height: 8, borderRadius: 4 }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ minWidth: 35 }}>{pctAnalyzed}%</Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={pctLinkedin}
                        color={completenessColor(pctLinkedin)}
                        sx={{ height: 8, borderRadius: 4 }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ minWidth: 35 }}>{pctLinkedin}%</Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={pctPhoto}
                        color={completenessColor(pctPhoto)}
                        sx={{ height: 8, borderRadius: 4 }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ minWidth: 35 }}>{pctPhoto}%</Typography>
                  </Box>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

function HeatmapTab() {
  const navigate = useNavigate()
  const { data, loading } = useHeatmap()

  if (loading) return <CircularProgress />
  if (!data || data.companies.length === 0) {
    return <Typography color="text.secondary">No heatmap data available</Typography>
  }

  const maxCount = Math.max(
    ...data.companies.flatMap((c) => Object.values(c.categories)),
    1,
  )

  const cellBg = (count: number) => {
    if (count === 0) return 'transparent'
    const intensity = Math.min(count / maxCount, 1)
    const alpha = 0.15 + intensity * 0.7
    return `rgba(25, 118, 210, ${alpha})`
  }

  return (
    <TableContainer component={Paper} elevation={1} sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700, position: 'sticky', left: 0, bgcolor: 'background.paper', zIndex: 2, minWidth: 180 }}>
              Company
            </TableCell>
            {data.category_names.map((cat) => (
              <TableCell
                key={cat}
                align="center"
                sx={{ fontWeight: 600, fontSize: '0.7rem', whiteSpace: 'nowrap', writingMode: 'vertical-lr', transform: 'rotate(180deg)', minWidth: 40, py: 2 }}
              >
                {cat}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {data.companies.map((company) => (
            <TableRow
              key={company.id}
              hover
              sx={{ cursor: 'pointer' }}
              onClick={() => navigate(`/companies/${company.id}`)}
            >
              <TableCell sx={{ fontWeight: 500, position: 'sticky', left: 0, bgcolor: 'background.paper', zIndex: 1 }}>
                {company.name || 'Unknown'}
              </TableCell>
              {data.category_names.map((cat) => {
                const count = company.categories[cat] || 0
                return (
                  <Tooltip key={cat} title={`${company.name}: ${count} in ${cat}`}>
                    <TableCell
                      align="center"
                      sx={{
                        bgcolor: cellBg(count),
                        fontWeight: count > 0 ? 600 : 400,
                        color: count > 0 ? 'text.primary' : 'text.disabled',
                        fontSize: '0.8rem',
                      }}
                    >
                      {count || ''}
                    </TableCell>
                  </Tooltip>
                )
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

const COST_COLORS = ['#4caf50', '#1976d2', '#ff9800', '#f44336', '#9c27b0', '#00bcd4', '#795548']

function formatUsd(value: number) {
  if (value >= 1) return `$${value.toFixed(2)}`
  if (value >= 0.01) return `$${value.toFixed(4)}`
  return `$${value.toFixed(6)}`
}

function CostsTab() {
  const { data, loading } = useCostSummary(30)

  if (loading) return <CircularProgress />
  if (!data || data.total_cost_usd === 0) {
    return <Typography color="text.secondary">No cost data available yet. Costs will appear after processing companies.</Typography>
  }

  const llmCost = data.cost_by_service.find(s => s.service === 'llm')?.cost || 0
  const apifyCost = data.cost_by_service.find(s => s.service === 'apify')?.cost || 0

  return (
    <Box>
      {/* Stat cards */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard icon={<AttachMoney fontSize="large" />} label="Total Cost (30d)" value={formatUsd(data.total_cost_usd)} color="#4caf50" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard icon={<AttachMoney fontSize="large" />} label="LLM Cost" value={formatUsd(llmCost)} color="#1976d2" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard icon={<AttachMoney fontSize="large" />} label="Apify Cost" value={formatUsd(apifyCost)} color="#ff9800" />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard icon={<Token fontSize="large" />} label="Total Tokens" value={(data.token_totals.input_tokens + data.token_totals.output_tokens).toLocaleString()} subtitle={`In: ${data.token_totals.input_tokens.toLocaleString()} / Out: ${data.token_totals.output_tokens.toLocaleString()}`} color="#9c27b0" />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Cost by pipeline step */}
        {data.cost_by_step.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="h6" fontWeight={600} gutterBottom>Cost by Pipeline Step</Typography>
            <Box sx={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <BarChart data={data.cost_by_step} layout="vertical" margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(v) => `$${v.toFixed(4)}`} />
                  <YAxis type="category" dataKey="step" width={110} tick={{ fontSize: 12 }} />
                  <RechartsTooltip formatter={(value: number) => [formatUsd(value), 'Cost']} />
                  <Bar dataKey="cost" fill="#1976d2" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Grid>
        )}

        {/* Cost by provider (pie) */}
        {data.cost_by_provider.length > 0 && (
          <Grid item xs={12} md={6}>
            <Typography variant="h6" fontWeight={600} gutterBottom>Cost by Provider</Typography>
            <Box sx={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={data.cost_by_provider}
                    dataKey="cost"
                    nameKey="provider"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ provider, percent }) => `${provider} (${(percent * 100).toFixed(0)}%)`}
                  >
                    {data.cost_by_provider.map((_, index) => (
                      <Cell key={index} fill={COST_COLORS[index % COST_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip formatter={(value: number) => [formatUsd(value), 'Cost']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </Box>
          </Grid>
        )}
      </Grid>

      {/* Daily cost trend */}
      {data.cost_over_time.length > 1 && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" fontWeight={600} gutterBottom>Daily Cost Trend</Typography>
          <Box sx={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={data.cost_over_time} margin={{ top: 5, right: 30, left: 60, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => `$${v.toFixed(4)}`} />
                <RechartsTooltip formatter={(value: number) => [formatUsd(value), 'Cost']} />
                <Line type="monotone" dataKey="cost" stroke="#1976d2" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </Box>
        </Box>
      )}

      {/* Cost per company table */}
      {data.cost_by_company.length > 0 && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" fontWeight={600} gutterBottom>Cost by Company</Typography>
          <TableContainer component={Paper} elevation={1}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><strong>Company</strong></TableCell>
                  <TableCell align="right"><strong>Cost (USD)</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.cost_by_company.map((c) => (
                  <TableRow key={c.company_id}>
                    <TableCell>{c.company_name || c.company_id}</TableCell>
                    <TableCell align="right">{formatUsd(c.cost)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}
    </Box>
  )
}

export default function AnalyticsPage() {
  const { data, loading } = useAnalyticsOverview()
  const [tab, setTab] = useState(0)

  if (loading) {
    return (
      <Box sx={{ textAlign: 'center', mt: 8 }}>
        <CircularProgress />
        <Typography mt={2}>Loading analytics...</Typography>
      </Box>
    )
  }

  if (!data || data.total_companies === 0) {
    return (
      <Box sx={{ textAlign: 'center', mt: 8 }}>
        <Typography variant="h5" color="text.secondary">No completed companies yet</Typography>
        <Typography color="text.secondary" mt={1}>
          Analytics will appear once companies finish processing.
        </Typography>
      </Box>
    )
  }

  const pctAnalyzed = data.total_people > 0 ? Math.round(data.total_analyzed / data.total_people * 100) : 0
  const pctLinkedin = data.total_people > 0 ? Math.round(data.total_linkedin_enriched / data.total_people * 100) : 0
  const pctPhoto = data.total_people > 0 ? Math.round(data.total_with_photo / data.total_people * 100) : 0

  return (
    <Box>
      <Typography variant="h4" fontWeight={600} mb={3}>Cross-Company Analytics</Typography>

      {/* Summary Stats */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatCard icon={<Business fontSize="large" />} label="Companies" value={data.total_companies} color="#1976d2" />
        </Grid>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatCard icon={<People fontSize="large" />} label="Total People" value={data.total_people.toLocaleString()} color="#7c4dff" />
        </Grid>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatCard icon={<Analytics fontSize="large" />} label="Analyzed" value={data.total_analyzed.toLocaleString()} subtitle={`${pctAnalyzed}%`} color="#4caf50" />
        </Grid>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatCard icon={<LinkedIn fontSize="large" />} label="LinkedIn Enriched" value={data.total_linkedin_enriched.toLocaleString()} subtitle={`${pctLinkedin}%`} color="#0077b5" />
        </Grid>
        <Grid item xs={12} sm={6} md={2.4}>
          <StatCard icon={<PhotoCamera fontSize="large" />} label="With Photo" value={data.total_with_photo.toLocaleString()} subtitle={`${pctPhoto}%`} color="#ff9800" />
        </Grid>
      </Grid>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Data Completeness" />
        <Tab label="Expertise Heatmap" />
        <Tab label="Charts" />
        <Tab label="Costs" />
      </Tabs>

      {/* Tab 0: Data Completeness */}
      {tab === 0 && (
        <Box>
          <Typography variant="h6" fontWeight={600} mb={2}>Data Completeness by Company</Typography>
          <CompletenessTable stats={data.company_stats} />
        </Box>
      )}

      {/* Tab 1: Heatmap */}
      {tab === 1 && (
        <Box>
          <Typography variant="h6" fontWeight={600} mb={2}>
            Expertise Heatmap (Companies x Categories)
          </Typography>
          <HeatmapTab />
        </Box>
      )}

      {/* Tab 2: Charts */}
      {tab === 2 && (
        <Box>
          {/* Categories */}
          <Typography variant="h6" fontWeight={600} gutterBottom>Expertise Categories (All Companies)</Typography>
          <Box sx={{ width: '100%', height: 400, mb: 4 }}>
            <ResponsiveContainer>
              <BarChart data={data.categories} layout="vertical" margin={{ top: 5, right: 30, left: 180, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={170} tick={{ fontSize: 12 }} />
                <RechartsTooltip formatter={(value: number) => [value, 'People']} />
                <Bar dataKey="count" fill="#1976d2" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Box>

          {/* Top Expertise Pie */}
          {data.top_expertise.length > 0 && (
            <>
              <Typography variant="h6" fontWeight={600} gutterBottom>Top Primary Expertise</Typography>
              <Box sx={{ width: '100%', height: 400, mb: 4 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={data.top_expertise.slice(0, 10)}
                      dataKey="count"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={140}
                      label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    >
                      {data.top_expertise.slice(0, 10).map((_, index) => (
                        <Cell key={index} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </>
          )}

          {/* Sectors and Geographies side by side */}
          <Grid container spacing={3}>
            {data.sectors.length > 0 && (
              <Grid item xs={12} md={6}>
                <Typography variant="h6" fontWeight={600} gutterBottom>Sectors</Typography>
                <Box sx={{ width: '100%', height: 350 }}>
                  <ResponsiveContainer>
                    <BarChart data={data.sectors} layout="vertical" margin={{ top: 5, right: 20, left: 120, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
                      <RechartsTooltip />
                      <Bar dataKey="count" fill="#7c4dff" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
              </Grid>
            )}
            {data.geographies.length > 0 && (
              <Grid item xs={12} md={6}>
                <Typography variant="h6" fontWeight={600} gutterBottom>Geographies</Typography>
                <Box sx={{ width: '100%', height: 350 }}>
                  <ResponsiveContainer>
                    <BarChart data={data.geographies} layout="vertical" margin={{ top: 5, right: 20, left: 120, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
                      <RechartsTooltip />
                      <Bar dataKey="count" fill="#00bcd4" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
              </Grid>
            )}
          </Grid>
        </Box>
      )}

      {/* Tab 3: Costs */}
      {tab === 3 && (
        <Box>
          <Typography variant="h6" fontWeight={600} mb={2}>Cost Monitoring (Last 30 Days)</Typography>
          <CostsTab />
        </Box>
      )}
    </Box>
  )
}