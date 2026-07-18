import axios from "axios";

// In-memory token storage (never leaked to localStorage/sessionStorage)
let inMemoryToken: string | null = null;

export function setInMemoryToken(token: string | null) {
  inMemoryToken = token;
}

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

// Request interceptor to inject Authorization and correlation headers
api.interceptors.request.use(
  (config) => {
    // 1. Inject unique Request-Correlation-ID
    const randomHex = Math.random().toString(36).substring(2, 15);
    config.headers["X-Correlation-ID"] = `req-${randomHex}`;

    // 2. Inject JWT Token if stored in memory
    if (inMemoryToken) {
      config.headers["Authorization"] = `Bearer ${inMemoryToken}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle token refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // Check if error is 401 and request wasn't already retried
    if (
      error.response &&
      error.response.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url.includes("/auth/refresh") &&
      !originalRequest.url.includes("/auth/login")
    ) {
      originalRequest._retry = true;
      try {
        // Attempt silent refresh
        const refreshResponse = await api.post("/auth/refresh");
        const { access_token, expires_in } = refreshResponse.data;
        
        setInMemoryToken(access_token);

        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("auth-token-refreshed", {
              detail: { accessToken: access_token, expiresIn: expires_in }
            })
          );
        }
        
        // Update the authorization header for the retried request
        originalRequest.headers["Authorization"] = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // If refresh fails, clear token and reject
        setInMemoryToken(null);
        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("auth-token-refreshed", {
              detail: { accessToken: null, expiresIn: null }
            })
          );
        }
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);
