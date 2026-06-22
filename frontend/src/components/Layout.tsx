/**
 * TalentGraph — Layout.tsx (rebrand)
 *
 * Drop this file into: frontend/src/components/Layout.tsx
 *
 * Font setup — pick ONE of:
 *   A) Add to frontend/index.html <head>:
 *      <link rel="preconnect" href="https://fonts.googleapis.com">
 *      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
 *      <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
 *
 *   B) Install @fontsource/sora, then in main.tsx:
 *      import '@fontsource/sora/300.css'
 *      import '@fontsource/sora/400.css'
 *      import '@fontsource/sora/600.css'
 *      import '@fontsource/sora/700.css'
 *      import '@fontsource/sora/800.css'
 *
 * SVG assets (copy to frontend/public/):
 *   logo-mark.svg       — mark only, light backgrounds
 *   logo-mark-dark.svg  — mark only, dark backgrounds (used here inline)
 */

import { ReactNode } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppBar, Toolbar, Box, Button, Container,
  ThemeProvider, createTheme, CssBaseline,
} from '@mui/material'
import { CloudUpload, Dashboard, Analytics, Search, FactCheck } from '@mui/icons-material'

// ── Theme ────────────────────────────────────────────────────────────────────
const theme = createTheme({
  palette: {
    primary: {
      main:         '#c47c14',
      light:        '#e8a030',
      dark:         '#9a6010',
      contrastText: '#ffffff',
    },
    secondary: {
      main:         '#1c1810',
      light:        '#3a3328',
      contrastText: '#faf8f5',
    },
    background: {
      default: '#faf8f5',
      paper:   '#ffffff',
    },
    text: {
      primary:   '#1c1810',
      secondary: '#8a7050',
    },
  },
  typography: {
    fontFamily: '"Sora", system-ui, sans-serif',
    h6: { fontWeight: 600, letterSpacing: '-0.015em' },
  },
  shape: { borderRadius: 6 },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          background:   '#1c1810',
          boxShadow:    'none',
          borderBottom: '1px solid #2e2618',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius:   6,
          fontFamily:    '"Sora", system-ui, sans-serif',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontFamily: '"Sora", system-ui, sans-serif' },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          fontFamily: '"Sora", system-ui, sans-serif',
          fontSize:   '0.75rem',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 500 },
      },
    },
  },
})

// ── T-as-graph mark (dark bg variant) ────────────────────────────────────────
// Amber edges + warm-white nodes — designed for the #1c1810 nav bar.
// Alternatively: <img src="/logo-mark-dark.svg" width={size} height={size} alt="" />
function TalentGraphMark({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      {/* Ghost edge — suggests network extends beyond the letterform */}
      <line
        x1="32" y1="56" x2="52" y2="47"
        stroke="#c47c14" strokeWidth="1.8" strokeLinecap="round" opacity={0.22}
      />
      {/* Crossbar */}
      <line
        x1="8"  y1="20" x2="56" y2="20"
        stroke="#c47c14" strokeWidth="2.5"  strokeLinecap="round"
      />
      {/* Stem */}
      <line
        x1="32" y1="20" x2="32" y2="56"
        stroke="#c47c14" strokeWidth="2.5"  strokeLinecap="round"
      />
      {/* Ghost node */}
      <circle cx="52" cy="47" r={4}   fill="#e8a030" opacity={0.28} />
      {/* Terminal nodes */}
      <circle cx="8"  cy="20" r={5}   fill="#e8a030" />
      <circle cx="56" cy="20" r={5}   fill="#e8a030" />
      <circle cx="32" cy="56" r={5}   fill="#e8a030" />
      {/* Junction hub (AI center) — largest */}
      <circle cx="32" cy="20" r={7.5} fill="#e8a030" />
    </svg>
  )
}

// ── Nav button ────────────────────────────────────────────────────────────────
interface NavBtnProps {
  label:    string
  icon:     ReactNode
  path:     string
  navigate: (path: string) => void
  active:   boolean
}

function NavBtn({ label, icon, path, navigate, active }: NavBtnProps) {
  return (
    <Button
      startIcon={icon}
      onClick={() => navigate(path)}
      disableRipple={false}
      sx={{
        color:      active ? '#e8a030'              : 'rgba(250,248,245,0.38)',
        fontWeight: active ? 700                    : 400,
        fontSize:   '0.8125rem',
        px:         1.5,
        '&:hover': {
          color:      '#faf8f5',
          background: 'rgba(255,255,255,0.06)',
        },
      }}
    >
      {label}
    </Button>
  )
}

// ── Layout ────────────────────────────────────────────────────────────────────
export default function Layout({ children }: { children: ReactNode }) {
  const navigate     = useNavigate()
  const { pathname } = useLocation()

  // Returns true if the current path matches `path` (prefix-safe)
  const is = (path: string) =>
    path === '/'
      ? pathname === '/'
      : pathname === path || pathname.startsWith(`${path}/`)

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />

      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>

        <AppBar position="static">
          <Toolbar>

            {/* Logo lockup ─────────────────────────────── */}
            <Box
              onClick={() => navigate('/')}
              role="link"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && navigate('/')}
              aria-label="TalentGraph home"
              sx={{
                display:       'flex',
                alignItems:    'center',
                gap:           1.25,
                mr:            3,
                cursor:        'pointer',
                userSelect:    'none',
                outline:       'none',
                borderRadius:  '6px',
                '&:focus-visible': { outline: '2px solid #c47c14', outlineOffset: '3px' },
              }}
            >
              <TalentGraphMark size={26} />
              <Box
                sx={{
                  fontFamily:    '"Sora", system-ui, sans-serif',
                  fontSize:      '0.9375rem',
                  fontWeight:    300,
                  color:         '#faf8f5',
                  letterSpacing: '-0.02em',
                  lineHeight:    1,
                }}
              >
                Talent
                <Box component="span" sx={{ fontWeight: 800 }}>Graph</Box>
              </Box>
            </Box>

            <Box sx={{ flex: 1 }} />

            {/* Nav links ───────────────────────────────── */}
            <NavBtn label="Upload"    path="/"          icon={<CloudUpload fontSize="small" />} navigate={navigate} active={is('/')} />
            <NavBtn label="Dashboard" path="/dashboard" icon={<Dashboard   fontSize="small" />} navigate={navigate} active={is('/dashboard')} />
            <NavBtn label="Analytics" path="/analytics" icon={<Analytics   fontSize="small" />} navigate={navigate} active={is('/analytics')} />
            <NavBtn label="Search"    path="/search"    icon={<Search      fontSize="small" />} navigate={navigate} active={is('/search')} />
            <NavBtn label="QA"        path="/qa"        icon={<FactCheck   fontSize="small" />} navigate={navigate} active={is('/qa')} />

          </Toolbar>
        </AppBar>

        <Container maxWidth="xl" sx={{ flex: 1, py: 3 }}>
          {children}
        </Container>

      </Box>
    </ThemeProvider>
  )
}
