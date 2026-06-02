import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Search, LogOut, ShieldCheck, LayoutDashboard, Ticket, Sparkles, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import Logo from "@/components/Logo";

/**
 * Site shell with a fully responsive header.
 *  • Desktop (≥md):  inline search + nav links.
 *  • Mobile (<md):   compact logo + hamburger menu that slides over the page.
 *  • Foldables:      uses max-width container + safe-area-inset padding so
 *                    nothing gets cut off in unfolded landscape mode.
 */
export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const onSearch = (e) => {
    e.preventDefault();
    navigate(`/events?q=${encodeURIComponent(q)}`);
    setMenuOpen(false);
  };

  // Close the mobile menu when route changes.
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  // Lock body scroll while the mobile menu is open.
  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [menuOpen]);

  return (
    <div className="min-h-screen grain">
      <header className="sticky top-0 z-50 glass border-b" style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex items-center gap-3 sm:gap-6">
          <Link to="/" className="inline-flex items-center flex-shrink-0" data-testid="brand-link">
            <span className="sm:hidden inline-flex"><Logo size={56} /></span>
            <span className="hidden sm:inline-flex"><Logo size={72} /></span>
          </Link>

          {/* Desktop search */}
          <form onSubmit={onSearch} className="flex-1 max-w-xl hidden md:block">
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search events, artists, venues..."
                className="pl-10 w-full"
                data-testid="nav-search-input"
              />
            </div>
          </form>

          {/* Desktop / tablet nav */}
          <nav className="hidden sm:flex items-center gap-1 md:gap-2 ml-auto">
            <Link
              to="/events"
              className={`px-2 md:px-3 py-2 text-sm transition hover:opacity-80 ${location.pathname === "/events" ? "font-semibold" : ""}`}
              style={{ color: location.pathname === "/events" ? "var(--text)" : "var(--text-muted)" }}
              data-testid="nav-events-link"
            >
              Browse
            </Link>
            {user ? (
              <>
                {user.role === "organizer" && (
                  <Link to="/organizer" className="px-2 md:px-3 py-2 text-sm inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-organizer-link">
                    <LayoutDashboard className="w-4 h-4" /> <span className="hidden md:inline">Organizer</span>
                  </Link>
                )}
                {user.role === "attendee" && (
                  <Link to="/become-organizer" className="px-2 md:px-3 py-2 text-sm hidden md:inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-host-link">
                    <Sparkles className="w-4 h-4" /> Host an event
                  </Link>
                )}
                {user.role === "admin" && (
                  <Link to="/admin" className="px-2 md:px-3 py-2 text-sm inline-flex items-center gap-1.5" style={{ color: "var(--text-muted)" }} data-testid="nav-admin-link">
                    <ShieldCheck className="w-4 h-4" /> <span className="hidden md:inline">Admin</span>
                  </Link>
                )}
                <Link to="/profile" className="btn-ghost !py-2 !px-3 md:!px-4 text-sm" data-testid="nav-profile-link">
                  <Ticket className="w-4 h-4" /> <span className="hidden md:inline">My Tickets</span>
                </Link>
                <button onClick={logout} className="p-2 text-sm" style={{ color: "var(--text-dim)" }} data-testid="nav-logout-btn" title="Log out">
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="px-3 py-2 text-sm" style={{ color: "var(--text-muted)" }} data-testid="nav-login-link">Sign in</Link>
                <Link to="/signup" className="btn-primary !py-2 !px-4 md:!px-5 text-sm" data-testid="nav-signup-link">Get Started</Link>
              </>
            )}
          </nav>

          {/* Mobile hamburger */}
          <button
            type="button"
            className="sm:hidden ml-auto p-2 rounded-lg"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            data-testid="nav-mobile-toggle"
          >
            {menuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile slide-down menu */}
        {menuOpen && (
          <div className="sm:hidden border-t" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="nav-mobile-menu">
            <form onSubmit={onSearch} className="px-4 pt-4 pb-2">
              <div className="relative">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search events..."
                  className="pl-10 w-full"
                  data-testid="nav-search-input-mobile"
                />
              </div>
            </form>
            <div className="flex flex-col px-2 pb-4">
              <MobileLink to="/events" label="Browse events" testid="m-nav-events" />
              {user ? (
                <>
                  {user.role === "organizer" && <MobileLink to="/organizer" label="Organizer dashboard" icon={<LayoutDashboard className="w-4 h-4" />} testid="m-nav-organizer" />}
                  {user.role === "attendee" && <MobileLink to="/become-organizer" label="Host an event" icon={<Sparkles className="w-4 h-4" />} testid="m-nav-host" />}
                  {user.role === "admin" && <MobileLink to="/admin" label="Admin" icon={<ShieldCheck className="w-4 h-4" />} testid="m-nav-admin" />}
                  <MobileLink to="/profile" label="My tickets" icon={<Ticket className="w-4 h-4" />} testid="m-nav-profile" />
                  <button onClick={() => { logout(); setMenuOpen(false); }} className="text-left px-3 py-3 rounded-lg text-sm flex items-center gap-2" style={{ color: "var(--text-dim)" }} data-testid="m-nav-logout">
                    <LogOut className="w-4 h-4" /> Log out
                  </button>
                </>
              ) : (
                <>
                  <MobileLink to="/login" label="Sign in" testid="m-nav-login" />
                  <MobileLink to="/signup" label="Get Started" testid="m-nav-signup" primary />
                </>
              )}
            </div>
          </div>
        )}
      </header>

      <main>{children}</main>

      <footer className="border-t mt-16 md:mt-24" style={{ borderColor: "var(--border)", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 md:py-12 grid sm:grid-cols-2 md:grid-cols-4 gap-8">
          <div>
            <div className="mb-2"><Logo size={72} /></div>
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

function MobileLink({ to, label, icon, testid, primary = false }) {
  return (
    <Link
      to={to}
      className={`px-3 py-3 rounded-lg text-sm flex items-center gap-2 transition ${primary ? "font-medium" : ""}`}
      style={{ color: primary ? "var(--accent)" : "var(--text)", background: primary ? "rgba(13,148,136,0.08)" : "transparent" }}
      data-testid={testid}
    >
      {icon}{label}
    </Link>
  );
}
