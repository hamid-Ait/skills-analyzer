import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import {
  Box, Typography, Paper, Button, FormControlLabel, Checkbox,
  Alert, CircularProgress, Chip,
} from '@mui/material'
import { CloudUpload, InsertDriveFile } from '@mui/icons-material'
import api from '../api/client'
import type { UploadResponse } from '../api/types'

export default function UploadPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [discover, setDiscover] = useState(true)
  const [followProfiles, setFollowProfiles] = useState(true)
  const [enrichLinkedin, setEnrichLinkedin] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

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

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError('')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('discover', String(discover))
    formData.append('follow_profiles', String(followProfiles))
    formData.append('enrich_linkedin', String(enrichLinkedin))

    try {
      const { data } = await api.post<UploadResponse>('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

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
        disabled={!file || uploading}
        onClick={handleUpload}
        startIcon={uploading ? <CircularProgress size={20} color="inherit" /> : <CloudUpload />}
        sx={{ mt: 3 }}
      >
        {uploading ? 'Uploading...' : 'Start Processing'}
      </Button>
    </Box>
  )
}
