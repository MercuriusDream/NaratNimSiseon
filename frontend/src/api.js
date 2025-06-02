import axios from 'axios';

// Use relative paths for API calls to work with the Django server
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;