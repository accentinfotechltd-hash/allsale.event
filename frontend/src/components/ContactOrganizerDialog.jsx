import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Mail, X, Send } from "lucide-react";

import api, { formatApiErrorDetail } from "../lib/api";

/**
 * Pop-over dialog to contact an organizer.
 *
 * Props:
 *   organizerId  – string (required)
 *   organizerName – string (display name shown in the heading)
 *   eventId      – optional, prefilled when contacting from an event detail page
 *   eventTitle   – optional, shown for context inside the form
 *   onClose      – callback to dismiss
 *   defaultEmail – pre-fill the visitor's email (e.g. from auth)
 *   defaultName  – pre-fill the visitor's name (e.g. from auth)
 */
export default function ContactOrganizerDialog({
  organizerId,
  organizerName,
  eventId,
  eventTitle,
  onClose,
  defaultEmail = "",
  defaultName = "",
}) {
  const [name, setName] = useState(defaultName);
  const [email, setEmail] = useState(defaultEmail);
  const [subject, setSubject] = useState(eventTitle ? `About: ${eventTitle}` : "");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  // Close on Escape
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !subject.trim() || !message.trim()) {
      toast.error("Please fill in every field");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/organizers/${organizerId}/contact`, {
        from_name: name.trim(),
        from_email: email.trim(),
        subject: subject.trim(),
        message: message.trim(),
        event_id: eventId || undefined,
      });
      toast.success("Message sent — the organizer will reply to your email shortly");
      onClose?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Failed to send. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
      data-testid="contact-organizer-dialog"
    >
      <form
        onSubmit={onSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg border rounded-2xl p-8 max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-1" style={{ color: "var(--accent)" }}>
              Contact organizer
            </div>
            <h2 className="serif text-2xl">{organizerName || "Organizer"}</h2>
            {eventTitle && (
              <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                About: {eventTitle}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="p-2 -mr-2" data-testid="contact-organizer-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <label className="block">
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Your name</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
              className="w-full"
              data-testid="contact-from-name"
            />
          </label>
          <label className="block">
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Your email</div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full"
              data-testid="contact-from-email"
            />
          </label>
          <label className="block">
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Subject</div>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={200}
              required
              className="w-full"
              data-testid="contact-subject"
            />
          </label>
          <label className="block">
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Message</div>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              maxLength={4000}
              rows={6}
              required
              placeholder="Question about pricing, accessibility, group booking, refund..."
              className="w-full"
              data-testid="contact-message"
            />
            <div className="text-xs mt-1 text-right" style={{ color: "var(--text-dim)" }}>
              {message.length} / 4000
            </div>
          </label>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button type="button" onClick={onClose} className="btn-ghost" data-testid="contact-cancel">
            Cancel
          </button>
          <button type="submit" disabled={busy} className="btn-primary" data-testid="contact-submit">
            <Send className="w-4 h-4" /> {busy ? "Sending…" : "Send message"}
          </button>
        </div>
      </form>
    </div>
  );
}


/**
 * Re-usable "Contact organizer" button. Drop into event cards / detail pages /
 * organizer profile. Renders the dialog inline so callers don't need to manage
 * the open/close state themselves.
 */
export function ContactOrganizerButton({
  organizerId,
  organizerName,
  eventId,
  eventTitle,
  user,
  className,
  label = "Contact organizer",
  testid = "contact-organizer-btn",
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={className || "btn-ghost"}
        data-testid={testid}
      >
        <Mail className="w-4 h-4" /> {label}
      </button>
      {open && (
        <ContactOrganizerDialog
          organizerId={organizerId}
          organizerName={organizerName}
          eventId={eventId}
          eventTitle={eventTitle}
          defaultName={user?.name || ""}
          defaultEmail={user?.email || ""}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
