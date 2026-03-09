import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

/**
 * Proxy LinkedIn CDN image URLs through our backend to avoid CORS/referrer blocks.
 */
export function proxyImageUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  if (url.includes('media.licdn.com')) {
    return `${API_URL}/api/image-proxy?url=${encodeURIComponent(url)}`
  }
  return url
}

export default api
