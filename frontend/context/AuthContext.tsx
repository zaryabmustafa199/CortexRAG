"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<string | null>;
}

const AuthContext = React.createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [accessToken, setAccessToken] = React.useState<string | null>(null);
  const [expiresIn, setExpiresIn] = React.useState<number | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const router = useRouter();
  const pathname = usePathname();

  /**
   * Centralised post-auth state update.
   * Called after both login and register succeed.
   * Keeps the in-memory token singleton (lib/api.ts) in sync with
   * React state so the axios interceptor always has the latest token.
   */
  const handleAuthSuccess = (data: { user: User; access_token: string; expires_in: number }) => {
    setUser(data.user);
    setAccessToken(data.access_token);
    setExpiresIn(data.expires_in);
    setIsLoading(false);
  };

  // Silent refresh logic
  const refreshSession = React.useCallback(async (): Promise<string | null> => {
    try {
      const response = await api.post("/auth/refresh");
      const { access_token, expires_in } = response.data;
      
      // Update global in-memory token variable (defined in lib/api.ts)
      const { setInMemoryToken } = await import("@/lib/api");
      setInMemoryToken(access_token);

      setAccessToken(access_token);
      setExpiresIn(expires_in);
      
      // Fetch user profile after refresh to populate state
      // (Refresh endpoint only returns access_token and expires_in)
      const userResponse = await api.get("/users/me");
      setUser(userResponse.data);
      
      return access_token;
    } catch {
      // Clear session if refresh fails
      setUser(null);
      setAccessToken(null);
      setExpiresIn(null);
      const { setInMemoryToken } = await import("@/lib/api");
      setInMemoryToken(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Login handler
  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await api.post("/auth/login", { email, password });
      const { user, access_token, expires_in } = response.data;
      
      // Sync the in-memory axios token before updating React state
      const { setInMemoryToken } = await import("@/lib/api");
      setInMemoryToken(access_token);

      // Delegate all state updates to the shared helper
      handleAuthSuccess({ user, access_token, expires_in });
      router.push("/dashboard");
    } catch (error) {
      setIsLoading(false);
      throw error;
    }
  };

  // Register handler
  const register = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await api.post("/auth/register", { email, password });
      const { user, access_token, expires_in } = response.data;

      // Sync the in-memory axios token before updating React state
      const { setInMemoryToken } = await import("@/lib/api");
      setInMemoryToken(access_token);

      // Delegate all state updates to the shared helper
      handleAuthSuccess({ user, access_token, expires_in });
      router.push("/dashboard");
    } catch (error) {
      setIsLoading(false);
      throw error;
    }
  };

  // Logout handler
  const logout = async () => {
    setIsLoading(true);
    try {
      await api.post("/auth/logout");
    } catch {
      // Proceed with local cleanup even if backend request fails
    } finally {
      setUser(null);
      setAccessToken(null);
      setExpiresIn(null);
      const { setInMemoryToken } = await import("@/lib/api");
      setInMemoryToken(null);
      setIsLoading(false);
      router.push("/login");
    }
  };

  // Listen to silent refresh updates from Axios interceptor
  React.useEffect(() => {
    const handleTokenRefreshed = (e: Event) => {
      const { accessToken: newAccess, expiresIn: newExpires } = (e as CustomEvent).detail;
      setAccessToken(newAccess);
      setExpiresIn(newExpires);
      if (newAccess === null) {
        setUser(null);
      }
    };
    window.addEventListener("auth-token-refreshed", handleTokenRefreshed);
    return () => window.removeEventListener("auth-token-refreshed", handleTokenRefreshed);
  }, []);

  // Initial mount: try silent refresh
  React.useEffect(() => {
    const timer = setTimeout(() => {
      refreshSession();
    }, 0);
    return () => clearTimeout(timer);
  }, [refreshSession]);

  // Periodic silent refresh timer before expiry
  React.useEffect(() => {
    if (!accessToken || !expiresIn) return;
    
    // Refresh 1 minute before expiry
    const delay = (expiresIn - 60) * 1000;
    if (delay <= 0) return;

    const timer = setTimeout(() => {
      refreshSession();
    }, delay);

    return () => clearTimeout(timer);
  }, [accessToken, expiresIn, refreshSession]);

  // Route protection gate
  React.useEffect(() => {
    if (isLoading) return;
    
    const publicPaths = ["/login", "/register"];
    const isPublicPath = publicPaths.includes(pathname);

    if (!accessToken && !isPublicPath) {
      router.push("/login");
    } else if (accessToken && isPublicPath) {
      router.push("/dashboard");
    }
  }, [accessToken, isLoading, pathname, router]);

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated: !!accessToken,
        isLoading,
        login,
        register,
        logout,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
