import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, TextField, InputAdornment, Chip, Avatar,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Pagination, CircularProgress, FormControl, InputLabel,
  Select, MenuItem, Grid,
} from '@mui/material'
import { Search, LinkedIn } from '@mui/icons-material'
import { useGlobalSearch } from '../api/hooks'
import { proxyImageUrl } from '../api/client'

const CATEGORIES = [
  'Revenue Growth', 'Operational Improvements', 'Finance and Accounting',
  'Marketing', 'People and Talent', 'Technology',
  'M&A and Corporate Development', 'Real Estate & Assets', 'R&D',
  'Environment (ESG)', 'Governance (ESG)', 'Social (ESG)', 'Legal',
]

export default function GlobalSearchPage() {
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [sector, setSector] = useState('')
  const [geography, setGeography] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 25

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(searchInput)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data, loading } = useGlobalSearch(q, category, sector, geography, page, pageSize)

  const totalPages = useMemo(() => {
    if (!data) return 0
    return Math.ceil(data.total / pageSize)
  }, [data])

  return (
    <Box>
      <Typography variant="h4" fontWeight={600} mb={3}>Global People Search</Typography>

      {/* Search & Filters */}
      <Paper sx={{ p: 2, mb: 3 }} elevation={1}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              placeholder="Search by name, title, or expertise..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={4} md={2.5}>
            <FormControl fullWidth size="small">
              <InputLabel>Category</InputLabel>
              <Select
                value={category}
                label="Category"
                onChange={(e) => { setCategory(e.target.value); setPage(1) }}
              >
                <MenuItem value="">All Categories</MenuItem>
                {CATEGORIES.map((c) => (
                  <MenuItem key={c} value={c}>{c}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4} md={2.5}>
            <TextField
              fullWidth
              label="Sector"
              placeholder="e.g. Healthcare"
              value={sector}
              onChange={(e) => { setSector(e.target.value); setPage(1) }}
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={4} md={2.5}>
            <TextField
              fullWidth
              label="Geography"
              placeholder="e.g. Europe"
              value={geography}
              onChange={(e) => { setGeography(e.target.value); setPage(1) }}
              size="small"
            />
          </Grid>
        </Grid>
      </Paper>

      {/* Results count */}
      {data && (
        <Typography variant="body2" color="text.secondary" mb={2}>
          {data.total.toLocaleString()} result{data.total !== 1 ? 's' : ''} found
        </Typography>
      )}

      {/* Loading */}
      {loading && (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {/* Results table */}
      {data && !loading && (
        <>
          <TableContainer component={Paper} elevation={1}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell></TableCell>
                  <TableCell><strong>Name</strong></TableCell>
                  <TableCell><strong>Title</strong></TableCell>
                  <TableCell><strong>Company</strong></TableCell>
                  <TableCell><strong>Primary Expertise</strong></TableCell>
                  <TableCell><strong>Sector</strong></TableCell>
                  <TableCell><strong>Geography</strong></TableCell>
                  <TableCell><strong>Categories</strong></TableCell>
                  <TableCell></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((person) => (
                  <TableRow
                    key={person.id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/companies/${person.company_id}`)}
                  >
                    <TableCell sx={{ width: 40 }}>
                      <Avatar
                        src={proxyImageUrl(person.image_url)}
                        sx={{ width: 32, height: 32 }}
                      >
                        {person.name.charAt(0)}
                      </Avatar>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight={500}>{person.name}</Typography>
                      {person.location && (
                        <Typography variant="caption" color="text.secondary">{person.location}</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{person.title || '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="primary">{person.company_name || '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{person.primary_expertise || '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{person.sector || '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{person.geography || '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {(person.matched_13_categories || []).slice(0, 2).map((cat) => (
                          <Chip key={cat} label={cat} size="small" variant="outlined" sx={{ fontSize: '0.65rem', height: 20 }} />
                        ))}
                        {(person.matched_13_categories || []).length > 2 && (
                          <Chip label={`+${person.matched_13_categories!.length - 2}`} size="small" sx={{ fontSize: '0.65rem', height: 20 }} />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {person.linkedin_url && (
                        <LinkedIn
                          fontSize="small"
                          sx={{ color: '#0077b5', cursor: 'pointer' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            window.open(person.linkedin_url!, '_blank')
                          }}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                      <Typography color="text.secondary">No results found</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>

          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={totalPages}
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