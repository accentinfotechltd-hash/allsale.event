import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "./auth-api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    // Skip /me call if no token to avoid noisy 401s for anonymous visitors
    if (!localStorage.getItem("aura_token")) {
      setLoading(false);
      setUser(null);
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch (err) {
      // ONLY sign the user out on an explicit 401 (token rejected). Network
      // hiccups, CORS races, 5xxs, or returning from a third-party redirect
      // (Stripe Checkout, OAuth, etc.) used to flip them to signed-out, which
      // confused users into thinking the platform "logged them out at checkout".
      // Now we keep the token in localStorage; the next request will retry.
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        localStorage.removeItem("aura_token");
        setUser(null);
      } else {
        // Transient — leave the user signed in with their cached token. The
        // header / nav will still show their name, and the next API call
        // will refresh the user object if the server's back.
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) { /* noop */ }
    localStorage.removeItem("aura_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, checkAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
