import axios from 'axios';

// Use relative URL for API calls to work with current domain
const api = axios.create({
  baseURL: '/api/',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;