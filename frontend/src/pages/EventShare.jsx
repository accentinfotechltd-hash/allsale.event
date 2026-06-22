import { useEffect, useRef, useState, forwardRef } from "react";
import { useParams, Link } from "react-router-dom";
import { Download, ArrowLeft, Twitter, Facebook, Linkedin, MessageCircle, Send, Copy, Check, Sparkles, Package, Wand2, X as XIcon } from "lucide-react";
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
  // AI-generated overlay text. Null = poster-first (clean) mode. When set,
  // the flyer renders a translucent caption strip above the brand bar with the
  // headline + tagline, and the brand bar's micro-copy becomes the CTA.
  const [aiText, setAiText] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
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

  const generateAi = async () => {
    setAiBusy(true);
    try {
      const { data } = await api.post(`/events/${id}/flyer/generate-text`);
      setAiText({ headline: data.headline || "", tagline: data.tagline || "", cta: data.cta || "GRAB TICKETS" });
      toast.success("AI text added — edit any line, then download");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't generate text — try again");
    } finally {
      setAiBusy(false);
    }
  };

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

          {/* Active preview — what the user sees. Wrapper has explicit size +
              overflow:hidden; inside it a scaling div shrinks the real
              1080px flyer DOM into the visible space. html-to-image still
              snapshots the un-transformed DOM at full target resolution. */}
          {(() => {
            const w = active === "story" ? 300 : (active === "wide" ? 600 : 500);
            const h = w * (activeFmt.height / activeFmt.width);
            const scale = w / activeFmt.width;
            return (
              <div
                className="relative mx-auto overflow-hidden rounded-lg"
                style={{ width: w, height: h, background: "#0F2A3A" }}
              >
                <div style={{ transform: `scale(${scale})`, transformOrigin: "top left", width: activeFmt.width, height: activeFmt.height }}>
                  <FlyerCanvas
                    ref={(el) => { refs.current[active] = el; }}
                    event={event}
                    format={activeFmt}
                    aiText={aiText}
                  />
                </div>
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
            {!aiText ? (
              <button onClick={generateAi} disabled={aiBusy} className="btn-ghost" data-testid="ai-generate-btn">
                <Wand2 size={14} /> {aiBusy ? "Writing..." : "Add AI text overlay"}
              </button>
            ) : (
              <button onClick={() => setAiText(null)} className="btn-ghost" data-testid="ai-remove-btn">
                <XIcon size={14} /> Remove text overlay
              </button>
            )}
          </div>

          {aiText && (
            <div
              className="mt-4 rounded-xl border p-4 space-y-3"
              style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
              data-testid="ai-text-editor"
            >
              <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                  <Wand2 size={12} className="inline mr-1" /> AI flyer text · editable
                </div>
                <button onClick={generateAi} disabled={aiBusy} className="text-xs underline" style={{ color: "var(--text-muted)" }} data-testid="ai-regenerate-btn">
                  {aiBusy ? "Rewriting..." : "Regenerate"}
                </button>
              </div>
              <AiField label="Headline" value={aiText.headline} onChange={(v) => setAiText({ ...aiText, headline: v.slice(0, 60) })} maxLength={60} testid="ai-text-headline" />
              <AiField label="Tagline" value={aiText.tagline} onChange={(v) => setAiText({ ...aiText, tagline: v.slice(0, 140) })} maxLength={140} testid="ai-text-tagline" />
              <AiField label="CTA" value={aiText.cta} onChange={(v) => setAiText({ ...aiText, cta: v.slice(0, 30) })} maxLength={30} testid="ai-text-cta" />
            </div>
          )}

          {/* Hidden export-size DOM for the inactive formats so downloadAll
              works without flipping the visible tab. */}
          <div className="absolute -left-[10000px] top-0 pointer-events-none" aria-hidden="true">
            {FORMATS.filter((f) => f.key !== active).map((f) => (
              <FlyerCanvas
                key={f.key}
                ref={(el) => { refs.current[f.key] = el; }}
                event={event}
                format={f}
                aiText={aiText}
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
// FlyerCanvas — "Poster-First" layout.
//
// Organizers almost always upload a fully-designed poster (title, venue, QR,
// sponsors etc. already baked in). Stamping our own title/QR on top creates
// visual clutter and bleeds outside the box in non-portrait aspects, so we
// instead present the *full* poster inside a branded letterbox frame with a
// thin Allsale strip at the bottom carrying just the ticket URL + a scannable
// QR. Works for any source aspect ratio (object-contain).
// =================================================================
const FlyerCanvas = forwardRef(function FlyerCanvas({ event, format, aiText = null }, ref) {
  const bg = flyerBgSrc(event);

  // Bottom brand strip height proportional to the format. Bigger frames get
  // a slightly larger strip so the QR stays scannable.
  const stripHeight =
    format.key === "story" ? 240
    : format.key === "wide" ? 120
    : 160;

  const qrSize = format.key === "story" ? 180 : format.key === "wide" ? 90 : 120;
  const titleSize = format.key === "story" ? 44 : format.key === "wide" ? 28 : 36;
  const urlSize = format.key === "story" ? 56 : format.key === "wide" ? 36 : 44;

  // Headline overlay sizing — bigger on Story because it has more vertical room.
  const headlineSize = format.key === "story" ? 78 : format.key === "wide" ? 44 : 60;
  const taglineSize = format.key === "story" ? 30 : format.key === "wide" ? 20 : 24;
  const overlayPadX = format.key === "wide" ? 40 : 56;

  // Public ticket URL & QR target.
  const ticketUrl = typeof window !== "undefined" ? `${window.location.origin}/events/${event.event_id}` : "";
  const qrSrc = `${process.env.REACT_APP_BACKEND_URL}/api/img-proxy?url=${encodeURIComponent(`https://api.qrserver.com/v1/create-qr-code/?size=400x400&margin=0&color=0F2A3A&bgcolor=ffffff&data=${encodeURIComponent(ticketUrl)}`)}`;

  return (
    <div
      ref={ref}
      className="relative overflow-hidden"
      style={{
        width: format.width,
        height: format.height,
        transformOrigin: "top left",
        background: "#0F2A3A",
      }}
      data-testid={`flyer-canvas-${format.key}`}
    >
      {/* Poster area — fills everything above the brand strip. object-contain
          so the full designed poster is always visible, never cropped. The
          deep navy backdrop fills any letterbox gap. */}
      <div
        className="absolute top-0 left-0 right-0"
        style={{ bottom: stripHeight, background: "#0F2A3A" }}
      >
        {bg && (
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
            className="absolute inset-0 w-full h-full"
            style={{ objectFit: "contain", objectPosition: "center" }}
          />
        )}

        {/* AI headline overlay — only rendered when the organizer opted into
            AI text. Sits at the bottom of the image area with a vertical
            gradient so text is readable on any background photo. */}
        {aiText && (aiText.headline || aiText.tagline) && (
          <div
            className="absolute left-0 right-0 bottom-0"
            style={{
              padding: `${format.key === "wide" ? 28 : 44}px ${overlayPadX}px ${format.key === "wide" ? 24 : 36}px`,
              background:
                "linear-gradient(180deg, rgba(15,42,58,0) 0%, rgba(15,42,58,0.55) 45%, rgba(15,42,58,0.92) 100%)",
              color: "#FFFFFF",
              fontFamily: "Helvetica, Arial, sans-serif",
            }}
          >
            {aiText.headline && (
              <div
                style={{
                  fontFamily: "Georgia, 'Times New Roman', serif",
                  fontWeight: 700,
                  fontSize: headlineSize,
                  lineHeight: 1.02,
                  letterSpacing: "-0.01em",
                  textShadow: "0 4px 18px rgba(0,0,0,0.45)",
                  wordBreak: "break-word",
                }}
              >
                {aiText.headline}
              </div>
            )}
            {aiText.tagline && (
              <div
                style={{
                  marginTop: 12,
                  fontSize: taglineSize,
                  fontWeight: 400,
                  color: "rgba(255,255,255,0.88)",
                  lineHeight: 1.25,
                  maxWidth: format.key === "wide" ? "70%" : "100%",
                  textShadow: "0 2px 12px rgba(0,0,0,0.5)",
                }}
              >
                {aiText.tagline}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Brand strip — sits flush at the bottom. Solid brand color so it
          reads as part of the flyer, not an afterthought. */}
      <div
        className="absolute left-0 right-0 bottom-0 flex items-center"
        style={{
          height: stripHeight,
          background: "linear-gradient(180deg, #0B2030 0%, #0F2A3A 100%)",
          paddingLeft: format.key === "wide" ? 36 : 56,
          paddingRight: format.key === "wide" ? 36 : 56,
          borderTop: "3px solid #F08A2A",
          color: "#FFFFFF",
          fontFamily: "Helvetica, Arial, sans-serif",
          gap: 32,
        }}
      >
        {/* Left: CTA (AI mode) or "GET TICKETS AT" wordmark (poster-first mode) */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: titleSize * 0.4,
              letterSpacing: "0.32em",
              color: "#F08A2A",
              fontWeight: 700,
              marginBottom: 6,
            }}
          >
            {aiText?.cta ? aiText.cta : "GET TICKETS AT"}
          </div>
          <div
            style={{
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontWeight: 600,
              fontSize: urlSize,
              color: "#FFFFFF",
              lineHeight: 1,
              letterSpacing: "-0.01em",
            }}
          >
            allsale.events
          </div>
          <div
            style={{
              fontSize: titleSize * 0.36,
              color: "rgba(255,255,255,0.6)",
              marginTop: 8,
              letterSpacing: "0.04em",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            Scan the QR or visit the link to book
          </div>
        </div>

        {/* Right: QR */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <img
            alt=""
            width={qrSize}
            height={qrSize}
            crossOrigin="anonymous"
            decoding="async"
            src={qrSrc}
            style={{ borderRadius: 8, background: "#FFFFFF", padding: 6, display: "block" }}
          />
          <div style={{ fontSize: titleSize * 0.32, color: "#F08A2A", letterSpacing: "0.25em", fontWeight: 700 }}>SCAN</div>
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

function AiField({ label, value, onChange, maxLength, testid }) {
  return (
    <label className="block">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</span>
        <span className="text-xs" style={{ color: "var(--text-dim)" }}>{value?.length || 0}/{maxLength}</span>
      </div>
      <input
        type="text"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        maxLength={maxLength}
        className="w-full text-sm"
        data-testid={testid}
      />
    </label>
  );
}
