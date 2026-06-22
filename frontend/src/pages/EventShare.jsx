import { useEffect, useRef, useState, forwardRef } from "react";
import { useParams, Link } from "react-router-dom";
import { Download, ArrowLeft, Twitter, Facebook, Linkedin, MessageCircle, Send, Copy, Check, Sparkles, Package } from "lucide-react";
import { toast } from "sonner";
import { toPng } from "html-to-image";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import api from "@/lib/api";

// Pick the best background image for a flyer. Posters (portrait) take precedence
// because they're already designed for 9:16; otherwise we fall back to the
// landscape banner / cover image.
function flyerBgSrc(event) {
  return event?.poster_url || event?.banner_url || event?.image_url || "";
}

// Wait for fonts + the proxied background images inside a node to finish loading
// before we hand the DOM to html-to-image. Without this the snapshot can capture
// the canvas while the image is still a 1x1 placeholder, which looks broken.
async function waitForAssets(node) {
  try { if (document.fonts?.ready) await document.fonts.ready; } catch (_e) { /* fonts API unavailable */ }
  const imgs = node ? Array.from(node.querySelectorAll("img")) : [];
  await Promise.all(
    imgs.map(
      (img) =>
        new Promise((resolve) => {
          if (img.complete && img.naturalWidth > 0) return resolve();
          img.addEventListener("load", resolve, { once: true });
          img.addEventListener("error", resolve, { once: true });
          // Hard timeout so a single broken image can never block the export.
          setTimeout(resolve, 4000);
        }),
    ),
  );
}

/**
 * EventShare — per-event social media flyer with multi-aspect previews +
 * one-click share to major networks.
 *
 *   • Square (1:1)   → Instagram feed, Facebook
 *   • Story  (9:16)  → Instagram / TikTok story, WhatsApp status
 *   • Wide   (16:9)  → Twitter / LinkedIn / Facebook link card
 *
 * We render each preview in real HTML/CSS (no canvas), then snapshot the DOM
 * to PNG via `html-to-image` on download. This means designers can iterate
 * on the layout without re-implementing a canvas drawing pipeline.
 *
 * Share buttons open the platform's native intent URL with the event's
 * public link pre-filled — fans can paste the downloaded image into the
 * post (every platform's API limits direct image+text sharing from web).
 */
const FORMATS = [
  { key: "square", label: "Square 1:1", sub: "Instagram, Facebook", width: 1080, height: 1080, displayClass: "aspect-square" },
  { key: "story", label: "Story 9:16", sub: "IG/TikTok Story", width: 1080, height: 1920, displayClass: "aspect-[9/16]" },
  { key: "wide", label: "Wide 16:9", sub: "Twitter, LinkedIn", width: 1200, height: 675, displayClass: "aspect-video" },
];

export default function EventShare() {
  const { id } = useParams();
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState("square");
  const [copied, setCopied] = useState(false);
  const refs = useRef({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/events/${id}`);
        if (!cancelled) setEvent(data);
      } catch {
        if (!cancelled) toast.error("Event not found");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  const eventUrl = event ? `${window.location.origin}/events/${event.event_id}` : "";
  const shareText = event ? `🎟️ ${event.title} — ${formatDate(event.date)} at ${event.venue}, ${event.city}. Tickets:` : "";

  const renderToBlob = async (fmt) => {
    const node = refs.current[fmt.key];
    if (!node) return null;
    await waitForAssets(node);
    const dataUrl = await toPng(node, {
      pixelRatio: 2,
      cacheBust: true,
      backgroundColor: "#0F2A3A",
    });
    const res = await fetch(dataUrl);
    return res.blob();
  };

  const downloadFormat = async (fmt) => {
    try {
      const blob = await renderToBlob(fmt);
      if (!blob) return;
      saveAs(blob, `${slugify(event.title)}-${fmt.key}.png`);
      toast.success(`${fmt.label} flyer downloaded`);
    } catch (err) {
      console.error("flyer export failed", err);
      toast.error("Couldn't render flyer — try again");
    }
  };

  const downloadAllZip = async () => {
    const t = toast.loading("Packing all 3 flyers...");
    try {
      const zip = new JSZip();
      for (const fmt of FORMATS) {
        const blob = await renderToBlob(fmt);
        if (blob) zip.file(`${slugify(event.title)}-${fmt.key}.png`, blob);
      }
      const out = await zip.generateAsync({ type: "blob" });
      saveAs(out, `${slugify(event.title)}-flyers.zip`);
      toast.success("All 3 flyers downloaded as ZIP", { id: t });
    } catch (err) {
      console.error("ZIP export failed", err);
      toast.error("Couldn't build ZIP — try again", { id: t });
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(eventUrl);
      setCopied(true);
      toast.success("Event link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy link");
    }
  };

  const share = (network) => {
    const u = encodeURIComponent(eventUrl);
    const t = encodeURIComponent(shareText);
    const urls = {
      twitter: `https://twitter.com/intent/tweet?text=${t}&url=${u}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
      whatsapp: `https://wa.me/?text=${t}%20${u}`,
      telegram: `https://t.me/share/url?url=${u}&text=${t}`,
    };
    window.open(urls[network], "_blank", "noopener,width=600,height=540");
  };

  if (loading) return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (!event) return <div className="text-center py-20">Event not available</div>;

  const activeFmt = FORMATS.find((f) => f.key === active);

  return (
    <div className="max-w-6xl mx-auto px-4 py-10" data-testid="event-share-page">
      <Link to={`/events/${id}`} className="inline-flex items-center gap-1 text-xs mb-6 hover:opacity-80" style={{ color: "var(--text-muted)" }} data-testid="back-to-event">
        <ArrowLeft size={14} /> Back to event
      </Link>

      <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
        <Sparkles size={14} /> Social media flyer
      </div>
      <h1 className="serif text-4xl sm:text-5xl mb-2">Share <span style={{ color: "var(--accent)" }}>{event.title}</span></h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
        Download a ready-to-post flyer in three sizes, or share directly to your favorite network.
      </p>

      <div className="grid lg:grid-cols-[1fr_320px] gap-8">
        {/* Preview area */}
        <div>
          {/* Format tabs */}
          <div className="flex gap-2 mb-4 flex-wrap" role="tablist">
            {FORMATS.map((f) => (
              <button
                key={f.key}
                onClick={() => setActive(f.key)}
                className={`px-4 py-2 rounded-full text-sm border transition`}
                style={{
                  borderColor: active === f.key ? "var(--accent)" : "var(--border)",
                  background: active === f.key ? "var(--accent-soft)" : "transparent",
                  color: active === f.key ? "var(--accent)" : "var(--text)",
                }}
                data-testid={`format-tab-${f.key}`}
              >
                {f.label} <span className="opacity-60">· {f.sub}</span>
              </button>
            ))}
          </div>

          {/* Active preview — what the user sees. The wrapper has its own
              explicit visual height so the scaled FlyerCanvas inside doesn't
              bleed onto the download buttons below (negative-margin trick was
              swallowing pointer events for buttons that visually appeared
              below the flyer). */}
          {(() => {
            const w = active === "story" ? 300 : (active === "wide" ? 600 : 500);
            const ratio = activeFmt.height / activeFmt.width;
            return (
              <div
                className="relative mx-auto overflow-hidden"
                style={{ width: w, height: w * ratio }}
              >
                <FlyerCanvas
                  ref={(el) => { refs.current[active] = el; }}
                  event={event}
                  format={activeFmt}
                />
              </div>
            );
          })()}

          <div className="relative z-10 flex gap-2 mt-4 flex-wrap justify-center">
            <button
              onClick={() => downloadFormat(activeFmt)}
              className="btn-primary"
              data-testid={`download-${active}-btn`}
            >
              <Download size={14} /> Download {activeFmt.label}
            </button>
            <button onClick={downloadAllZip} className="btn-ghost" data-testid="download-all-btn">
              <Package size={14} /> Download all 3 (ZIP)
            </button>
          </div>

          {/* Hidden export-size DOM for the inactive formats so downloadAll
              works without flipping the visible tab. */}
          <div className="absolute -left-[10000px] top-0 pointer-events-none" aria-hidden="true">
            {FORMATS.filter((f) => f.key !== active).map((f) => (
              <FlyerCanvas
                key={f.key}
                ref={(el) => { refs.current[f.key] = el; }}
                event={event}
                format={f}
              />
            ))}
          </div>
        </div>

        {/* Share rail */}
        <aside>
          <div
            className="rounded-2xl border p-5 sticky top-24"
            style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
          >
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Share to</div>
            <div className="grid grid-cols-2 gap-2 mb-4">
              <ShareBtn icon={<Twitter size={14} />} label="X / Twitter" onClick={() => share("twitter")} testid="share-twitter" />
              <ShareBtn icon={<Facebook size={14} />} label="Facebook" onClick={() => share("facebook")} testid="share-facebook" />
              <ShareBtn icon={<MessageCircle size={14} />} label="WhatsApp" onClick={() => share("whatsapp")} testid="share-whatsapp" />
              <ShareBtn icon={<Linkedin size={14} />} label="LinkedIn" onClick={() => share("linkedin")} testid="share-linkedin" />
              <ShareBtn icon={<Send size={14} />} label="Telegram" onClick={() => share("telegram")} testid="share-telegram" />
              <ShareBtn icon={copied ? <Check size={14} /> : <Copy size={14} />} label={copied ? "Copied!" : "Copy link"} onClick={copyLink} testid="copy-link" />
            </div>

            <div className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>Event link</div>
            <input
              readOnly
              value={eventUrl}
              onClick={(e) => e.target.select()}
              className="font-mono text-xs"
              data-testid="event-url-input"
            />

            <div className="mt-5 text-xs" style={{ color: "var(--text-muted)" }}>
              💡 <strong>Pro tip:</strong> For Instagram, download the Story format,
              then attach the link as a Story sticker after uploading.
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ShareBtn({ icon, label, onClick, testid }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border text-xs hover:opacity-80"
      style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
      data-testid={testid}
    >
      {icon} {label}
    </button>
  );
}

// =================================================================
// FlyerCanvas — the actual designed flyer. Same component renders all
// three aspect ratios; tweaks happen via the `format` prop.
// =================================================================
const FlyerCanvas = forwardRef(function FlyerCanvas({ event, format }, ref) {
  const isStory = format.key === "story";
  const isWide = format.key === "wide";
  const isSquare = format.key === "square";

  return (
    <div
      ref={ref}
      className={`relative overflow-hidden ${format.displayClass}`}
      style={{
        // Render at target size; CSS scales it down for the preview via
        // the parent's max-width. html-to-image picks up the real px size.
        width: format.width,
        height: format.height,
        // Scale into the visible card
        transformOrigin: "top left",
        transform: `scale(${isStory ? 300 / format.width : isWide ? 1 : 500 / format.width})`,
        marginBottom: isStory ? `calc(${format.height * (300 / format.width)}px - ${format.height}px)` : isWide ? 0 : `calc(${format.height * (500 / format.width)}px - ${format.height}px)`,
        background: "#0F2A3A",
      }}
      data-testid={`flyer-canvas-${format.key}`}
    >
      {/* Background image — proxied through our backend so html-to-image can
          read the canvas pixels without tainting. The proxy adds proper CORS
          headers regardless of what the original CDN sends. Prefers a
          dedicated portrait poster for Story format, falling back to banner
          / cover image. */}
      {(() => {
        const bg = flyerBgSrc(event);
        if (!bg) return null;
        return (
          <img
            src={`${process.env.REACT_APP_BACKEND_URL}/api/img-proxy?url=${encodeURIComponent(bg)}`}
            alt=""
            crossOrigin="anonymous"
            referrerPolicy="no-referrer"
            decoding="async"
            onError={(e) => {
              if (e.currentTarget.dataset.fallback !== "1") {
                e.currentTarget.dataset.fallback = "1";
                e.currentTarget.removeAttribute("crossorigin");
                e.currentTarget.src = bg;
              }
            }}
            className="absolute inset-0 w-full h-full object-cover"
            style={{ objectPosition: "center", filter: "brightness(0.7) saturate(1.1) contrast(1.05)" }}
          />
        );
      })()}
      {/* Dark gradient + brand accent — top fade is light so the photo can breathe;
          bottom fade is heavy so text is always readable. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(15,42,58,0.15) 0%, rgba(15,42,58,0.05) 30%, rgba(15,42,58,0.55) 65%, rgba(15,42,58,0.97) 100%)",
        }}
      />
      {/* Brand accent corner */}
      <div
        className="absolute top-0 left-0"
        style={{
          width: isWide ? 12 : 16,
          height: "100%",
          background: "linear-gradient(180deg, #F08A2A 0%, #F08A2A 30%, transparent 100%)",
        }}
      />

      {/* Content */}
      <div className={`absolute inset-0 flex flex-col ${isWide ? "justify-end p-14" : "justify-end p-16"}`} style={{ color: "#FFFFFF" }}>
        <div
          style={{
            fontSize: isStory ? 22 : isWide ? 18 : 22,
            letterSpacing: "0.25em",
            color: "#F08A2A",
            fontWeight: 600,
            marginBottom: 16,
          }}
        >
          ALLSALE EVENTS · LIVE
        </div>

        <div
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: isWide ? 64 : isStory ? 110 : 84,
            lineHeight: 1.02,
            marginBottom: 24,
            maxWidth: isWide ? "80%" : "100%",
            wordBreak: "break-word",
          }}
        >
          {event.title}
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: isWide ? "row" : "column",
            gap: isWide ? 32 : 12,
            fontSize: isWide ? 22 : isStory ? 32 : 28,
            color: "rgba(255,255,255,0.92)",
            marginBottom: 32,
          }}
        >
          <div>
            <span style={{ opacity: 0.6, marginRight: 8 }}>WHEN</span>
            {formatDate(event.date)}
          </div>
          <div>
            <span style={{ opacity: 0.6, marginRight: 8 }}>WHERE</span>
            {event.venue}, {event.city}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 18,
            paddingTop: 24,
            borderTop: "2px solid rgba(255,255,255,0.18)",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div style={{ fontSize: isStory ? 22 : 14, opacity: 0.6, letterSpacing: "0.15em" }}>GET TICKETS</div>
            <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: isWide ? 32 : isStory ? 48 : 38, color: "#F08A2A", lineHeight: 1 }}>
              allsale.events
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <img
              alt=""
              width={isStory ? 180 : isWide ? 100 : 130}
              height={isStory ? 180 : isWide ? 100 : 130}
              crossOrigin="anonymous"
              decoding="async"
              src={`${process.env.REACT_APP_BACKEND_URL}/api/img-proxy?url=${encodeURIComponent(`https://api.qrserver.com/v1/create-qr-code/?size=400x400&margin=0&color=0F2A3A&bgcolor=ffffff&data=${encodeURIComponent(`${typeof window !== "undefined" ? window.location.origin : ""}/events/${event.event_id}`)}`)}`}
              style={{ borderRadius: 8, background: "#FFFFFF", padding: 6 }}
            />
            <div style={{ fontSize: isStory ? 18 : 11, opacity: 0.7 }}>SCAN</div>
          </div>
        </div>
      </div>
    </div>
  );
});

function formatDate(iso) {
  if (!iso) return "TBA";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  } catch { return "TBA"; }
}

function slugify(s) {
  return (s || "event")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}
