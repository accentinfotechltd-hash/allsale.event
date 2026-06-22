import { useState } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * BlogSubscribeForm — newsletter capture for the Allsale Journal.
 *
 * Drop it anywhere on /blog or /blog/:slug. `source` lets the admin see which
 * surface drove the signup (e.g. "blog_index" vs "blog_post:how-to-sell-out").
 *
 * Idempotent on the backend — repeat submissions of the same address don't
 * create duplicates, so we can show the same form on every page without fear.
 */
export default function BlogSubscribeForm({ source = "blog", compact = false }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/blog/subscribers", { email, source });
      setDone(true);
      if (data.status === "already_subscribed") {
        toast.success("You're already on the list — see you in your inbox!");
      } else {
        toast.success("You're in. We'll send the next story straight to your inbox.");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't subscribe — try again.");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div
        className={`rounded-2xl border p-6 text-center ${compact ? "" : "md:p-10"}`}
        style={{ borderColor: "var(--border)", background: "linear-gradient(135deg, rgba(240,138,42,0.06), rgba(15,42,58,0.04))" }}
        data-testid="blog-subscribe-success"
      >
        <CheckCircle2 className="mx-auto mb-3" size={32} style={{ color: "var(--accent)" }} />
        <div className="font-serif text-xl" style={{ color: "var(--text)" }}>
          You&apos;re on the list.
        </div>
        <p className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>
          Watch your inbox for stories, playbooks and behind-the-scenes from the live-events world.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-2xl border ${compact ? "p-5" : "p-6 md:p-10"} relative overflow-hidden`}
      style={{ borderColor: "var(--border)", background: "linear-gradient(135deg, rgba(240,138,42,0.06), rgba(15,42,58,0.04))" }}
      data-testid="blog-subscribe-form"
    >
      <div className="text-xs uppercase tracking-[0.32em] mb-2" style={{ color: "var(--accent)" }}>
        The Allsale Journal
      </div>
      <h3 className={`font-serif ${compact ? "text-xl" : "text-2xl md:text-3xl"}`} style={{ color: "var(--text)", lineHeight: 1.15 }}>
        Get the next story before anyone else.
      </h3>
      <p className="text-sm mt-2 max-w-md" style={{ color: "var(--text-dim)" }}>
        Weekly playbooks, organizer interviews, and ticketing insights from the
        New Zealand live-events scene. No spam, unsubscribe anytime.
      </p>
      <form onSubmit={submit} className={`mt-4 flex flex-col sm:flex-row gap-2 ${compact ? "" : "max-w-lg"}`}>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourcompany.com"
          aria-label="Email address"
          className="flex-1"
          data-testid="blog-subscribe-input"
        />
        <button type="submit" disabled={busy} className="btn-primary" data-testid="blog-subscribe-submit">
          {busy ? "Joining..." : "Subscribe"} <ArrowRight size={14} />
        </button>
      </form>
    </div>
  );
}
