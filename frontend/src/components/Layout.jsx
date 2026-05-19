import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Search, User, LogOut, Calendar, ShieldCheck, LayoutDashboard, Ticket, Sparkles } from "lucide-react";
import { useState } from "react";
import Logo, { LogoMark } from "@/components/Logo";

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");

  const onSearch = (e) => {
    e.preventDefault();
    navigate(`/events?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="min-h-screen grain">
      <header className="sticky top-0 z-50 glass border-b">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-6">
          <Link to="/" className="inline-flex items-center" data-testid="brand-link">
            <Logo size={48} />
          </Link>

          <form onSubmit={onSearch} className="flex-1 max-w-xl hidden md:block">
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search events, artists, venues..."
                className="pl-10"
                data-testid="nav-search-input"
              />
            </div>
          </form>

          <nav className="flex items-center gap-2 ml-auto">
            <Link
              to="/events"
              className={`px-3 py-2 text-sm transition hover:opacity-80 ${
                location.pathname === "/events" ? "font-semibold" : ""
              }`}
              style={{ color: location.pathname === "/events" ? "var(--text)" : "var(--text-muted)" }}
              data-testid="nav-events-link"
            >
              Browse
            </Link>

            {user ? (
              <>
                {user.role === "organizer" && (
                  <Link to="/organizer" className="px-3 py-2 text-sm hidden sm:inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-organizer-link">
                    <LayoutDashboard className="w-4 h-4" /> Organizer
                  </Link>
                )}
                {user.role === "attendee" && (
                  <Link to="/become-organizer" className="px-3 py-2 text-sm hidden sm:inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-host-link">
                    <Sparkles className="w-4 h-4" /> Host an event
                  </Link>
                )}
                {user.role === "admin" && (
                  <Link to="/admin" className="px-3 py-2 text-sm hidden sm:inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-admin-link">
                    <ShieldCheck className="w-4 h-4" /> Admin
                  </Link>
                )}
                <Link to="/profile" className="btn-ghost !py-2 !px-4 text-sm" data-testid="nav-profile-link">
                  <Ticket className="w-4 h-4" /> My Tickets
                </Link>
                <button onClick={logout} className="px-3 py-2 text-sm" style={{ color: "var(--text-dim)" }} data-testid="nav-logout-btn" title="Log out">
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="px-3 py-2 text-sm" style={{ color: "var(--text-muted)" }} data-testid="nav-login-link">Sign in</Link>
                <Link to="/signup" className="btn-primary !py-2 !px-5 text-sm" data-testid="nav-signup-link">Get Started</Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>{children}</main>

      <footer className="border-t mt-24" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-7xl mx-auto px-6 py-12 grid md:grid-cols-4 gap-8">
          <div>
            <div className="mb-2"><Logo size={56} /></div>
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>The new way to discover and book unforgettable live experiences.</p>
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Discover</div>
            <ul className="space-y-2 text-sm">
              <li><Link to="/events" style={{ color: "var(--text-muted)" }}>All Events</Link></li>
              <li><Link to="/events?category=music" style={{ color: "var(--text-muted)" }}>Music</Link></li>
              <li><Link to="/events?category=sports" style={{ color: "var(--text-muted)" }}>Sports</Link></li>
              <li><Link to="/events?category=theater" style={{ color: "var(--text-muted)" }}>Theater</Link></li>
            </ul>
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>For Organizers</div>
            <ul className="space-y-2 text-sm">
              <li><Link to={user ? (user.role === "attendee" ? "/become-organizer" : "/organizer") : "/signup"} style={{ color: "var(--text-muted)" }}>Sell Tickets</Link></li>
              <li><Link to={user && user.role !== "attendee" ? "/organizer" : "/become-organizer"} style={{ color: "var(--text-muted)" }}>Dashboard</Link></li>
            </ul>
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Company</div>
            <ul className="space-y-2 text-sm">
              <li style={{ color: "var(--text-muted)" }}>About</li>
              <li style={{ color: "var(--text-muted)" }}>Contact</li>
            </ul>
          </div>
        </div>
        <div className="border-t py-6 text-center text-xs" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
          © 2026 Allsale Events. Live, loud, and limited.
        </div>
      </footer>
    </div>
  );
}
