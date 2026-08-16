import React, { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import api, { setToken } from '../api/client';
import type { LoginResponse, Organization } from '../api/types';

interface AuthContextType {
  accessToken: string | null;
  organization: Organization | null;
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
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await api.post<LoginResponse>('/auth/login/', { email, password });

      const { access_token, organization: org } = res.data;
      setToken(access_token);
      setAccessToken(access_token);
      setOrganization(org ?? null);
      return { success: true };
    } catch (error: any) {
      if (error.response?.status === 423) {
        return {
          success: false,
          error: error.response?.data?.detail
            ?? 'Account locked. Please try again in 30 minutes.',
          status: 423,
        };
      }
      if (error.response?.status === 403) {
        return {
          success: false,
          error: error.response?.data?.detail
            ?? 'Please verify your email address before signing in.',
          status: 403,
        };
      }
      if (error.response?.status === 401) {
        return { success: false, error: 'Invalid credentials.', status: 401 };
      }
      if (error.response?.status === 429) {
        return {
          success: false,
          error: 'Too many attempts. Please wait a moment and try again.',
          status: 429,
        };
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
    setOrganization(null);
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      const res = await api.post<LoginResponse>('/auth/refresh-token/');
      setToken(res.data.access_token);
      setAccessToken(res.data.access_token);
      if (res.data.organization) setOrganization(res.data.organization);
      return true;
    } catch {
      setToken(null);
      setAccessToken(null);
      setOrganization(null);
      return false;
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        organization,
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
