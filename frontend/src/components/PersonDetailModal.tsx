import { useState, useEffect } from 'react'
import {
  Dialog, DialogTitle, DialogContent, IconButton, Box, Typography,
  Avatar, Chip, Divider, Link, CircularProgress, Grid,
} from '@mui/material'
import { Close, Email, Phone, LinkedIn, Language } from '@mui/icons-material'
import api, { proxyImageUrl } from '../api/client'
import type { PersonDetail } from '../api/types'

interface Props {
  personId: string | null
  onClose: () => void
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={600}>
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  )
}

export default function PersonDetailModal({ personId, onClose }: Props) {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!personId) { setPerson(null); return }
    setLoading(true)
    api
      .get<PersonDetail>(`/people/${personId}`)
      .then(({ data }) => setPerson(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [personId])

  return (
    <Dialog open={!!personId} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        Person Details
        <IconButton onClick={onClose} size="small"><Close /></IconButton>
      </DialogTitle>
      <DialogContent>
        {loading || !person ? (
          <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress /></Box>
        ) : (
          <Box>
            {/* Header */}
            <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
              <Avatar
                src={proxyImageUrl(person.image_url)}
                sx={{ width: 64, height: 64, fontSize: '1.5rem' }}
              >
                {person.name?.[0]}
              </Avatar>
              <Box>
                <Typography variant="h6" fontWeight={600}>{person.name}</Typography>
                {person.title && (
                  <Typography variant="body2" color="text.secondary">{person.title}</Typography>
                )}
                {person.department && (
                  <Typography variant="caption" color="text.secondary">{person.department}</Typography>
                )}
              </Box>
            </Box>

            {/* Contact links */}
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              {person.email && (
                <Chip icon={<Email />} label={person.email} size="small" component="a" href={`mailto:${person.email}`} clickable />
              )}
              {person.phone && (
                <Chip icon={<Phone />} label={person.phone} size="small" component="a" href={`tel:${person.phone}`} clickable />
              )}
              {person.linkedin_url && (
                <Chip icon={<LinkedIn />} label="LinkedIn" size="small" component="a" href={person.linkedin_url} target="_blank" clickable />
              )}
              {person.twitter_url && (
                <Chip icon={<Language />} label="Twitter" size="small" component="a" href={person.twitter_url} target="_blank" clickable />
              )}
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* Bio */}
            <DetailRow label="Bio" value={person.bio} />

            {/* Expertise */}
            <DetailRow label="Primary Expertise" value={person.primary_expertise} />
            <DetailRow label="Justification" value={person.justification} />
            {/* Categories */}
            {person.matched_13_categories && person.matched_13_categories.length > 0 && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Matched 13 Expertise
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.matched_13_categories.map((cat) => (
                    <Chip key={cat} label={cat} size="small" variant="outlined" />
                  ))}
                </Box>
              </Box>
            )}
            {/* Functional Expertise */}
            {person.inferred_expertise_functional && person.inferred_expertise_functional.length > 0 && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Inferred Expertise
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.inferred_expertise_functional.map((f) => (
                    <Chip key={f} label={f} size="small" variant="outlined" color="success" />
                  ))}
                </Box>
              </Box>
            )}

            {/* Sector */}
            {person.sector && person.sector !== '—' && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Sector
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.sector.split('; ').filter(Boolean).map((s) => (
                    <Chip key={s} label={s} size="small" variant="outlined" color="info" />
                  ))}
                </Box>
              </Box>
            )}

            {/* Geography */}
            {person.geography && person.geography !== '—' && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Geography
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.geography.split('; ').filter(Boolean).map((g) => (
                    <Chip key={g} label={g} size="small" variant="outlined" color="secondary" />
                  ))}
                </Box>
              </Box>
            )}
            <DetailRow label="Location" value={person.location} />



            {/* Expertise topics */}
            {person.matched_inferred_expertise_topics && person.matched_inferred_expertise_topics.length > 0 && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Matched Inferred Expertise
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.matched_inferred_expertise_topics.map((topic) => (
                    <Chip key={topic} label={topic} size="small" color="primary" variant="outlined" />
                  ))}
                </Box>
              </Box>
            )}

            {/* LinkedIn enrichment */}
            <DetailRow label="LinkedIn Headline" value={person.linkedin_headline} />
            {person.linkedin_experience_summary && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  LinkedIn Experience
                </Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {person.linkedin_experience_summary.split('\n').filter(Boolean).map((line, i) => (
                    <li key={i}>
                      <Typography variant="body2">{line}</Typography>
                    </li>
                  ))}
                </Box>
              </Box>
            )}

            {/* Meta */}
            <Divider sx={{ my: 2 }} />
            <Typography variant="caption" color="text.secondary">
              Source: {person.data_source || 'Website'}
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  )
}