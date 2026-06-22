import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle2, AlertTriangle, ArrowLeft } from "lucide-react";
import api from "@/lib/api";

/**
 * BlogUnsubscribe — one-click opt-out page linked from every newsletter email.
 *
 * Flow:
 *   • Land with `?email=foo@bar.com`
 *   • Show a confirm button (so a random link-prefetcher can't accidentally
 *     unsubscribe the reader — Gmail and some inbox scanners follow links
 *     to fetch previews).
 *   • POST /api/blog/unsubscribe → success state with an "Undo" path that
 *     re-subscribes by hitting the existing /blog/subscribers endpoint.
 */
export default function BlogUnsubscribe() {
  const [params] = useSearchParams();
  const email = (params.get("email") || "").trim().toLowerCase();
  const [state, setState] = useState("idle"); // idle | busy | done | error | resubscribed
  const [msg, setMsg] = useState("");

  useEffect(() => {
    document.title = "Unsubscribe — Allsale Events";
  }, []);

  const submit = async () => {
    if (!email) {
      setState("error");
      setMsg("No email address was provided in the link.");
      return;
    }
    setState("busy");
    try {
      await api.post("/blog/unsubscribe", { email });
      setState("done");
    } catch (err) {
      setState("error");
      setMsg(err?.response?.data?.detail || "Couldn't process the request — please try again.");
    }
  };

  const undo = async () => {
    setState("busy");
    try {
      await api.post("/blog/subscribers", { email, source: "unsubscribe_undo" });
      setState("resubscribed");
    } catch (err) {
      setState("error");
      setMsg(err?.response?.data?.detail || "Couldn't re-subscribe — please try again.");
    }
  };

  return (
    <div className="max-w-xl mx-auto px-4 sm:px-6 py-20" data-testid="blog-unsubscribe-page">
      <Link to="/blog" className="text-xs inline-flex items-center gap-1 mb-8" style={{ color: "var(--accent)" }}>
        <ArrowLeft size={12} /> Back to the Journal
      </Link>

      {(state === "idle" || state === "busy") && (
        <div
          className="rounded-2xl border p-8 text-center"
          style={{ borderColor: "var(--border)", background: "linear-gradient(135deg, rgba(240,138,42,0.06), rgba(15,42,58,0.04))" }}
        >
          <div className="text-xs uppercase tracking-[0.32em] mb-3" style={{ color: "var(--accent)" }}>
            The Allsale Journal
          </div>
          <h1 className="font-serif" style={{ fontSize: "1.75rem", color: "var(--text)", lineHeight: 1.2 }}>
            Unsubscribe from the newsletter?
          </h1>
          {email ? (
            <p className="text-sm mt-3" style={{ color: "var(--text-dim)" }}>
              We&apos;ll stop sending blog updates to <strong style={{ color: "var(--text)" }}>{email}</strong>.
              You can still book tickets and receive transactional emails.
            </p>
          ) : (
            <p className="text-sm mt-3" style={{ color: "var(--text-dim)" }}>
              No email found in the link. If you&apos;re trying to unsubscribe, please click the link in your email again.
            </p>
          )}
          <button
            onClick={submit}
            disabled={!email || state === "busy"}
            className="btn-primary mt-6"
            data-testid="confirm-unsubscribe-btn"
          >
            {state === "busy" ? "Working..." : "Yes, unsubscribe"}
          </button>
          <div className="mt-4">
            <Link to="/blog" className="text-xs underline" style={{ color: "var(--text-dim)" }} data-testid="keep-subscribed-link">
              No, keep me subscribed
            </Link>
          </div>
        </div>
      )}

      {state === "done" && (
        <div
          className="rounded-2xl border p-8 text-center"
          style={{ borderColor: "var(--border)" }}
          data-testid="unsubscribe-success"
        >
          <CheckCircle2 className="mx-auto mb-3" size={36} style={{ color: "var(--accent)" }} />
          <h1 className="font-serif" style={{ fontSize: "1.5rem", color: "var(--text)" }}>
            You&apos;re unsubscribed.
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>
            <strong style={{ color: "var(--text)" }}>{email}</strong> won&apos;t receive any more
            Allsale Journal updates. Sorry to see you go.
          </p>
          <p className="text-xs mt-4" style={{ color: "var(--text-dim)" }}>
            Clicked by mistake?
          </p>
          <button onClick={undo} className="btn-ghost mt-3" data-testid="undo-unsubscribe-btn">
            Re-subscribe
          </button>
        </div>
      )}

      {state === "resubscribed" && (
        <div
          className="rounded-2xl border p-8 text-center"
          style={{ borderColor: "var(--border)" }}
          data-testid="resubscribed-success"
        >
          <CheckCircle2 className="mx-auto mb-3" size={36} style={{ color: "var(--accent)" }} />
          <h1 className="font-serif" style={{ fontSize: "1.5rem", color: "var(--text)" }}>
            Welcome back!
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>
            <strong style={{ color: "var(--text)" }}>{email}</strong> is back on the list.
          </p>
        </div>
      )}

      {state === "error" && (
        <div
          className="rounded-2xl border p-8 text-center"
          style={{ borderColor: "var(--border)" }}
          data-testid="unsubscribe-error"
        >
          <AlertTriangle className="mx-auto mb-3" size={32} style={{ color: "#E74C3C" }} />
          <h1 className="font-serif" style={{ fontSize: "1.25rem", color: "var(--text)" }}>
            Something went wrong
          </h1>
          <p className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>{msg}</p>
          <button onClick={() => setState("idle")} className="btn-ghost mt-4">Try again</button>
        </div>
      )}
    </div>
  );
}
