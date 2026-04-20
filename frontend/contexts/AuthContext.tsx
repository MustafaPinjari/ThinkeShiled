"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import api from "@/lib/api";

export type UserRole =
  | "AUDITOR"
  | "ADMIN"
  | "AGENCY_ADMIN"
  | "AGENCY_OFFICER"
  | "REVIEWER"
  | "GOVERNMENT_AUDITOR";

interface AuthState {
  accessToken: string | null;
  role: UserRole | null;
  agencyId: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    accessToken: null,
    role: null,
    agencyId: null,
    isAuthenticated: false,
    isLoading: true,
  });

  // Rehydrate from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    const role = localStorage.getItem("user_role") as UserRole | null;
    const agencyId = localStorage.getItem("agencyId");
    setState({
      accessToken: token,
      role,
      agencyId,
      isAuthenticated: !!token,
      isLoading: false,
    });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const { data } = await api.post<{
      access: string;
      refresh: string;
      expires_in: number;
      role: UserRole;
      agency_id: string | null;
    }>("/agencies/login/", { username, password });

    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);
    localStorage.setItem("user_role", data.role);
    if (data.agency_id != null) {
      localStorage.setItem("agencyId", data.agency_id);
    } else {
      localStorage.removeItem("agencyId");
    }

    setState({
      accessToken: data.access,
      role: data.role,
      agencyId: data.agency_id ?? null,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const logout = useCallback(async () => {
    try {
      const refreshToken = localStorage.getItem("refresh_token");
      await api.post("/auth/logout/", { refresh: refreshToken });
    } catch {
      // best-effort — clear local state regardless
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user_role");
      localStorage.removeItem("agencyId");
      setState({
        accessToken: null,
        role: null,
        agencyId: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout }),
    [state, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
