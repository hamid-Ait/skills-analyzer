import { ReactNode } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppBar, Toolbar, Typography, Box, IconButton, Button, Container,
} from '@mui/material'
import { CloudUpload, Dashboard, Groups, Analytics, Search, FactCheck } from '@mui/icons-material'

export default function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="static" elevation={1}>
        <Toolbar>
          <IconButton color="inherit" onClick={() => navigate('/')} sx={{ mr: 1 }}>
            <Groups />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 600 }}>
            TalentGraph
          </Typography>
          <Button
            color="inherit"
            startIcon={<CloudUpload />}
            onClick={() => navigate('/')}
            sx={{ fontWeight: location.pathname === '/' ? 700 : 400 }}
          >
            Upload
          </Button>
          <Button
            color="inherit"
            startIcon={<Dashboard />}
            onClick={() => navigate('/dashboard')}
            sx={{ fontWeight: location.pathname.startsWith('/dashboard') ? 700 : 400 }}
          >
            Dashboard
          </Button>
          <Button
            color="inherit"
            startIcon={<Analytics />}
            onClick={() => navigate('/analytics')}
            sx={{ fontWeight: location.pathname === '/analytics' ? 700 : 400 }}
          >
            Analytics
          </Button>
          <Button
            color="inherit"
            startIcon={<Search />}
            onClick={() => navigate('/search')}
            sx={{ fontWeight: location.pathname === '/search' ? 700 : 400 }}
          >
            Search
          </Button>
          <Button
            color="inherit"
            startIcon={<FactCheck />}
            onClick={() => navigate('/qa')}
            sx={{ fontWeight: location.pathname === '/qa' ? 700 : 400 }}
          >
            QA
          </Button>
        </Toolbar>
      </AppBar>
      <Container maxWidth="xl" sx={{ flex: 1, py: 3 }}>
        {children}
      </Container>
    </Box>
  )
}
