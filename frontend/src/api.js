import axios from 'axios';

// Use relative URLs so requests go through Django's static file serving
const api = axios.create({
  baseURL: window.location.origin,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;