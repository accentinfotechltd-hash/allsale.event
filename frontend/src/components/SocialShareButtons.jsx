import { useEffect, useState } from "react";
import { Share2, Twitter, Facebook, MessageCircle, Send, Copy } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * SocialShareButtons
 * Renders WhatsApp/Twitter/Facebook/Copy buttons that share the event.
 * If the visitor is signed in AND has joined this event's affiliate program,
 * the share URL is automatically swapped for their affiliate-tracked link
 * so any sales from that share are attributed (and commissioned) to them.
 */
export default function SocialShareButtons({ event }) {
  const { user } = useAuth();
  const [code, setCode] = useState(null);
  const baseUrl = typeof window !== "undefined" ? `${window.location.origin}/events/${event.event_id}` : "";

  useEffect(() => {
    if (!user || !event?.event_id) return;
    (async () => {
      try {
        const { data } = await api.get("/influencer/dashboard");
        const mine = (data?.campaigns || []).find((c) => c.event_id === event.event_id);
        if (mine?.code) setCode(mine.code);
      } catch {
        // not an influencer or no profile — silent
      }
    })();
  }, [user, event?.event_id]);

  const shareUrl = code
    ? `${typeof window !== "undefined" ? window.location.origin : ""}/api/affiliate/track?code=${encodeURIComponent(code)}&event_id=${encodeURIComponent(event.event_id)}`
    : baseUrl;
  const text = `${event.title} — get tickets`;

  const copy = () => {
    navigator.clipboard?.writeText(shareUrl);
    toast.success(code ? "Your affiliate link copied!" : "Link copied!");
  };

  return (
    <div className="rounded-xl border p-5" style={{ background: "var(--surface)", borderColor: "var(--border)" }} data-testid="social-share">
      <div className="flex items-center gap-2 mb-3">
        <Share2 size={16} />
        <div className="font-medium">Share this event</div>
        {code && (
          <span className="ml-auto px-2 py-0.5 rounded-full text-xs" style={{ background: "rgba(255,79,0,0.15)", color: "var(--accent)" }} data-testid="share-with-affiliate">
            With your code: {code}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <a
          href={`https://wa.me/?text=${encodeURIComponent(`${text} ${shareUrl}`)}`}
          target="_blank" rel="noopener noreferrer"
          data-testid="share-whatsapp"
          className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
          style={{ borderColor: "var(--border)" }}
        >
          <MessageCircle size={14} /> WhatsApp
        </a>
        <a
          href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(shareUrl)}`}
          target="_blank" rel="noopener noreferrer"
          data-testid="share-twitter"
          className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
          style={{ borderColor: "var(--border)" }}
        >
          <Twitter size={14} /> X / Twitter
        </a>
        <a
          href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`}
          target="_blank" rel="noopener noreferrer"
          data-testid="share-facebook"
          className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
          style={{ borderColor: "var(--border)" }}
        >
          <Facebook size={14} /> Facebook
        </a>
        <a
          href={`https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(text)}`}
          target="_blank" rel="noopener noreferrer"
          data-testid="share-telegram"
          className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
          style={{ borderColor: "var(--border)" }}
        >
          <Send size={14} /> Telegram
        </a>
        <button
          onClick={copy}
          data-testid="share-copy"
          className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
          style={{ borderColor: "var(--border)" }}
        >
          <Copy size={14} /> Copy link
        </button>
      </div>
      {!code && user && (
        <div className="text-xs opacity-60 mt-3" data-testid="share-creator-hint">
          Want to earn commission sharing this event?{" "}
          <a href="/influencer/campaigns" style={{ color: "var(--accent)" }}>Join as a creator →</a>
        </div>
      )}
    </div>
  );
}
