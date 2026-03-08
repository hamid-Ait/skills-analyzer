import { useState } from 'react'
import { Box, TextField, Chip, Avatar, Link, Pagination } from '@mui/material'
import { DataGrid, GridColDef } from '@mui/x-data-grid'
import { usePeople } from '../api/hooks'
import PersonDetailModal from './PersonDetailModal'

const columns: GridColDef[] = [
  {
    field: 'name',
    headerName: 'Name',
    flex: 1,
    minWidth: 180,
    renderCell: (params) => (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Avatar src={params.row.image_url || undefined} imgProps={{ referrerPolicy: 'no-referrer' }} sx={{ width: 32, height: 32 }}>
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
    headerName: 'Categories',
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
  { field: 'sector', headerName: 'Sector', flex: 0.6, minWidth: 100 },
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
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)
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
        onRowClick={(params) => setSelectedPersonId(params.row.id)}
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
      <PersonDetailModal
        personId={selectedPersonId}
        onClose={() => setSelectedPersonId(null)}
      />
    </Box>
  )
}
