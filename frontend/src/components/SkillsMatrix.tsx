import { Box, Typography, CircularProgress } from '@mui/material'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { useSkillsMatrix } from '../api/hooks'

const COLORS = [
  '#1976d2', '#7c4dff', '#00bcd4', '#4caf50', '#ff9800',
  '#f44336', '#9c27b0', '#3f51b5', '#009688', '#ff5722',
  '#607d8b', '#795548', '#e91e63',
]

export default function SkillsMatrix({ companyId }: { companyId: string }) {
  const { matrix, loading } = useSkillsMatrix(companyId)

  if (loading) return <CircularProgress />
  if (!matrix) return <Typography color="text.secondary">No data available</Typography>

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <Typography variant="body2" color="text.secondary">
          {matrix.total_people} total people | {matrix.total_analyzed} analyzed
        </Typography>
      </Box>

      {/* Category Bar Chart */}
      <Typography variant="h6" gutterBottom>
        Expertise Categories
      </Typography>
      <Box sx={{ width: '100%', height: 400, mb: 4 }}>
        <ResponsiveContainer>
          <BarChart
            data={matrix.categories}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 150, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(value: number, name: string) => [value, name === 'count' ? 'People' : name]} />
            <Bar dataKey="count" fill="#1976d2" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Box>

      {/* Top Expertise Pie */}
      {matrix.top_expertise.length > 0 && (
        <>
          <Typography variant="h6" gutterBottom>
            Top Primary Expertise
          </Typography>
          <Box sx={{ width: '100%', height: 350, mb: 4 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={matrix.top_expertise.slice(0, 10)}
                  dataKey="count"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={120}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                >
                  {matrix.top_expertise.slice(0, 10).map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </Box>
        </>
      )}

      {/* Sectors Bar Chart */}
      {matrix.sectors.length > 0 && (
        <>
          <Typography variant="h6" gutterBottom>
            Sectors
          </Typography>
          <Box sx={{ width: '100%', height: 300, mb: 4 }}>
            <ResponsiveContainer>
              <BarChart data={matrix.sectors} margin={{ top: 5, right: 30, left: 100, bottom: 5 }} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#7c4dff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Box>
        </>
      )}
    </Box>
  )
}
