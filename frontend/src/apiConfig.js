// frontend/src/apiConfig.js
export const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export const ENDPOINTS = {
  HOME_DATA: `${API_BASE_URL}/api/home-data/`,
  STATS_OVERVIEW: `${API_BASE_URL}/api/stats-overview/`,
  SESSIONS: `${API_BASE_URL}/api/sessions/`,
  BILLS: `${API_BASE_URL}/api/bills/`,
  SPEAKERS: `${API_BASE_URL}/api/speakers/`,
  STATEMENTS: `${API_BASE_URL}/api/statements/`,
  PARTIES: `${API_BASE_URL}/api/parties/`,
  CATEGORIES: `${API_BASE_URL}/api/categories/`,
  ANALYTICS_OVERALL: `${API_BASE_URL}/api/analytics/overall/`,
  ANALYTICS_PARTIES: `${API_BASE_URL}/api/analytics/parties/`,
};