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
          className="rounded-2xl border p-8"
          style={{ borderColor: "var(--border)" }}
          data-testid="unsubscribe-success"
        >
          <div className="text-center">
            <CheckCircle2 className="mx-auto mb-3" size={36} style={{ color: "var(--accent)" }} />
            <h1 className="font-serif" style={{ fontSize: "1.5rem", color: "var(--text)" }}>
              You&apos;re unsubscribed.
            </h1>
            <p className="text-sm mt-2" style={{ color: "var(--text-dim)" }}>
              <strong style={{ color: "var(--text)" }}>{email}</strong> won&apos;t receive any more
              Allsale Journal updates. Sorry to see you go.
            </p>
          </div>

          <ReasonSurvey email={email} />

          <div className="text-center mt-8 pt-6 border-t" style={{ borderColor: "var(--border)" }}>
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              Clicked by mistake?
            </p>
            <button onClick={undo} className="btn-ghost mt-3" data-testid="undo-unsubscribe-btn">
              Re-subscribe
            </button>
          </div>
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

const REASONS = [
  { id: "too_many_emails", label: "Too many emails" },
  { id: "not_relevant", label: "Content isn't relevant to me" },
  { id: "never_signed_up", label: "I never signed up" },
  { id: "found_better", label: "Found a better source" },
  { id: "other", label: "Other (tell us below)" },
];

function ReasonSurvey({ email }) {
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const submit = async () => {
    if (!reason) return;
    setSubmitting(true);
    try {
      await api.post("/blog/unsubscribe/reason", { email, reason, comment: comment.trim() || null });
      setSubmitted(true);
    } catch {
      // Survey is optional — don't surface errors loudly.
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="mt-8 pt-6 border-t text-center" style={{ borderColor: "var(--border)" }} data-testid="survey-thanks">
        <p className="text-sm" style={{ color: "var(--accent)" }}>Thanks for the feedback — it helps us improve.</p>
      </div>
    );
  }

  return (
    <div className="mt-8 pt-6 border-t" style={{ borderColor: "var(--border)" }} data-testid="unsubscribe-survey">
      <div className="text-xs uppercase tracking-widest mb-3 text-center" style={{ color: "var(--text-dim)" }}>
        Optional — help us improve
      </div>
      <p className="text-sm text-center mb-4" style={{ color: "var(--text)" }}>
        Mind sharing why you&apos;re leaving?
      </p>
      <div className="space-y-2 max-w-md mx-auto">
        {REASONS.map((r) => (
          <label
            key={r.id}
            className="flex items-center gap-3 px-3 py-2 rounded-md border cursor-pointer transition"
            style={{
              borderColor: reason === r.id ? "var(--accent)" : "var(--border)",
              background: reason === r.id ? "rgba(240,138,42,0.06)" : "transparent",
            }}
            data-testid={`reason-${r.id}`}
          >
            <input
              type="radio"
              name="unsub-reason"
              value={r.id}
              checked={reason === r.id}
              onChange={() => setReason(r.id)}
              style={{ width: "16px", height: "16px", flexShrink: 0, accentColor: "var(--accent)" }}
            />
            <span className="text-sm" style={{ color: "var(--text)" }}>{r.label}</span>
          </label>
        ))}
      </div>
      {reason === "other" && (
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value.slice(0, 500))}
          placeholder="What could we have done better? (optional)"
          rows={3}
          className="w-full mt-3 px-3 py-2 rounded-md border text-sm max-w-md mx-auto block"
          style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
          data-testid="reason-comment-textarea"
        />
      )}
      <div className="text-center mt-4">
        <button
          onClick={submit}
          disabled={!reason || submitting}
          className="btn-primary text-sm"
          data-testid="submit-reason-btn"
        >
          {submitting ? "Submitting…" : "Submit feedback"}
        </button>
      </div>
    </div>
  );
}
