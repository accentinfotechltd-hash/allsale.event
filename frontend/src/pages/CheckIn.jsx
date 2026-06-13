import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { Html5Qrcode } from "html5-qrcode";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ArrowLeft, Camera, CameraOff, CheckCircle2, AlertCircle, Search, Download, RotateCcw, Users } from "lucide-react";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function CheckIn() {
  const { eventId } = useParams();
  const [params] = useSearchParams();
  const scannerToken = params.get("t") || params.get("token") || null;
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [tokenContext, setTokenContext] = useState(null); // event meta when using token mode
  const [scannerOn, setScannerOn] = useState(false);
  const [lastResult, setLastResult] = useState(null); // {kind: "success"|"already"|"error", booking?, msg?}
  const [manual, setManual] = useState("");
  const scannerRef = useRef(null);
  const lockedRef = useRef(false);

  const isTokenMode = Boolean(scannerToken);

  // When loaded via the public /scan/:eventId path, install the dedicated
  // Scanner PWA manifest so iOS/Android offers an "Add to Home Screen"
  // prompt branded as "Allsale Scanner" (separate icon from the main app).
  useEffect(() => {
    if (!window.location.pathname.startsWith("/scan/")) return;
    const id = "allsale-scanner-manifest";
    if (!document.getElementById(id)) {
      const link = document.createElement("link");
      link.id = id;
      link.rel = "manifest";
      link.href = "/scanner.webmanifest";
      document.head.appendChild(link);
    }
    const theme = document.querySelector("meta[name=theme-color]");
    const orig = theme?.getAttribute("content");
    theme?.setAttribute("content", "#0e0e10");
    return () => { if (theme && orig) theme.setAttribute("content", orig); };
  }, []);

  const loadStats = async () => {
    try {
      if (isTokenMode) {
        // Token mode: load public stats via the scanner-context endpoint
        const { data } = await api.get(`/organizer/scanner-context`, { params: { event_id: eventId, token: scannerToken } });
        setTokenContext(data);
        setStats(data.stats);
      } else {
        const { data } = await api.get(`/organizer/events/${eventId}/checkin-stats`);
        setStats(data);
      }
    } catch (e) {
      if (isTokenMode) toast.error("Invalid or revoked scanner link");
      else toast.error("Could not load stats");
    }
  };

  useEffect(() => {
    loadStats();
    const i = setInterval(loadStats, 5000);
    return () => clearInterval(i);
    // eslint-disable-next-line
  }, [eventId]);

  const startScanner = async () => {
    setScannerOn(true);
    // Wait for DOM render of reader element
    setTimeout(async () => {
      try {
        const scanner = new Html5Qrcode("qr-reader");
        scannerRef.current = scanner;
        await scanner.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 260, height: 260 } },
          (decoded) => onScan(decoded),
          () => { /* ignore per-frame errors */ }
        );
      } catch (e) {
        toast.error("Couldn't start camera. Try the manual entry below.");
        setScannerOn(false);
      }
    }, 100);
  };

  const stopScanner = async () => {
    if (scannerRef.current) {
      try { await scannerRef.current.stop(); await scannerRef.current.clear(); } catch { /* noop */ }
      scannerRef.current = null;
    }
    setScannerOn(false);
  };

  useEffect(() => () => { stopScanner(); /* cleanup on unmount */ /* eslint-disable-next-line */ }, []);

  const onScan = async (qrText) => {
    if (lockedRef.current) return;
    lockedRef.current = true;
    setTimeout(() => { lockedRef.current = false; }, 1500); // throttle 1.5s between scans
    await submitCheckin({ qr_payload: qrText });
  };

  const submitCheckin = async (payload) => {
    try {
      const body = { event_id: eventId, ...payload };
      if (isTokenMode) body.scanner_token = scannerToken;
      const { data } = await api.post("/organizer/checkin", body);
      if (data.already_checked_in) {
        setLastResult({ kind: "already", booking: data.booking });
        toast(`Already checked in: ${data.booking.user_name}`, { description: "Earlier today" });
      } else {
        setLastResult({ kind: "success", booking: data.booking });
        toast.success(`✓ Checked in ${data.booking.user_name}`);
      }
      loadStats();
    } catch (e) {
      const msg = formatApiErrorDetail(e?.response?.data?.detail) || "Check-in failed";
      setLastResult({ kind: "error", msg });
      toast.error(msg);
    }
  };

  const submitManual = (e) => {
    e.preventDefault();
    if (!manual.trim()) return;
    const t = manual.trim();
    // If looks like full QR payload, submit as qr_payload; otherwise treat as booking_id
    if (t.toUpperCase().startsWith("AURA|")) {
      submitCheckin({ qr_payload: t });
    } else {
      submitCheckin({ booking_id: t.startsWith("bkg_") ? t : `bkg_${t}` });
    }
    setManual("");
  };

  const undoLast = async () => {
    if (!lastResult?.booking) return;
    if (!window.confirm(`Undo check-in for ${lastResult.booking.user_name}?`)) return;
    try {
      await api.post(`/organizer/events/${eventId}/checkin/${lastResult.booking.booking_id}/undo`);
      toast.success("Check-in undone");
      setLastResult(null);
      loadStats();
    } catch { toast.error("Undo failed"); }
  };

  const downloadReport = async () => {
    try {
      const token = localStorage.getItem("aura_token");
      const r = await fetch(`${BACKEND}/api/organizer/events/${eventId}/attendance-report.csv`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!r.ok) throw new Error();
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `attendance_${eventId}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Report downloaded");
    } catch { toast.error("Report download failed"); }
  };

  // Stats shape differs between authed mode (rich) and token mode (compact).
  // Normalise so the four-tile dashboard renders identically in both.
  // NOTE: This hook must be called unconditionally — keep it above any early return.
  const displayStats = useMemo(() => {
    if (!stats) return null;
    if (isTokenMode) {
      const pct = stats.total ? Math.round((stats.checked_in / stats.total) * 100) : 0;
      return {
        total_bookings: stats.total,
        checked_in_count: stats.checked_in,
        no_shows_count: stats.remaining,
        percent: pct,
      };
    }
    return stats;
  }, [stats, isTokenMode]);

  if (!isTokenMode && (!user || (user.role !== "organizer" && user.role !== "admin"))) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required. <br /><span className="text-sm">Volunteers should use the dedicated scanner link shared by the organizer.</span></div>;
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {isTokenMode ? (
        <div
          className="mb-6 px-4 py-3 rounded-xl border flex items-center gap-3"
          style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
          data-testid="token-mode-banner"
        >
          <CheckCircle2 className="w-5 h-5" style={{ color: "var(--success)" }} />
          <div className="flex-1">
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Door staff mode</div>
            <div className="text-sm font-medium">
              {tokenContext?.label ? `${tokenContext.label} · ` : ""}{tokenContext?.event?.title || "Event"}
            </div>
          </div>
        </div>
      ) : (
        <Link to={`/organizer/events/${eventId}`} className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: "var(--text-muted)" }} data-testid="back-to-event">
          <ArrowLeft className="w-4 h-4" /> Back to event analytics
        </Link>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4 mb-10">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Door check-in</div>
          <h1 className="serif text-5xl">QR scanner</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>Point your camera at attendee QR codes. Scan is throttled to avoid duplicates.</p>
        </div>
        {!isTokenMode && (
          <button onClick={downloadReport} className="btn-ghost" data-testid="download-attendance-btn">
            <Download className="w-4 h-4" /> Attendance report (CSV)
          </button>
        )}
      </div>

      {/* Stats */}
      {displayStats && (
        <div className="grid sm:grid-cols-4 gap-3 mb-8">
          <Stat label="Bookings" value={displayStats.total_bookings} icon={<Users className="w-4 h-4" />} />
          <Stat label="Checked in" value={displayStats.checked_in_count} accent="var(--success)" />
          <Stat label={isTokenMode ? "Remaining" : "No-shows"} value={displayStats.no_shows_count} accent={displayStats.no_shows_count > 0 ? "var(--text-muted)" : null} />
          <Stat label="Attendance" value={`${displayStats.percent}%`} icon={<CheckCircle2 className="w-4 h-4" />} />
        </div>
      )}

      <div className="grid lg:grid-cols-[1fr_1fr] gap-6">
        {/* Scanner */}
        <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          <div className="flex items-center justify-between mb-5">
            <div>
              <div className="serif text-2xl">Scan</div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>Aim phone camera at the QR code</div>
            </div>
            {scannerOn ? (
              <button onClick={stopScanner} className="btn-ghost" data-testid="stop-scanner-btn">
                <CameraOff className="w-4 h-4" /> Stop
              </button>
            ) : (
              <button onClick={startScanner} className="btn-primary" data-testid="start-scanner-btn">
                <Camera className="w-4 h-4" /> Start camera
              </button>
            )}
          </div>

          <div id="qr-reader" style={{ minHeight: scannerOn ? 320 : 0 }} className="rounded-xl overflow-hidden" />
          {!scannerOn && (
            <div className="rounded-xl border-2 border-dashed flex flex-col items-center justify-center text-center p-10" style={{ borderColor: "var(--border-strong)", color: "var(--text-muted)", minHeight: 280 }}>
              <Camera className="w-10 h-10 mb-3" style={{ color: "var(--accent)" }} />
              <p className="font-medium mb-1">Camera off</p>
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>Click "Start camera" above to begin scanning.</p>
            </div>
          )}

          {/* Manual entry */}
          <form onSubmit={submitManual} className="mt-5">
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Manual entry (booking ID)</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="bkg_xxxxxxxx or full QR text" className="pl-10" data-testid="manual-checkin-input" />
              </div>
              <button type="submit" className="btn-ghost" data-testid="manual-checkin-submit">Check in</button>
            </div>
          </form>
        </div>

        {/* Last result + recent */}
        <div className="space-y-4">
          {lastResult && (
            <ResultCard result={lastResult} onUndo={undoLast} />
          )}

          <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <div className="serif text-xl mb-3">Recent check-ins</div>
            {!stats?.recent || stats.recent.length === 0 ? (
              <p className="text-sm py-6 text-center" style={{ color: "var(--text-dim)" }}>No check-ins yet.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {stats.recent.map((r) => (
                  <div key={r.booking_id} className="flex items-center justify-between border-b py-2" style={{ borderColor: "var(--border)" }} data-testid={`recent-${r.booking_id}`}>
                    <div>
                      <div className="text-sm font-medium">{r.user_name}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                        {r.seats?.length ? r.seats.join(", ") : r.tier_name} · {r.user_email}
                      </div>
                    </div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {new Date(r.checked_in_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, icon, accent }) {
  return (
    <div className="border rounded-2xl p-4" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        {icon && <div style={{ color: accent || "var(--accent)" }}>{icon}</div>}
      </div>
      <div className="serif text-3xl" style={{ color: accent || "var(--text)" }} data-testid={`stat-${label.toLowerCase().replace(/ /g,"-")}`}>{value}</div>
    </div>
  );
}

function ResultCard({ result, onUndo }) {
  if (result.kind === "error") {
    return (
      <div className="border rounded-2xl p-5 flex items-start gap-3" style={{ borderColor: "var(--danger)", background: "rgba(239,68,68,0.08)" }} data-testid="result-error">
        <AlertCircle className="w-5 h-5 mt-0.5" style={{ color: "var(--danger)" }} />
        <div className="flex-1">
          <div className="font-medium" style={{ color: "var(--danger)" }}>Check-in failed</div>
          <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>{result.msg}</div>
        </div>
      </div>
    );
  }
  const isAlready = result.kind === "already";
  const color = isAlready ? "var(--warn)" : "var(--success)";
  return (
    <div className="border rounded-2xl p-5 flex items-start gap-3" style={{ borderColor: color, background: isAlready ? "rgba(251,191,36,0.08)" : "rgba(52,211,153,0.08)" }} data-testid={isAlready ? "result-already" : "result-success"}>
      <CheckCircle2 className="w-5 h-5 mt-0.5" style={{ color }} />
      <div className="flex-1">
        <div className="font-medium" style={{ color }}>{isAlready ? "Already checked in" : "Checked in"}</div>
        <div className="text-sm mt-1">
          <div className="font-medium">{result.booking.user_name}</div>
          <div style={{ color: "var(--text-muted)" }}>
            {result.booking.seats?.length ? result.booking.seats.join(", ") : result.booking.tier_name} · {result.booking.user_email}
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            {new Date(result.booking.checked_in_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </div>
        </div>
      </div>
      <button onClick={onUndo} className="btn-ghost !py-1 !px-3 text-xs" data-testid="undo-checkin-btn"><RotateCcw className="w-3 h-3" /> Undo</button>
    </div>
  );
}
