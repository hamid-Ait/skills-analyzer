import { Box, Typography } from '@mui/material'
import { Check } from '@mui/icons-material'

const STEPS = [
  { key: 'discovering', label: 'Discover' },
  { key: 'scraping', label: 'Scrape' },
  { key: 'searching', label: 'Search' },
  { key: 'resolving', label: 'Resolve' },
  { key: 'enriching', label: 'Enrich' },
  { key: 'analyzing', label: 'Analyze' },
]

const STATUS_ORDER: Record<string, number> = {
  pending: -1,
  discovering: 0,
  scraping: 1,
  searching: 2,
  resolving: 3,
  enriching: 4,
  analyzing: 5,
  completed: 6,
  error: -2,
}

export default function PipelineProgress({ status }: { status: string }) {
  const currentIdx = STATUS_ORDER[status] ?? -1

  if (status === 'completed' || status === 'error') return null

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      {STEPS.map((step, idx) => {
        const isDone = idx < currentIdx
        const isActive = idx === currentIdx
        const color = isDone
          ? 'success.main'
          : isActive
            ? 'warning.main'
            : 'grey.400'

        return (
          <Box key={step.key} sx={{ display: 'flex', alignItems: 'center' }}>
            {/* Step dot */}
            <Box
              sx={{
                width: isActive ? 22 : 18,
                height: isActive ? 22 : 18,
                borderRadius: '50%',
                bgcolor: color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.3s',
                boxShadow: isActive ? '0 0 0 3px rgba(255,152,0,0.3)' : 'none',
              }}
            >
              {isDone && <Check sx={{ fontSize: 12, color: 'white' }} />}
              {isActive && (
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: 'white' }} />
              )}
            </Box>
            {/* Label */}
            <Typography
              variant="caption"
              sx={{
                mx: 0.3,
                fontSize: '0.6rem',
                fontWeight: isActive ? 700 : 400,
                color: isActive ? 'warning.main' : isDone ? 'success.main' : 'text.disabled',
              }}
            >
              {step.label}
            </Typography>
            {/* Connector line */}
            {idx < STEPS.length - 1 && (
              <Box
                sx={{
                  width: 12,
                  height: 2,
                  bgcolor: isDone ? 'success.main' : 'grey.300',
                  mx: 0.2,
                }}
              />
            )}
          </Box>
        )
      })}
    </Box>
  )
}