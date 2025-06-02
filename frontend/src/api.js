import axios from 'axios';

// Base URL for the API
const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://eabf669f-492b-435b-b85a-6332b4265af5-00-2jrzkcqoqv3wb.riker.replit.dev:3000';

const api = axios.create({
  baseURL: 'https://eabf669f-492b-435b-b85a-6332b4265af5-00-2jrzkcqoqv3wb.riker.replit.dev:3000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;