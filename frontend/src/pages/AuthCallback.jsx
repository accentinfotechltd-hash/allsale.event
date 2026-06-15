import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AuthCallback() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    // Path 1: Custom Google OAuth — code grant comes back as ?code=...
    const qs = new URLSearchParams(window.location.search || "");
    const code = qs.get("code");
    if (code) {
      (async () => {
        try {
          const redirectUri = window.location.origin + "/auth/callback";
          const { data } = await api.post("/auth/google-code", { code, redirect_uri: redirectUri });
          if (data?.token) localStorage.setItem("aura_token", data.token);
          setUser(data);
          window.history.replaceState({}, "", "/");
          nav("/", { state: { user: data } });
        } catch {
          nav("/login");
        }
      })();
      return;
    }

    // Path 2: Legacy Emergent-managed flow — session_id in URL fragment.
    const hash = window.location.hash || "";
    const m = hash.match(/session_id=([^&]+)/);
    if (!m) {
      nav("/login");
      return;
    }
    const sessionId = decodeURIComponent(m[1]);

    (async () => {
      try {
        const { data } = await api.post("/auth/google-session", { session_id: sessionId });
        setUser(data);
        window.history.replaceState({}, "", "/");
        nav("/", { state: { user: data } });
      } catch {
        nav("/login");
      }
    })();
  }, [nav, setUser]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block w-8 h-8 border-2 rounded-full animate-spin mb-4" style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
        <div className="serif text-2xl">Finishing sign-in...</div>
      </div>
    </div>
  );
}
