import axios from "axios";
import { API_BASE_URL } from "./apiConfig"; // Import base URL

const api = axios.create({
  baseURL: API_BASE_URL, // Use the configured base URL
  headers: {
    "Content-Type": "application/json",
  },
});

// Cache for sessions to avoid redundant API calls
const sessionsCache = new Map();
const CACHE_DURATION = 30000; // 30 seconds

// Fetch home page data
export const fetchHomeData = async () => {
  try {
    const response = await api.get("/api/home-data/");
    return response.data;
  } catch (error) {
    console.error("Error fetching home data:", error);
    throw error;
  }
};

// Fetch overall stats
export const fetchStatsOverview = async () => {
  try {
    const response = await api.get("/api/stats-overview/");
    return response.data;
  } catch (error) {
    console.error("Error fetching stats:", error);
    throw error;
  }
};

// Fetch sentiment data
export const fetchSentimentData = async (timeRange = "all") => {
  try {
    const response = await api.get(
      `/api/analytics/sentiment/?time_range=${timeRange}`,
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching sentiment data:", error);
    throw error;
  }
};

// Fetch sessions with optional filters
export const fetchSessions = async (filters = {}) => {
  try {
    // Create cache key from filters
    const cacheKey = JSON.stringify(filters);
    const cached = sessionsCache.get(cacheKey);

    // Return cached data if still valid
    if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
      return cached.data;
    }

    const params = new URLSearchParams();
    if (filters.era_co) params.append("era_co", filters.era_co);
    if (filters.sess) params.append("sess", filters.sess);
    if (filters.dgr) params.append("dgr", filters.dgr);
    if (filters.date_from) params.append("date_from", filters.date_from);
    if (filters.date_to) params.append("date_to", filters.date_to);

    // Add page size limit to reduce data transfer
    params.append("page_size", "20");

    const response = await api.get(`/api/sessions/?${params}`);

    // Cache the response
    sessionsCache.set(cacheKey, {
      data: response.data,
      timestamp: Date.now(),
    });

    return response.data;
  } catch (error) {
    console.error("Error fetching sessions:", error);
    throw error;
  }
};

// Fetch bills
export const fetchBills = async (filters = {}) => {
  try {
    const params = new URLSearchParams();
    if (filters.name) params.append("name", filters.name);
    if (filters.session_id) params.append("session_id", filters.session_id);
    if (filters.date_from) params.append("date_from", filters.date_from);
    if (filters.date_to) params.append("date_to", filters.date_to);

    const response = await api.get(`/api/bills/?${params}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching bills:", error);
    throw error;
  }
};

// Fetch bill details
export const fetchBillDetail = async (billId) => {
  try {
    const response = await api.get(`/api/bills/${billId}/`);
    return response.data;
  } catch (error) {
    console.error("Error fetching bill detail:", error);
    throw error;
  }
};

// Fetch parties
export const fetchParties = async () => {
  try {
    const response = await api.get("/api/parties/");
    return response.data;
  } catch (error) {
    console.error("Error fetching parties:", error);
    throw error;
  }
};

// Fetch party detail
export const fetchPartyDetail = async (partyId) => {
  try {
    const response = await api.get(`/api/parties/${partyId}/`);
    return response.data;
  } catch (error) {
    console.error("Error fetching party detail:", error);
    throw error;
  }
};

// Fetch speakers
export const fetchSpeakers = async (filters = {}) => {
  try {
    const params = new URLSearchParams();
    if (filters.name) params.append("name", filters.name);
    if (filters.party) params.append("party", filters.party);
    if (filters.elecd_nm) params.append("elecd_nm", filters.elecd_nm);
    if (filters.era_co) params.append("era_co", filters.era_co);
    // Add any other new fields as filter params if needed
    if (filters.page) params.append("page", filters.page);
    // You can add more fields according to backend support
    const response = await api.get(`/api/speakers/?${params}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching speakers:", error);
    throw error;
  }
};

// Fetch speaker detail by id
export const fetchSpeakerDetail = async (speakerId) => {
  try {
    const response = await api.get(`/api/speakers/${speakerId}/`);
    return response.data;
  } catch (error) {
    console.error("Error fetching speaker detail:", error);
    throw error;
  }
};

// Fetch session detail
export const fetchSessionDetail = async (sessionId) => {
  try {
    const response = await api.get(`/api/sessions/${sessionId}/`);
    return response.data;
  } catch (error) {
    console.error("Error fetching session detail:", error);
    throw error;
  }
};

export default api;
