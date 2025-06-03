import axios from 'axios';
import { API_BASE_URL } from './apiConfig'; // Import base URL

const api = axios.create({
  baseURL: API_BASE_URL, // Use the configured base URL
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;