import React, { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import { API_BASE_URL } from '../api/config';
import type { LoginResponse } from '../api/types';

interface AuthContextType {
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string; status?: number }>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = (): AuthContextType => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Access token stored in memory only — never localStorage (per FR-1.3)
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include', // sends/receives HttpOnly cookie
        body: JSON.stringify({ email, password }),
      });

      if (res.status === 423) {
        return { success: false, error: 'Account locked. Please try again in 30 minutes.', status: 423 };
      }

      if (res.status === 401) {
        return { success: false, error: 'Invalid credentials.', status: 401 };
      }

      if (!res.ok) {
        return { success: false, error: 'An unexpected error occurred.' };
      }

      const data = (await res.json()) as LoginResponse;
      setAccessToken(data.access_token);
      return { success: true };
    } catch {
      return { success: false, error: 'Network error. Please try again.' };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout/`, {
        method: 'POST',
        credentials: 'include',
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      });
    } catch {
      // Logout should always clear local state even if the API call fails
    }
    setAccessToken(null);
  }, [accessToken]);

  const refreshToken = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh-token/`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        setAccessToken(null);
        return false;
      }
      const data = (await res.json()) as LoginResponse;
      setAccessToken(data.access_token);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        isAuthenticated: !!accessToken,
        isLoading,
        login,
        logout,
        refreshToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
