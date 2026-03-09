import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import UploadPage from './pages/UploadPage'
import DashboardPage from './pages/DashboardPage'
import CompanyDetailPage from './pages/CompanyDetailPage'
import AnalyticsPage from './pages/AnalyticsPage'
import GlobalSearchPage from './pages/GlobalSearchPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/dashboard/:jobId" element={<DashboardPage />} />
        <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/search" element={<GlobalSearchPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
