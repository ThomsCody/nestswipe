import { createContext, useContext, useState, useCallback } from "react";

interface AuthState {
  token: string | null;
  loading: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

const TOKEN_KEY = "nestswipe_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Read localStorage synchronously during init — no flash of unauthenticated state
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const loading = false;

  const login = useCallback((newToken: string) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
