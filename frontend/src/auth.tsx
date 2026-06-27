import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, LOGIN_URL } from "./api";
import type { AuthMe } from "./api";

interface AuthCtx {
  me: AuthMe | null;        // null = 최초 로딩 전
  loggedIn: boolean;
  refresh: () => void;
  login: () => void;        // Bungie OAuth 시작(브라우저 네비게이션)
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<AuthMe | null>(null);

  const refresh = useCallback(() => {
    api.me().then(setMe).catch(() => setMe({ connected: false }));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = () => { window.location.href = LOGIN_URL; };

  const logout = useCallback(async () => {
    try { await api.logout(); } catch { /* ignore */ }
    setMe({ connected: false });
  }, []);

  return (
    <Ctx.Provider value={{ me, loggedIn: !!me?.connected, refresh, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within AuthProvider");
  return c;
}
