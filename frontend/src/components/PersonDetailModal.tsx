import { useState, useEffect } from 'react'
import {
  Dialog, DialogTitle, DialogContent, IconButton, Box, Typography,
  Avatar, Chip, Divider, Link, CircularProgress, Grid,
} from '@mui/material'
import { Close, Email, Phone, LinkedIn, Language } from '@mui/icons-material'
import api from '../api/client'
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
                src={person.image_url || undefined}
                imgProps={{ referrerPolicy: 'no-referrer' }}
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
            <DetailRow label="Functional Expertise" value={person.inferred_expertise_functional} />
            <DetailRow label="Sector" value={person.sector} />
            <DetailRow label="Geography" value={person.geography} />
            <DetailRow label="Location" value={person.location} />

            {/* Categories */}
            {person.matched_13_categories && person.matched_13_categories.length > 0 && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Categories
                </Typography>
                <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                  {person.matched_13_categories.map((cat) => (
                    <Chip key={cat} label={cat} size="small" variant="outlined" />
                  ))}
                </Box>
              </Box>
            )}

            {/* Expertise topics */}
            {person.matched_inferred_expertise_topics && person.matched_inferred_expertise_topics.length > 0 && (
              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Expertise Topics
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
            <DetailRow label="LinkedIn Experience" value={person.linkedin_experience_summary} />

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