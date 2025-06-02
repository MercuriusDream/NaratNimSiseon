import axios from 'axios';

// Use relative paths for API calls to work with the Django server
const api = axios.create({
  baseURL: '/api/',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
  validateStatus: function (status) {
    return status < 500; // Accept any status code less than 500
  }
});

// Add response interceptor for better error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNABORTED') {
      console.log('Request timeout');
    }
    return Promise.reject(error);
  }
);

export default api;