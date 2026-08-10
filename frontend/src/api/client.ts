import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL } from './config';

// Define the interface for the refresh token response
interface RefreshResponse {
  access_token: string;
}

// Create a custom axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Send cookies with requests
  headers: {
    'Content-Type': 'application/json',
  },
});

// A flag to prevent multiple simultaneous refresh requests
let isRefreshing = false;
let failedQueue: { resolve: (value?: unknown) => void; reject: (reason?: any) => void }[] = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });

  failedQueue = [];
};

// State to store the token in memory
let inMemoryToken: string | null = null;

export const setToken = (token: string | null) => {
  inMemoryToken = token;
};

export const getToken = () => inMemoryToken;

// Request interceptor to attach the access token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (inMemoryToken && config.headers) {
      config.headers.Authorization = `Bearer ${inMemoryToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle 401s and silent refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // If it's not a 401, or it's a login/refresh request that failed with 401, reject immediately
    if (
      error.response?.status !== 401 ||
      originalRequest.url?.includes('/auth/login/') ||
      originalRequest.url?.includes('/auth/refresh-token/')
    ) {
      return Promise.reject(error);
    }

    if (originalRequest._retry) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise(function (resolve, reject) {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          if (originalRequest.headers && token) {
            originalRequest.headers.Authorization = 'Bearer ' + token;
          }
          return api(originalRequest);
        })
        .catch((err) => {
          return Promise.reject(err);
        });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      // Attempt to refresh the token using the HttpOnly cookie
      const { data } = await axios.post<RefreshResponse>(
        `${API_BASE_URL}/auth/refresh-token/`,
        {},
        { withCredentials: true }
      );

      // Update the in-memory token
      setToken(data.access_token);
      
      // Update the failed requests and current request with the new token
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
      }
      
      processQueue(null, data.access_token);
      return api(originalRequest);
    } catch (err) {
      processQueue(err, null);
      setToken(null);
      // Let the application handle redirecting to login (e.g. via AuthContext)
      return Promise.reject(err);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;
