import axios from 'axios';

// Base URL for the API
const API_BASE_URL = window.location.origin + '/api';

// Use relative URL for API calls to work with current domain
const api = axios.create({
  baseURL: '/api/',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;