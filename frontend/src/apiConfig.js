// frontend/src/apiConfig.js
export const API_BASE_URL = process.env.REACT_APP_API_URL || window.location.origin;

export const ENDPOINTS = {
  // Sessions
  SESSIONS: '/api/sessions/',
  SESSION_DETAIL: (id) => `/api/sessions/${id}/`,

  // Bills
  BILLS: '/api/bills/',
  BILL_DETAIL: (id) => `/api/bills/${id}/`,

  // Speakers
  SPEAKERS: '/api/speakers/',
  SPEAKER_DETAIL: (id) => `/api/speakers/${id}/`,

  // Parties
  PARTIES: '/api/parties/',
  PARTY_DETAIL: (id) => `/api/parties/${id}/`,

  // Categories
  CATEGORIES: '/api/categories/',

  // Statements
  STATEMENTS: '/api/statements/',
  STATEMENT_DETAIL: (id) => `/api/statements/${id}/`,

  // Search
  SEARCH: '/api/search/',
};