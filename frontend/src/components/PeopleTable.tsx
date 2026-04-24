import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, TextField, Chip, Avatar, Link, Pagination } from '@mui/material'
import { DataGrid, GridColDef } from '@mui/x-data-grid'
import { usePeople } from '../api/hooks'
import { proxyImageUrl } from '../api/client'

const columns: GridColDef[] = [
  {
    field: 'name',
    headerName: 'Name',
    flex: 1,
    minWidth: 180,
    renderCell: (params) => (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Avatar src={proxyImageUrl(params.row.image_url)} sx={{ width: 32, height: 32 }}>
          {params.value?.[0]}
        </Avatar>
        {params.value}
      </Box>
    ),
  },
  { field: 'title', headerName: 'Title', flex: 1, minWidth: 200 },
  { field: 'department', headerName: 'Department', flex: 0.7, minWidth: 120 },
  { field: 'location', headerName: 'Location', flex: 0.7, minWidth: 120 },
  { field: 'primary_expertise', headerName: 'Primary Expertise', flex: 0.8, minWidth: 150 },
  {
    field: 'matched_13_categories',
    headerName: 'Matched 13 Expertise',
    flex: 1,
    minWidth: 200,
    renderCell: (params) => (
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {(params.value || []).slice(0, 2).map((cat: string) => (
          <Chip key={cat} label={cat} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
        ))}
        {(params.value || []).length > 2 && (
          <Chip label={`+${params.value.length - 2}`} size="small" sx={{ fontSize: '0.7rem' }} />
        )}
      </Box>
    ),
  },
  {
    field: 'sector',
    headerName: 'Sector',
    flex: 0.8,
    minWidth: 150,
    renderCell: (params) => {
      const sectors = params.value ? params.value.split('; ').filter(Boolean) : []
      return (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {sectors.slice(0, 2).map((s: string) => (
            <Chip key={s} label={s} size="small" variant="outlined" color="info" sx={{ fontSize: '0.7rem' }} />
          ))}
          {sectors.length > 2 && (
            <Chip label={`+${sectors.length - 2}`} size="small" color="info" sx={{ fontSize: '0.7rem' }} />
          )}
        </Box>
      )
    },
  },
  {
    field: 'linkedin_url',
    headerName: 'LinkedIn',
    width: 80,
    renderCell: (params) =>
      params.value ? (
        <Link href={params.value} target="_blank" rel="noopener" sx={{ fontSize: '0.8rem' }}>
          View
        </Link>
      ) : null,
  },
]

export default function PeopleTable({ companyId }: { companyId: string }) {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const pageSize = 50

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
      <DataGrid
        rows={data?.items || []}
        columns={columns}
        loading={loading}
        autoHeight
        disableRowSelectionOnClick
        hideFooter
        getRowId={(row) => row.id}
        onRowClick={(params) => navigate(`/people/${params.row.id}`, { state: { from: `/companies/${companyId}` } })}
        sx={{
          '& .MuiDataGrid-cell': { py: 1 },
          '& .MuiDataGrid-row': { cursor: 'pointer' },
        }}
      />
      {data && data.total > pageSize && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <Pagination
            count={Math.ceil(data.total / pageSize)}
            page={page}
            onChange={(_, p) => setPage(p)}
            color="primary"
          />
        </Box>
      )}
    </Box>
  )
}
