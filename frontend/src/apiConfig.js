// frontend/src/apiConfig.js
const API_BASE_URL = window.location.origin;

export const ENDPOINTS = {
  SESSIONS: `${API_BASE_URL}/api/sessions/`,
  BILLS: `${API_BASE_URL}/api/bills/`,
  SPEAKERS: `${API_BASE_URL}/api/speakers/`,
  STATEMENTS: `${API_BASE_URL}/api/statements/`,
  PARTIES: `${API_BASE_URL}/api/parties/`,
  CATEGORIES: `${API_BASE_URL}/api/categories/`,
};