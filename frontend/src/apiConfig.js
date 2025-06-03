// frontend/src/apiConfig.js
export const API_BASE_URL = process.env.REACT_APP_API_URL || window.location.origin;

export const ENDPOINTS = {
  PARTIES: '/api/parties/',
  SESSIONS: '/api/sessions/',
  BILLS: '/api/bills/',
  SPEAKERS: '/api/speakers/',
  STATEMENTS: '/api/statements/', // Assuming this might be needed later
  STATS: '/api/stats/',
  // Add more specific endpoints as needed, e.g., for detail views if params are handled separately
  // PARTY_DETAIL: (id) => `/api/parties/${id}/`,
  // SESSION_DETAIL: (id) => `/api/sessions/${id}/`,
  // BILL_DETAIL: (id) => `/api/bills/${id}/`,
  // SPEAKER_DETAIL: (id) => `/api/speakers/${id}/`,
};
