import { useState, useEffect } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  Box, Typography, Avatar, Chip, Divider, Link, CircularProgress,
  Card, CardContent, Breadcrumbs, IconButton, Accordion, Button,
  AccordionSummary, AccordionDetails, Tooltip, Dialog, DialogTitle,
  DialogContent, DialogActions, MenuItem, Select, FormControl,
  InputLabel, Alert, Snackbar, Tab, Tabs, Paper, TextField,
} from '@mui/material'
import {
  ArrowBack, Email, Phone, LinkedIn, Language, OpenInNew,
  ExpandMore, Verified, WorkOutline, PictureAsPdf, Refresh, Compare,
  Fullscreen, FullscreenExit,
} from '@mui/icons-material'
import { proxyImageUrl } from '../api/client'
import { usePerson, reanalyzePerson, analyzePersonWith, useAnalysisRuns, useProviders } from '../api/hooks'
import EvidencePopover from '../components/EvidencePopover'
import type { PersonDetail, EvidenceEntry, ExpertiseEvidence, AnalysisRun, AnalysisRunResult } from '../api/types'

// ── Shared types ─────────────────────────────────────────────────────────────

interface EvidenceAnchor {
  el: HTMLElement
  label: string
  entries: EvidenceEntry[]
}

type OnEvidence = (el: HTMLElement, label: string, entries: EvidenceEntry[]) => void

// ── Evidence-aware chip ───────────────────────────────────────────────────────

function EvChip({
  label,
  entries,
  onEvidence,
  color = 'default',
  variant = 'outlined',
  size = 'small',
  sx,
}: {
  label: string
  entries: EvidenceEntry[]
  onEvidence: OnEvidence
  color?: 'default' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error'
  variant?: 'outlined' | 'filled'
  size?: 'small' | 'medium'
  sx?: object
}) {
  return (
    <Tooltip title="Click to see evidence" arrow>
      <Chip
        label={label}
        size={size}
        color={color}
        variant={variant}
        onClick={(e) => onEvidence(e.currentTarget, label, entries)}
        sx={{ cursor: 'pointer', '&:hover': { boxShadow: 2 }, ...sx }}
      />
    </Tooltip>
  )
}

// ── Section heading ───────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <Typography variant="overline" color="text.secondary" fontWeight={700} sx={{ letterSpacing: 1.5, display: 'block', mb: 1.5 }}>
      {children}
    </Typography>
  )
}

// ── Left panel ────────────────────────────────────────────────────────────────

function LeftPanel({ person }: { person: PersonDetail }) {
  const extra = person.extra || {}
  const websiteIndustries = (extra.expertise_industries as string[] | undefined) || []
  const websiteCapabilities = (extra.expertise_capabilities as string[] | undefined) || []

  return (
    <Card elevation={1} sx={{ position: { md: 'sticky' }, top: 80, alignSelf: 'start' }}>
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', mb: 2.5 }}>
          <Avatar
            src={proxyImageUrl(person.image_url)}
            sx={{ width: 96, height: 96, fontSize: '2.5rem', mb: 1.5 }}
          >
            {person.name?.[0]}
          </Avatar>
          <Typography variant="h6" fontWeight={700} lineHeight={1.2}>{person.name}</Typography>
          {person.title && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{person.title}</Typography>
          )}
          {person.department && (
            <Typography variant="caption" color="text.disabled">{person.department}</Typography>
          )}
          {person.location && (
            <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5 }}>
              📍 {person.location}
            </Typography>
          )}
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2.5 }}>
          {person.email && (
            <Link href={`mailto:${person.email}`} underline="hover" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: '0.8rem' }}>
              <Email sx={{ fontSize: 16, color: 'text.secondary' }} />
              {person.email}
            </Link>
          )}
          {person.phone && (
            <Link href={`tel:${person.phone}`} underline="hover" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: '0.8rem' }}>
              <Phone sx={{ fontSize: 16, color: 'text.secondary' }} />
              {person.phone}
            </Link>
          )}
          {person.linkedin_url && (
            <Link href={person.linkedin_url} target="_blank" rel="noopener" underline="hover" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: '0.8rem' }}>
              <LinkedIn sx={{ fontSize: 16, color: '#0077b5' }} />
              LinkedIn
              {person.linkedin_enriched && (
                <Tooltip title="LinkedIn data enriched">
                  <Verified sx={{ fontSize: 14, color: 'success.main' }} />
                </Tooltip>
              )}
            </Link>
          )}
          {person.twitter_url && (
            <Link href={person.twitter_url} target="_blank" rel="noopener" underline="hover" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: '0.8rem' }}>
              <Language sx={{ fontSize: 16, color: 'text.secondary' }} />
              Twitter / X
            </Link>
          )}
          {person.profile_url && (
            <Link href={person.profile_url} target="_blank" rel="noopener" underline="hover" sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: '0.8rem' }}>
              <WorkOutline sx={{ fontSize: 16, color: 'text.secondary' }} />
              Profile page
            </Link>
          )}
        </Box>

        {websiteIndustries.length > 0 && (
          <>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              Website Industries
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {websiteIndustries.map((s) => <Chip key={s} label={s} size="small" />)}
            </Box>
          </>
        )}
        {websiteCapabilities.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
              Website Capabilities
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {websiteCapabilities.map((s) => <Chip key={s} label={s} size="small" />)}
            </Box>
          </Box>
        )}

        <Divider sx={{ my: 2 }} />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Typography variant="caption" color="text.disabled">
            Source: {person.data_source || 'Website'}
          </Typography>
          <Typography variant="caption" color="text.disabled">
            Scraped: {new Date(person.created_at).toLocaleDateString()}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  )
}

// ── Intelligence summary ──────────────────────────────────────────────────────

function IntelligenceSection({ person }: { person: PersonDetail }) {
  if (!person.primary_expertise && !person.justification) return null
  return (
    <Box sx={{ mb: 4 }}>
      <SectionHeading>Intelligence Summary</SectionHeading>
      {person.primary_expertise && (
        <Chip
          label={person.primary_expertise}
          color="primary"
          sx={{ fontWeight: 600, fontSize: '0.85rem', height: 32, mb: 1.5 }}
        />
      )}
      {person.justification && (
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
          {person.justification}
        </Typography>
      )}
    </Box>
  )
}

// ── Expertise classification ──────────────────────────────────────────────────

function ExpertiseSection({
  person,
  evidence,
  onEvidence,
}: {
  person: PersonDetail
  evidence: ExpertiseEvidence
  onEvidence: OnEvidence
}) {
  const [inferenceOpen, setInferenceOpen] = useState(false)
  const hasAny = (
    (person.matched_13_categories?.length ?? 0) > 0 ||
    (person.inferred_expertise_functional?.length ?? 0) > 0 ||
    (person.matched_inferred_expertise_topics?.length ?? 0) > 0
  )
  if (!hasAny) return null

  return (
    <Box sx={{ mb: 4 }}>
      <SectionHeading>Expertise Classification</SectionHeading>

      {(person.matched_13_categories?.length ?? 0) > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Layer 1 — Explicit expertise (13 categories)
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {person.matched_13_categories!.map((cat) => (
              <EvChip
                key={cat}
                label={cat}
                entries={evidence.categories?.[cat] ?? []}
                onEvidence={onEvidence}
                variant="outlined"
              />
            ))}
          </Box>
        </Box>
      )}

      {(person.inferred_expertise_functional?.length ?? 0) > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Layer 2 — Inferred functional expertise
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {person.inferred_expertise_functional!.map((item) => (
              <EvChip
                key={item}
                label={item}
                entries={evidence.inferred?.[item] ?? []}
                onEvidence={onEvidence}
                color="success"
                variant="outlined"
              />
            ))}
          </Box>
          {person.inference_reasoning && (
            <Box
              onClick={() => setInferenceOpen((o) => !o)}
              sx={{ mt: 1, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 0.5 }}
            >
              <ExpandMore
                sx={{
                  fontSize: 16,
                  color: 'text.secondary',
                  transform: inferenceOpen ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.2s',
                }}
              />
              <Typography variant="caption" color="text.secondary">
                {inferenceOpen ? 'Hide' : 'Show'} inference reasoning
              </Typography>
            </Box>
          )}
          {inferenceOpen && person.inference_reasoning && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block', mt: 0.75, pl: 2.5, borderLeft: '2px solid', borderColor: 'divider', lineHeight: 1.6 }}
            >
              {person.inference_reasoning}
            </Typography>
          )}
        </Box>
      )}

      {(person.matched_inferred_expertise_topics?.length ?? 0) > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Layer 3 — Topic expertise
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {person.matched_inferred_expertise_topics!.map((topic) => (
              <EvChip
                key={topic}
                label={topic}
                entries={evidence.topics?.[topic] ?? []}
                onEvidence={onEvidence}
                color="primary"
                variant="outlined"
                sx={{ fontSize: '0.7rem', height: 22 }}
              />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  )
}

// ── Sector & geography ────────────────────────────────────────────────────────

function SectorSection({
  person,
  evidence,
  onEvidence,
}: {
  person: PersonDetail
  evidence: ExpertiseEvidence
  onEvidence: OnEvidence
}) {
  const sectors = person.sector ? person.sector.split('; ').filter(Boolean) : []
  const geographies = person.geography ? person.geography.split('; ').filter(Boolean) : []
  const hasAny = sectors.length > 0 || (person.matched_sector?.length ?? 0) > 0 || geographies.length > 0
  if (!hasAny) return null

  return (
    <Box sx={{ mb: 4 }}>
      <SectionHeading>Sector & Geography</SectionHeading>

      {sectors.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Sector
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {sectors.map((s) => (
              <EvChip
                key={s}
                label={s}
                entries={evidence.sectors?.[s] ?? []}
                onEvidence={onEvidence}
                color="info"
                variant="outlined"
              />
            ))}
          </Box>
        </Box>
      )}

      {(person.matched_sector?.length ?? 0) > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Matched Sector (controlled vocabulary)
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {person.matched_sector!.map((s) => (
              <EvChip
                key={s}
                label={s}
                entries={evidence.matched_sectors?.[s] ?? []}
                onEvidence={onEvidence}
                color="info"
              />
            ))}
          </Box>
        </Box>
      )}

      {geographies.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>
            Geography
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
            {geographies.map((g) => (
              <Chip key={g} label={g} size="small" color="secondary" variant="outlined" />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  )
}

// ── Profile section ───────────────────────────────────────────────────────────

function ProfileSection({ person }: { person: PersonDetail }) {
  const hasAny = person.bio || person.linkedin_headline || person.linkedin_summary ||
    person.linkedin_experience_summary || (person.linkedin_skills?.length ?? 0) > 0
  if (!hasAny) return null

  return (
    <Box sx={{ mb: 4 }}>
      <SectionHeading>Profile</SectionHeading>

      {person.bio && (
        <Box sx={{ mb: 2.5 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>Bio</Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{person.bio}</Typography>
        </Box>
      )}

      {person.linkedin_headline && (
        <Box sx={{ mb: 2.5 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>LinkedIn Headline</Typography>
          <Typography variant="body2">{person.linkedin_headline}</Typography>
        </Box>
      )}

      {person.linkedin_summary && (
        <Box sx={{ mb: 2.5 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>LinkedIn Summary</Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{person.linkedin_summary}</Typography>
        </Box>
      )}

      {person.linkedin_experience_summary && (
        <Box sx={{ mb: 2.5 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>LinkedIn Experience</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {person.linkedin_experience_summary.split('\n').filter(Boolean).map((line, i) => (
              <li key={i}>
                <Typography variant="body2" sx={{ lineHeight: 1.6 }}>{line}</Typography>
              </li>
            ))}
          </Box>
        </Box>
      )}

      {(person.linkedin_skills?.length ?? 0) > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>LinkedIn Skills</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {person.linkedin_skills!.map((s) => (
              <Chip key={s} label={s} size="small" variant="outlined" sx={{ fontSize: '0.7rem', height: 22 }} />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  )
}

// ── Source evidence accordion ─────────────────────────────────────────────────

function SourceEvidenceAccordion({ person, expanded }: { person: PersonDetail; expanded?: boolean }) {
  const extra = person.extra || {}
  const websiteIndustries = (extra.expertise_industries as string[] | undefined) || []
  const websiteCapabilities = (extra.expertise_capabilities as string[] | undefined) || []
  const websiteEducation = (extra.education as Array<{ degree?: string; institution?: string; year?: string; raw?: string }> | undefined) || []
  const hasAny = websiteIndustries.length > 0 || websiteCapabilities.length > 0 || websiteEducation.length > 0 || person.source_url

  if (!hasAny) return null

  return (
    <Accordion expanded={expanded} elevation={0} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, '&:before': { display: 'none' } }}>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Typography variant="body2" fontWeight={600} color="text.secondary">Source Evidence</Typography>
      </AccordionSummary>
      <AccordionDetails>
        {websiteIndustries.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>Website Industries</Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {websiteIndustries.map((s) => <Chip key={s} label={s} size="small" variant="outlined" />)}
            </Box>
          </Box>
        )}
        {websiteCapabilities.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>Website Capabilities</Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {websiteCapabilities.map((s) => <Chip key={s} label={s} size="small" variant="outlined" />)}
            </Box>
          </Box>
        )}
        {websiteEducation.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>Education</Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
              {websiteEducation.map((e, i) => {
                const text = e.raw || [e.degree, e.institution, e.year].filter(Boolean).join(', ')
                return text ? <Typography key={i} variant="body2">{text}</Typography> : null
              })}
            </Box>
          </Box>
        )}
        {person.source_url && (
          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.75}>Source URL</Typography>
            <Link href={person.source_url} target="_blank" rel="noopener" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, fontSize: '0.8rem' }}>
              {person.source_url}
              <OpenInNew sx={{ fontSize: 14 }} />
            </Link>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  )
}

// ── Analysis comparison helpers ───────────────────────────────────────────────

const PROVIDER_OPTIONS = ['claude', 'openai', 'deepseek', 'gemini', 'qwen']

interface NormalizedAnalysis {
  primaryExpertise: string | null
  justification: string | null
  layer1: string[]
  layer2: string[]
  inferenceReasoning: string | null
  topics: string[]
  sectors: string[]
  matchedSectors: string[]
  evidence: ExpertiseEvidence
}

function normalizePersonResult(p: PersonDetail): NormalizedAnalysis {
  return {
    primaryExpertise: p.primary_expertise ?? null,
    justification: p.justification ?? null,
    layer1: p.matched_13_categories ?? [],
    layer2: p.inferred_expertise_functional ?? [],
    inferenceReasoning: p.inference_reasoning ?? null,
    topics: p.matched_inferred_expertise_topics ?? [],
    sectors: p.sector ? p.sector.split('; ').filter(Boolean) : [],
    matchedSectors: p.matched_sector ?? [],
    evidence: p.expertise_evidence ?? {},
  }
}

function normalizeRunResult(r: AnalysisRunResult): NormalizedAnalysis {
  return {
    primaryExpertise: r.primary_expertise ?? null,
    justification: r.justification ?? null,
    layer1: r.explicit_expertise_13 ?? [],
    layer2: r.inferred_expertise_functional ?? [],
    inferenceReasoning: r.inference_reasoning ?? null,
    topics: r.topic_overlap ?? [],
    sectors: r.sectors ?? [],
    matchedSectors: r.matched_sectors ?? [],
    evidence: r.evidence_map ?? {},
  }
}

function CompareColumn({
  label,
  analysis,
  providerLabel,
  onEvidence,
}: {
  label: string
  analysis: NormalizedAnalysis
  providerLabel: string
  onEvidence: OnEvidence
}) {
  const { primaryExpertise, justification, layer1: l1, layer2: l2, inferenceReasoning, topics, sectors, matchedSectors: matched, evidence } = analysis

  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={700} display="block" mb={1}>
        {label} — <em>{providerLabel}</em>
      </Typography>

      {primaryExpertise && (
        <Box mb={1.5}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Primary</Typography>
          <Chip label={primaryExpertise} color="primary" size="small" />
          {justification && (
            <Typography variant="caption" color="text.secondary" display="block" mt={0.75} sx={{ fontStyle: 'italic', lineHeight: 1.5 }}>
              {justification}
            </Typography>
          )}
        </Box>
      )}

      {l1.length > 0 && (
        <Box mb={1.5}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Layer 1 — Explicit</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {l1.map((c: string) => (
              <EvChip key={c} label={c} entries={evidence.categories?.[c] ?? []} onEvidence={onEvidence} variant="outlined" />
            ))}
          </Box>
        </Box>
      )}

      {l2.length > 0 && (
        <Box mb={1.5}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Layer 2 — Inferred</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {l2.map((c: string) => (
              <EvChip key={c} label={c} entries={evidence.inferred?.[c] ?? []} onEvidence={onEvidence} color="success" variant="outlined" />
            ))}
          </Box>
          {inferenceReasoning && (
            <Typography variant="caption" color="text.secondary" display="block" mt={0.75} sx={{ fontStyle: 'italic', lineHeight: 1.5 }}>
              {inferenceReasoning}
            </Typography>
          )}
        </Box>
      )}

      {topics.length > 0 && (
        <Box mb={1.5}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Layer 3 — Topics</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {topics.map((t: string) => (
              <EvChip key={t} label={t} entries={evidence.topics?.[t] ?? []} onEvidence={onEvidence} color="primary" variant="outlined" sx={{ fontSize: '0.7rem', height: 22 }} />
            ))}
          </Box>
        </Box>
      )}

      {sectors.length > 0 && (
        <Box mb={1.5}>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Sectors</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {sectors.map((s: string) => (
              <EvChip key={s} label={s} entries={evidence.sectors?.[s] ?? []} onEvidence={onEvidence} color="info" variant="outlined" />
            ))}
          </Box>
        </Box>
      )}

      {matched.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Matched Sectors</Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {matched.map((s: string) => (
              <EvChip key={s} label={s} entries={evidence.matched_sectors?.[s] ?? []} onEvidence={onEvidence} color="info" />
            ))}
          </Box>
        </Box>
      )}
    </Box>
  )
}

function CompareDialog({
  open,
  onClose,
  person,
  personId,
}: {
  open: boolean
  onClose: () => void
  person: PersonDetail
  personId: string
}) {
  const providerList = useProviders()
  const [provider, setProvider] = useState('deepseek')
  const [model, setModel] = useState('')
  const [running, setRunning] = useState(false)
  const [latestRun, setLatestRun] = useState<AnalysisRun | null>(null)
  const [leftRunId, setLeftRunId] = useState<string | 'current'>('current')
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState(0)
  const [fullScreen, setFullScreen] = useState(false)
  const [evidenceAnchor, setEvidenceAnchor] = useState<EvidenceAnchor | null>(null)
  const { runs, loading: runsLoading, refresh: refreshRuns } = useAnalysisRuns(open ? personId : null)

  const handleEvidence: OnEvidence = (el, label, entries) => setEvidenceAnchor({ el, label, entries })

  // Pre-fill model when provider changes or provider list loads
  useEffect(() => {
    const info = providerList.find((p) => p.provider === provider)
    setModel(info?.default_model ?? '')
  }, [provider, providerList])

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    try {
      const run = await analyzePersonWith(personId, provider, model || undefined)
      setLatestRun(run)
      setTab(0)
      refreshRuns()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setRunning(false)
    }
  }

  const displayRun = latestRun ?? (runs.length > 0 ? runs[0] : null)

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth fullScreen={fullScreen}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        Compare Analysis
        <Tooltip title={fullScreen ? 'Exit full screen' : 'Full screen'}>
          <IconButton size="small" onClick={() => setFullScreen((f) => !f)}>
            {fullScreen ? <FullscreenExit fontSize="small" /> : <Fullscreen fontSize="small" />}
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Provider</InputLabel>
            <Select value={provider} label="Provider" onChange={(e) => setProvider(e.target.value)}>
              {(providerList.length > 0 ? providerList.map((p) => p.provider) : PROVIDER_OPTIONS).map((p) => (
                <MenuItem key={p} value={p}>{p}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            sx={{ minWidth: 220 }}
            placeholder="default"
          />
          <Button variant="contained" size="small" onClick={handleRun} disabled={running}>
            {running ? 'Running…' : 'Run Analysis'}
          </Button>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Comparison" />
          <Tab label={`History (${runs.length})`} />
        </Tabs>

        {tab === 0 && (() => {
          const leftRun = leftRunId === 'current' ? null : runs.find((r) => r.id === leftRunId) ?? null
          const leftAnalysis = leftRun ? normalizeRunResult(leftRun.result) : normalizePersonResult(person)
          const leftLabel = leftRun
            ? `${leftRun.provider}${leftRun.model ? ` / ${leftRun.model}` : ''} v${leftRun.version}`
            : 'active'
          return (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                <FormControl size="small" sx={{ minWidth: 220 }}>
                  <InputLabel>Left side</InputLabel>
                  <Select value={leftRunId} label="Left side" onChange={(e) => setLeftRunId(e.target.value)}>
                    <MenuItem value="current">Current (active)</MenuItem>
                    {runs.map((r) => (
                      <MenuItem key={r.id} value={r.id}>
                        {r.provider}{r.model ? ` / ${r.model}` : ''} v{r.version} — {new Date(r.created_at).toLocaleDateString()}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
              <Box sx={{ display: 'flex', gap: 3 }}>
                <CompareColumn label="Left" analysis={leftAnalysis} providerLabel={leftLabel} onEvidence={handleEvidence} />
                <Divider orientation="vertical" flexItem />
                {displayRun ? (
                  <CompareColumn
                    label="Right"
                    analysis={normalizeRunResult(displayRun.result)}
                    providerLabel={`${displayRun.provider}${displayRun.model ? ` / ${displayRun.model}` : ''} v${displayRun.version}`}
                    onEvidence={handleEvidence}
                  />
                ) : (
                  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography color="text.secondary" variant="body2">
                      Run an analysis or select a run from History
                    </Typography>
                  </Box>
                )}
              </Box>
            </Box>
          )
        })()}

        {tab === 1 && (
          <Box>
            {runsLoading && <CircularProgress size={20} />}
            {!runsLoading && runs.length === 0 && (
              <Typography color="text.secondary" variant="body2">No past runs yet</Typography>
            )}
            {runs.map((run) => (
              <Paper key={run.id} variant="outlined" sx={{ p: 2, mb: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {run.provider}{run.model ? ` / ${run.model}` : ''} v{run.version} — {new Date(run.created_at).toLocaleString()}
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 0.5 }}>
                      {run.result.primary_expertise ?? '—'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
                    <Button size="small" variant="outlined" onClick={() => { setLeftRunId(run.id); setTab(0) }}>
                      ← Left
                    </Button>
                    <Button size="small" variant="outlined" onClick={() => { setLatestRun(run); setTab(0) }}>
                      Right →
                    </Button>
                  </Box>
                </Box>
              </Paper>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>

      <EvidencePopover
        anchorEl={evidenceAnchor?.el ?? null}
        label={evidenceAnchor?.label ?? ''}
        entries={evidenceAnchor?.entries ?? []}
        onClose={() => setEvidenceAnchor(null)}
      />
    </Dialog>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PersonProfilePage() {
  const { personId } = useParams<{ personId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { person, loading } = usePerson(personId ?? null)
  const [evidenceAnchor, setEvidenceAnchor] = useState<EvidenceAnchor | null>(null)
  const [isPrinting, setIsPrinting] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const backPath: string = (location.state as { from?: string } | null)?.from
    ?? (person ? `/companies/${person.company_id}` : '/dashboard')

  const handleEvidence: OnEvidence = (el, label, entries) => {
    setEvidenceAnchor({ el, label, entries })
  }

  const handleExportPdf = () => {
    setIsPrinting(true)
    setTimeout(() => { window.print() }, 100)
  }

  const handleReanalyze = async () => {
    if (!personId) return
    setReanalyzing(true)
    try {
      await reanalyzePerson(personId)
      setToast('Re-analysis queued — refresh in a few seconds to see updated results')
    } catch {
      setToast('Failed to queue re-analysis')
    } finally {
      setReanalyzing(false)
    }
  }

  useEffect(() => {
    const afterPrint = () => setIsPrinting(false)
    window.addEventListener('afterprint', afterPrint)
    return () => window.removeEventListener('afterprint', afterPrint)
  }, [])

  if (loading || !person) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
        <CircularProgress />
      </Box>
    )
  }

  const evidence: ExpertiseEvidence = person.expertise_evidence ?? {}

  return (
    <Box sx={{ maxWidth: 1280, mx: 'auto' }}>
      {/* Breadcrumb + actions — hidden on print */}
      <Box className="no-print" sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconButton size="small" onClick={() => navigate(backPath)}>
            <ArrowBack fontSize="small" />
          </IconButton>
          <Breadcrumbs>
            <Link component="button" underline="hover" onClick={() => navigate('/dashboard')} sx={{ cursor: 'pointer', fontSize: '0.875rem' }}>
              Dashboard
            </Link>
            {person.company_id && (
              <Link component="button" underline="hover" onClick={() => navigate(`/companies/${person.company_id}`)} sx={{ cursor: 'pointer', fontSize: '0.875rem' }}>
                Company
              </Link>
            )}
            <Typography color="text.primary" fontSize="0.875rem">{person.name}</Typography>
          </Breadcrumbs>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={reanalyzing ? <CircularProgress size={14} /> : <Refresh />}
            onClick={handleReanalyze}
            disabled={reanalyzing}
          >
            Re-analyze
          </Button>
          <Button
            variant="outlined"
            size="small"
            startIcon={<Compare />}
            onClick={() => setCompareOpen(true)}
          >
            Compare
          </Button>
          <Button
            variant="outlined"
            size="small"
            startIcon={<PictureAsPdf />}
            onClick={handleExportPdf}
          >
            Export PDF
          </Button>
        </Box>
      </Box>

      <Box
        className="profile-grid"
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '300px 1fr' },
          gap: 3,
          alignItems: 'start',
        }}
      >
        <Box className="profile-left-panel">
          <LeftPanel person={person} />
        </Box>

        <Box>
          <IntelligenceSection person={person} />
          {(person.primary_expertise || person.justification) && <Divider sx={{ mb: 4 }} />}

          <ExpertiseSection person={person} evidence={evidence} onEvidence={handleEvidence} />
          <SectorSection person={person} evidence={evidence} onEvidence={handleEvidence} />
          <ProfileSection person={person} />
          <SourceEvidenceAccordion person={person} expanded={isPrinting || undefined} />
        </Box>
      </Box>

      <EvidencePopover
        anchorEl={evidenceAnchor?.el ?? null}
        label={evidenceAnchor?.label ?? ''}
        entries={evidenceAnchor?.entries ?? []}
        onClose={() => setEvidenceAnchor(null)}
      />

      {compareOpen && personId && (
        <CompareDialog
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
          person={person}
          personId={personId}
        />
      )}

      <Snackbar
        open={toast !== null}
        autoHideDuration={5000}
        onClose={() => setToast(null)}
        message={toast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  )
}