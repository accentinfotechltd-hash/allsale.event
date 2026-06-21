/**
 * EventMedia — renders the promo video (if any) and makes the cover banner
 * clickable to open in a fullscreen lightbox.
 *
 * Supported video sources:
 *   - YouTube (youtube.com/watch?v=, youtu.be/, /shorts/, /embed/)
 *   - Vimeo (vimeo.com/123, player.vimeo.com/video/123)
 *   - Instagram reel / post (instagram.com/reel/XXX, /p/XXX)
 *   - Direct .mp4 / .webm URL → rendered with the native <video> tag
 *
 * We do the URL→embed transformation client-side so organizers can paste
 * whatever URL they have on the clipboard without thinking about format.
 */
import { useEffect, useState } from "react";
import { X, Maximize2 } from "lucide-react";

function embedUrl(url) {
  if (!url) return null;
  const u = String(url).trim();
  // YouTube
  let m = u.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
  if (m) return { kind: "iframe", src: `https://www.youtube.com/embed/${m[1]}?rel=0` };
  // Vimeo
  m = u.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  if (m) return { kind: "iframe", src: `https://player.vimeo.com/video/${m[1]}` };
  // Instagram reel/post
  m = u.match(/instagram\.com\/(?:reel|p|tv)\/([A-Za-z0-9_-]+)/);
  if (m) return { kind: "iframe", src: `https://www.instagram.com/p/${m[1]}/embed` };
  // Direct video file
  if (/\.(mp4|webm|mov|m3u8)(\?|$)/i.test(u)) return { kind: "native", src: u };
  return null;
}

export function PromoVideoEmbed({ url }) {
  const e = embedUrl(url);
  if (!e) return null;
  return (
    <div
      className="max-w-4xl mx-auto px-4 sm:px-6 -mt-8 sm:-mt-12 relative z-10"
      data-testid="promo-video-block"
    >
      <div
        className="rounded-2xl overflow-hidden border shadow-2xl"
        style={{
          borderColor: "var(--border)",
          aspectRatio: "16 / 9",
          background: "#000",
        }}
      >
        {e.kind === "iframe" ? (
          <iframe
            src={e.src}
            title="Event promo video"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            className="w-full h-full"
            data-testid="promo-video-iframe"
          />
        ) : (
          <video
            controls
            playsInline
            preload="metadata"
            className="w-full h-full"
            data-testid="promo-video-native"
          >
            <source src={e.src} />
            Your browser doesn&apos;t support inline video. <a href={e.src}>Open video</a>.
          </video>
        )}
      </div>
    </div>
  );
}

export function BannerLightbox({ src, alt, open, onClose }) {
  // Lock body scroll while the lightbox is open so the page underneath
  // doesn't jump around when the user swipes/scrolls on the image.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.92)" }}
      data-testid="banner-lightbox"
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full"
        style={{ background: "rgba(255,255,255,0.1)", color: "#fff" }}
        aria-label="Close"
        data-testid="banner-lightbox-close"
      >
        <X className="w-6 h-6" />
      </button>
      <img
        src={src}
        alt={alt}
        className="max-w-full max-h-full object-contain rounded-lg"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

/**
 * Tiny "View full poster" overlay button — sits in the corner of the banner.
 * The whole banner is also clickable as a fallback for users on touch devices
 * where the small overlay button is hard to hit.
 */
export function BannerExpandHint() {
  return (
    <div
      className="absolute top-4 right-4 px-3 py-1.5 rounded-full text-xs inline-flex items-center gap-1.5 pointer-events-none"
      style={{ background: "rgba(0,0,0,0.55)", color: "#fff" }}
    >
      <Maximize2 className="w-3 h-3" /> View full poster
    </div>
  );
}

export default function EventMedia({ event, lightboxOpen, onLightboxClose }) {
  return (
    <>
      <PromoVideoEmbed url={event.promo_video_url} />
      <BannerLightbox
        src={event.banner_url || event.image_url}
        alt={event.title}
        open={lightboxOpen}
        onClose={onLightboxClose}
      />
    </>
  );
}
