import { useState } from "react";
import { Link2, Copy } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * UtmLinkGenerator
 * Lets organizers wrap their event URL with utm_* params (for Google Ads,
 * Facebook Ads, email blasts) and optionally bind an affiliate code so
 * paid-traffic conversions still attribute commission to the right partner.
 */
export default function UtmLinkGenerator({ event, affiliateCodes = [] }) {
  const origin = typeof window !== "undefined" ? window.location.origin : "https://www.allsale.events";
  const defaultUrl = event ? `${origin}/events/${event.event_id}` : "";
  const [form, setForm] = useState({
    base_url: defaultUrl,
    source: "facebook",
    medium: "paid",
    campaign: event ? `${event.title?.slice(0, 40)?.replace(/\s+/g, "_").toLowerCase() || "launch"}` : "launch",
    content: "",
    affiliate_code: "",
  });
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);

  const generate = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/organizer/utm-link", {
        ...form,
        affiliate_code: form.affiliate_code || undefined,
      });
      setResult(data.url);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't generate link");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border p-5" style={{ background: "var(--surface)", borderColor: "var(--border)" }} data-testid="utm-generator">
      <div className="flex items-center gap-2 mb-1">
        <Link2 size={16} />
        <div className="font-medium">UTM link generator</div>
      </div>
      <p className="text-xs opacity-60 mb-4">Build trackable URLs for paid ads (Facebook, Google, email blasts).</p>

      <form onSubmit={generate} className="space-y-3">
        <Field label="Destination URL" value={form.base_url} onChange={(v) => setForm({ ...form, base_url: v })} testid="utm-base-url" />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Source" hint="facebook / google / newsletter" value={form.source} onChange={(v) => setForm({ ...form, source: v })} testid="utm-source" />
          <Field label="Medium" hint="paid / organic / email" value={form.medium} onChange={(v) => setForm({ ...form, medium: v })} testid="utm-medium" />
        </div>
        <Field label="Campaign" value={form.campaign} onChange={(v) => setForm({ ...form, campaign: v })} testid="utm-campaign" />
        <Field label="Content (optional)" hint="e.g. video-ad-v2" value={form.content} onChange={(v) => setForm({ ...form, content: v })} testid="utm-content" />

        {affiliateCodes.length > 0 && (
          <div>
            <label className="text-xs opacity-70 block mb-1">Tag with affiliate (optional)</label>
            <select
              value={form.affiliate_code}
              onChange={(e) => setForm({ ...form, affiliate_code: e.target.value })}
              className="w-full rounded-lg border px-3 py-2 text-sm bg-transparent"
              style={{ borderColor: "var(--border)" }}
              data-testid="utm-affiliate-select"
            >
              <option value="" style={{ background: "var(--surface)" }}>— None —</option>
              {affiliateCodes.map((c) => (
                <option key={c.code} value={c.code} style={{ background: "var(--surface)" }}>
                  {c.code} ({c.partner_name})
                </option>
              ))}
            </select>
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          data-testid="utm-generate-btn"
          className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#000" }}
        >
          {busy ? "Generating…" : "Generate URL"}
        </button>
      </form>

      {result && (
        <div className="mt-4 rounded-lg border p-3 break-all text-xs font-mono" style={{ borderColor: "var(--border)", background: "rgba(0,0,0,0.2)" }} data-testid="utm-result">
          <div className="flex items-start gap-2">
            <span className="flex-1">{result}</span>
            <button
              onClick={() => { navigator.clipboard?.writeText(result); toast.success("Copied!"); }}
              className="flex-shrink-0 px-2 py-1 rounded border inline-flex items-center gap-1"
              style={{ borderColor: "var(--border)" }}
              data-testid="utm-copy-btn"
            >
              <Copy size={12} /> Copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, value, onChange, testid }) {
  return (
    <div>
      <label className="text-xs opacity-70 block mb-1">{label} {hint && <span className="opacity-60">— {hint}</span>}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border px-3 py-2 text-sm bg-transparent"
        style={{ borderColor: "var(--border)" }}
        data-testid={testid}
      />
    </div>
  );
}
