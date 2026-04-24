import { useNavigate } from 'react-router-dom'
import { Box, Typography, Card, CardContent, Avatar, Chip, Link } from '@mui/material'
import { LinkedIn } from '@mui/icons-material'
import { proxyImageUrl } from '../api/client'
import type { PersonBrief } from '../api/types'

interface Props {
  people: PersonBrief[]
  companyId?: string
}

export default function PeopleCards({ people, companyId }: Props) {
  const navigate = useNavigate()
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: 2,
      }}
    >
      {people.map((person) => (
        <Card
          key={person.id}
          sx={{
            cursor: 'pointer',
            transition: 'box-shadow 0.2s, transform 0.2s',
            '&:hover': { boxShadow: 4, transform: 'translateY(-2px)' },
          }}
          onClick={() => navigate(`/people/${person.id}`, { state: { from: companyId ? `/companies/${companyId}` : '/dashboard' } })}
        >
          <CardContent sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', pb: 2 }}>
            <Avatar
              src={proxyImageUrl(person.image_url)}
              sx={{ width: 72, height: 72, mb: 1.5, fontSize: '1.8rem' }}
            >
              {person.name?.[0]}
            </Avatar>
            <Typography variant="subtitle1" fontWeight={600} noWrap sx={{ maxWidth: '100%' }}>
              {person.name}
            </Typography>
            {person.title && (
              <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: '100%', mb: 0.5 }}>
                {person.title}
              </Typography>
            )}
            {person.location && (
              <Typography variant="caption" color="text.disabled" noWrap sx={{ maxWidth: '100%', mb: 1 }}>
                {person.location}
              </Typography>
            )}
            {person.primary_expertise && (
              <Chip
                label={person.primary_expertise}
                size="small"
                color="primary"
                variant="outlined"
                sx={{ fontSize: '0.7rem', mb: 1, maxWidth: '100%' }}
              />
            )}
            {person.matched_13_categories && person.matched_13_categories.length > 0 && (
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', justifyContent: 'center' }}>
                {person.matched_13_categories.slice(0, 2).map((cat) => (
                  <Chip
                    key={cat}
                    label={cat}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.6rem', height: 18 }}
                  />
                ))}
                {person.matched_13_categories.length > 2 && (
                  <Chip label={`+${person.matched_13_categories.length - 2}`} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
                )}
              </Box>
            )}
            {person.linkedin_url && (
              <Box sx={{ mt: 1 }}>
                <Link
                  href={person.linkedin_url}
                  target="_blank"
                  rel="noopener"
                  onClick={(e) => e.stopPropagation()}
                  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, fontSize: '0.75rem' }}
                >
                  <LinkedIn sx={{ fontSize: 16, color: '#0077b5' }} />
                  LinkedIn
                </Link>
              </Box>
            )}
          </CardContent>
        </Card>
      ))}
    </Box>
  )
}