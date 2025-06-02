import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'https://eabf669f-492b-435b-b85a-6332b4265af5-00-2jrzkcqoqv3wb.riker.replit.dev/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;