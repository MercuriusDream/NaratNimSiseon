import axios from 'axios';

// Use the current domain with port 3000 for API calls
const API_BASE_URL = window.location.protocol + '//' + window.location.hostname + ':3000';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;