import { Chip } from '@mui/material'

const STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> = {
  pending: 'default',
  discovering: 'info',
  scraping: 'warning',
  searching: 'info',
  analyzing: 'secondary',
  resolving: 'info',
  enriching: 'secondary',
  processing: 'warning',
  completed: 'success',
  error: 'error',
}

export default function StatusChip({ status }: { status: string }) {
  return (
    <Chip
      label={status}
      color={STATUS_COLORS[status] || 'default'}
      size="small"
      sx={{ textTransform: 'capitalize', fontWeight: 500 }}
    />
  )
}
