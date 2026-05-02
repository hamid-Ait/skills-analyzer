import { Popover, Box, Typography, Chip, Divider } from '@mui/material'
import type { EvidenceEntry } from '../api/types'

const SOURCE_LABELS: Record<string, string> = {
  bio: 'Bio',
  title: 'Title',
  department: 'Department',
  linkedin_headline: 'LinkedIn Headline',
  linkedin_summary: 'LinkedIn Summary',
  linkedin_experience: 'LinkedIn Experience',
  linkedin_skills: 'LinkedIn Skills',
  website_industries: 'Website Industries',
  website_capabilities: 'Website Capabilities',
  keyword_match: 'Keyword',
}

const SOURCE_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'success' | 'info' | 'warning'> = {
  bio: 'primary',
  title: 'secondary',
  department: 'secondary',
  linkedin_headline: 'info',
  linkedin_summary: 'info',
  linkedin_experience: 'info',
  linkedin_skills: 'info',
  website_industries: 'success',
  website_capabilities: 'success',
  keyword_match: 'warning',
}

interface Props {
  anchorEl: HTMLElement | null
  label: string
  entries: EvidenceEntry[]
  onClose: () => void
}

export default function EvidencePopover({ anchorEl, label, entries, onClose }: Props) {
  return (
    <Popover
      open={Boolean(anchorEl)}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      transformOrigin={{ vertical: 'top', horizontal: 'left' }}
      slotProps={{ paper: { sx: { maxWidth: 380, p: 2 } } }}
    >
      <Typography variant="subtitle2" fontWeight={700} mb={1}>
        {label}
      </Typography>
      <Divider sx={{ mb: 1.5 }} />
      {entries.length === 0 ? (
        <Typography variant="caption" color="text.disabled">
          No evidence recorded — re-analyze this company to populate evidence.
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
          {entries.map((e, i) => (
            <Box key={i} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
              <Chip
                label={SOURCE_LABELS[e.source] ?? e.source}
                size="small"
                color={SOURCE_COLORS[e.source] ?? 'default'}
                variant="outlined"
                sx={{ fontSize: '0.65rem', height: 20, flexShrink: 0 }}
              />
              <Typography variant="caption" sx={{ lineHeight: 1.5, pt: '1px' }}>
                {e.text}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Popover>
  )
}