import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import {
  Box, Typography, Paper, Button, FormControlLabel, Checkbox,
  Alert, CircularProgress, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, List, ListItem,
  ListItemText, ListItemIcon,
} from '@mui/material'
import { CloudUpload, InsertDriveFile, Warning } from '@mui/icons-material'
import api from '../api/client'
import type { UploadResponse } from '../api/types'

interface ExistingCompany {
  url: string
  name: string | null
  people_count: number
  status: string
}

/** Parse URLs from a file client-side (same logic as backend). */
function parseUrlsFromFile(text: string, filename: string): string[] {
  const urls: string[] = []
  if (filename.endsWith('.json')) {
    try {
      const raw = JSON.parse(text)
      const items = Array.isArray(raw) ? raw : (raw.urls || raw.URLs || [])
      for (const item of items) {
        if (typeof item === 'string') urls.push(item.trim())
        else if (typeof item === 'object') {
          for (const k of ['url', 'URL', 'link', 'href', 'website']) {
            if (k in item) { urls.push(item[k].trim()); break }
          }
        }
      }
    } catch { /* ignore parse errors */ }
  } else {
    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (trimmed.startsWith('http')) urls.push(trimmed)
    }
  }
  return urls.filter(u => u.startsWith('http'))
}

export default function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [discover, setDiscover] = useState(true)
  const [followProfiles, setFollowProfiles] = useState(true)
  const [enrichLinkedin, setEnrichLinkedin] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  // Rescrape confirmation state
  const [showConfirm, setShowConfirm] = useState(false)
  const [existingCompanies, setExistingCompanies] = useState<ExistingCompany[]>([])
  const [selectedRefreshUrls, setSelectedRefreshUrls] = useState<Set<string>>(new Set())
  const [checking, setChecking] = useState(false)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0])
      setError('')
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/json': ['.json'],
      'text/csv': ['.csv'],
      'text/plain': ['.txt'],
    },
    maxFiles: 1,
  })

  const doUpload = async () => {
    if (!file) return
    setUploading(true)
    setError('')

    // Determine which existing companies to skip (unchecked in dialog)
    const skipUrls = existingCompanies
      .filter(c => !selectedRefreshUrls.has(c.url))
      .map(c => c.url)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('discover', String(discover))
    formData.append('follow_profiles', String(followProfiles))
    formData.append('enrich_linkedin', String(enrichLinkedin))
    if (skipUrls.length > 0) {
      formData.append('skip_urls', JSON.stringify(skipUrls))
    }

    try {
      await api.post<UploadResponse>('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setChecking(true)
    setError('')

    try {
      // Parse URLs from the file to check for existing companies
      const text = await file.text()
      const urls = parseUrlsFromFile(text, file.name)

      if (urls.length === 0) {
        setError('No valid URLs found in the file')
        setChecking(false)
        return
      }

      const { data } = await api.post<{ existing: ExistingCompany[]; new_urls: string[] }>(
        '/upload/check-urls', { urls }
      )

      if (data.existing.length > 0) {
        setExistingCompanies(data.existing)
        setSelectedRefreshUrls(new Set(data.existing.map((c: ExistingCompany) => c.url)))
        setShowConfirm(true)
      } else {
        await doUpload()
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to check URLs')
    } finally {
      setChecking(false)
    }
  }

  const handleConfirmRescrape = async () => {
    setShowConfirm(false)
    await doUpload()
  }

  const isLoading = uploading || checking

  return (
    <Box sx={{ maxWidth: 600, mx: 'auto', mt: 6 }}>
      <Typography variant="h4" gutterBottom fontWeight={600} textAlign="center">
        Upload Company URLs
      </Typography>
      <Typography variant="body1" color="text.secondary" textAlign="center" mb={4}>
        Upload a JSON, CSV, or TXT file containing company URLs (one per line).
        The system will scrape team pages, analyze expertise, and build a skills matrix.
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper
        {...getRootProps()}
        sx={{
          p: 4,
          textAlign: 'center',
          cursor: 'pointer',
          border: '2px dashed',
          borderColor: isDragActive ? 'primary.main' : 'grey.300',
          bgcolor: isDragActive ? 'action.hover' : 'background.paper',
          transition: 'all 0.2s',
          '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' },
        }}
      >
        <input {...getInputProps()} />
        {file ? (
          <Box>
            <InsertDriveFile sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
            <Typography variant="h6">{file.name}</Typography>
            <Chip label={`${(file.size / 1024).toFixed(1)} KB`} size="small" sx={{ mt: 1 }} />
          </Box>
        ) : (
          <Box>
            <CloudUpload sx={{ fontSize: 48, color: 'grey.400', mb: 1 }} />
            <Typography variant="h6" color="text.secondary">
              {isDragActive ? 'Drop file here' : 'Drag & drop a file, or click to browse'}
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={1}>
              Supported: .json, .csv, .txt
            </Typography>
          </Box>
        )}
      </Paper>

      <Box sx={{ mt: 3 }}>
        <FormControlLabel
          control={<Checkbox checked={discover} onChange={(e) => setDiscover(e.target.checked)} />}
          label="Auto-discover team pages from homepage URLs"
        />
        <FormControlLabel
          control={<Checkbox checked={followProfiles} onChange={(e) => setFollowProfiles(e.target.checked)} />}
          label="Follow individual profile pages for richer data"
        />
        <FormControlLabel
          control={<Checkbox checked={enrichLinkedin} onChange={(e) => setEnrichLinkedin(e.target.checked)} />}
          label="Enrich with LinkedIn data (requires Apify token)"
        />
      </Box>

      <Button
        variant="contained"
        size="large"
        fullWidth
        disabled={!file || isLoading}
        onClick={handleUpload}
        startIcon={isLoading ? <CircularProgress size={20} color="inherit" /> : <CloudUpload />}
        sx={{ mt: 3 }}
      >
        {uploading ? 'Uploading...' : checking ? 'Checking...' : 'Start Processing'}
      </Button>

      {/* Rescrape confirmation dialog */}
      <Dialog open={showConfirm} onClose={() => setShowConfirm(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Warning color="warning" />
          Companies Already Exist
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            The following companies have already been scraped. Select which ones
            to refresh (existing data will be deleted and re-scraped). Unselected
            companies will be skipped.
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
            <Button
              size="small"
              onClick={() => setSelectedRefreshUrls(new Set(existingCompanies.map(c => c.url)))}
            >
              Select all
            </Button>
            <Button
              size="small"
              onClick={() => setSelectedRefreshUrls(new Set())}
            >
              Deselect all
            </Button>
          </Box>
          <List dense>
            {existingCompanies.map((c) => (
              <ListItem key={c.url} sx={{ cursor: 'pointer' }} onClick={() => {
                setSelectedRefreshUrls(prev => {
                  const next = new Set(prev)
                  if (next.has(c.url)) next.delete(c.url)
                  else next.add(c.url)
                  return next
                })
              }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Checkbox
                    edge="start"
                    checked={selectedRefreshUrls.has(c.url)}
                    tabIndex={-1}
                    disableRipple
                  />
                </ListItemIcon>
                <ListItemText
                  primary={c.name || c.url}
                  secondary={`${c.people_count} people | Status: ${c.status}`}
                />
              </ListItem>
            ))}
          </List>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowConfirm(false)}>Cancel</Button>
          <Button onClick={handleConfirmRescrape} variant="contained" color="warning">
            {selectedRefreshUrls.size > 0
              ? `Refresh ${selectedRefreshUrls.size} ${selectedRefreshUrls.size === 1 ? 'company' : 'companies'}`
              : 'Skip all & upload new only'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
