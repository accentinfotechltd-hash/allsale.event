/**
 * RequireOrganizer — route guard for /organizer/*
 * - Not signed in → /login
 * - Signed in but role !== organizer/admin → /become-organizer
 * - Otherwise renders the protected child route
 */
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export default function RequireOrganizer({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Loading…</div>;
  }
  if (!user) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (user.role !== "organizer" && user.role !== "admin") {
    return <Navigate to={`/become-organizer?redirect=${encodeURIComponent(location.pathname)}`} replace />;
  }
  return children;
}
