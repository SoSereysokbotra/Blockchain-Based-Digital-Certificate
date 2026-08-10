import React, { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import api, { setToken } from '../api/client';
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
      const res = await api.post<LoginResponse>('/auth/login/', { email, password });
      
      const { access_token } = res.data;
      setToken(access_token);
      setAccessToken(access_token);
      return { success: true };
    } catch (error: any) {
      if (error.response?.status === 423) {
        return { success: false, error: 'Account locked. Please try again in 30 minutes.', status: 423 };
      }
      if (error.response?.status === 401) {
        return { success: false, error: 'Invalid credentials.', status: 401 };
      }
      return { success: false, error: 'An unexpected error occurred.' };
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout/');
    } catch {
      // Logout should always clear local state even if the API call fails
    }
    setToken(null);
    setAccessToken(null);
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      const res = await api.post<LoginResponse>('/auth/refresh-token/');
      setToken(res.data.access_token);
      setAccessToken(res.data.access_token);
      return true;
    } catch {
      setToken(null);
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
