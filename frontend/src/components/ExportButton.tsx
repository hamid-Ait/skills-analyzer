import { useState } from 'react'
import { Button, Menu, MenuItem, ListItemIcon, ListItemText } from '@mui/material'
import { Download, TableChart, Code, GridOn, FolderZip } from '@mui/icons-material'

interface Props {
  companyId: string
}

export default function ExportButton({ companyId }: Props) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleExport = (format: string) => {
    setAnchorEl(null)
    const baseUrl = import.meta.env.VITE_API_URL || ''
    const url = `${baseUrl}/api/export/${companyId}?format=${format}`
    window.open(url, '_blank')
  }

  return (
    <>
      <Button
        variant="outlined"
        startIcon={<Download />}
        onClick={(e) => setAnchorEl(e.currentTarget)}
      >
        Export
      </Button>
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
      >
        <MenuItem onClick={() => handleExport('csv')}>
          <ListItemIcon><TableChart fontSize="small" /></ListItemIcon>
          <ListItemText>CSV</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => handleExport('json')}>
          <ListItemIcon><Code fontSize="small" /></ListItemIcon>
          <ListItemText>JSON</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => handleExport('xlsx')}>
          <ListItemIcon><GridOn fontSize="small" /></ListItemIcon>
          <ListItemText>Excel (XLSX)</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => handleExport('zip')}>
          <ListItemIcon><FolderZip fontSize="small" /></ListItemIcon>
          <ListItemText>ZIP (Excel + Photos)</ListItemText>
        </MenuItem>
      </Menu>
    </>
  )
}
