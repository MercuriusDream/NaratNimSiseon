import axios from 'axios';
import { API_BASE_URL } from './apiConfig'; // Import base URL

const api = axios.create({
  baseURL: API_BASE_URL, // Use the configured base URL
  headers: {
    'Content-Type': 'application/json',
  },
});

// Cache for sessions to avoid redundant API calls
const sessionsCache = new Map();
const CACHE_DURATION = 30000; // 30 seconds

// Fetch sessions with optional filters
export const fetchSessions = async (filters = {}) => {
  try {
    // Create cache key from filters
    const cacheKey = JSON.stringify(filters);
    const cached = sessionsCache.get(cacheKey);

    // Return cached data if still valid
    if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
      return cached.data;
    }

    const params = new URLSearchParams();
    if (filters.era_co) params.append('era_co', filters.era_co);
    if (filters.sess) params.append('sess', filters.sess);
    if (filters.dgr) params.append('dgr', filters.dgr);
    if (filters.date_from) params.append('date_from', filters.date_from);
    if (filters.date_to) params.append('date_to', filters.date_to);

    // Add page size limit to reduce data transfer
    params.append('page_size', '20');

    const response = await api.get(`/sessions/?${params}`);

    // Cache the response
    sessionsCache.set(cacheKey, {
      data: response.data,
      timestamp: Date.now()
    });

    return response.data;
  } catch (error) {
    console.error('Error fetching sessions:', error);
    throw error;
  }
};

export default api;