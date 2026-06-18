import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import ImageUploader from "@/components/ImageUploader";
import SeatDesigner from "@/components/SeatDesigner";
import DateTimePicker from "@/components/DateTimePicker";
import { SUPPORTED_CURRENCIES, DEFAULT_CURRENCY, currencySymbol } from "@/lib/currencies";
import { COUNTRIES, DEFAULT_COUNTRY, currencyForCountry, timezoneForCountry } from "@/lib/countries";

const CATEGORIES = [
  { id: "movies", name: "Movies" },
  { id: "music", name: "Music" },
  { id: "comedy", name: "Comedy" },
  { id: "sports", name: "Sports" },
  { id: "theater", name: "Theater" },
  { id: "tech", name: "Tech" },
  { id: "workshops", name: "Workshops" },
  { id: "festivals", name: "Festivals" },
  { id: "arts", name: "Arts" },
];

export default function CreateEvent() {
  const nav = useNavigate();
  const { eventId } = useParams();
  const isEdit = !!eventId;
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "music",
    venue: "",
    city: "",
    country: DEFAULT_COUNTRY,
    timezone: timezoneForCountry(DEFAULT_COUNTRY),
    date: "",
    image_url: "",
    banner_url: "",
    currency: DEFAULT_CURRENCY,
    has_seatmap: false,
    seat_rows: 6,
    seat_cols: 10,
    seat_price: 50.0,
    aisles: [],
    seat_map_image_url: "",
    seatmap_curved: false,
    seatmap_numbering_rtl: false,
    seatmap_sections: [],
    seatmap_backdrop_opacity: 0.4,
    seatmap_backdrop_offset_y: 0,
    seatmap_backdrop_offset_x: 0,
    seatmap_backdrop_scale: 1,
    group_discount_min_qty: 0,
    group_discount_pct_off: 0,
    seatmap_categories: {},
    seatmap_category_prices: {},
  });
  const [tiers, setTiers] = useState([{ name: "General", price: 50.0, capacity: 200 }]);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  // Load existing event when in edit mode
  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const { data } = await api.get(`/events/${eventId}`);
        setForm({
          title: data.title || "",
          description: data.description || "",
          category: data.category || "music",
          venue: data.venue || "",
          city: data.city || "",
          country: data.country || DEFAULT_COUNTRY,
          timezone: data.timezone || timezoneForCountry(data.country || DEFAULT_COUNTRY),
          // Trim the timezone suffix for the datetime-local input
          date: data.date ? data.date.slice(0, 16) : "",
          image_url: data.image_url || "",
          banner_url: data.banner_url || "",
          currency: data.currency || DEFAULT_CURRENCY,
          has_seatmap: !!data.has_seatmap,
          seat_rows: data.seat_rows || 6,
          seat_cols: data.seat_cols || 10,
          seat_price: data.seat_price || 50,
          aisles: data.aisles || [],
          seat_map_image_url: data.seat_map_image_url || "",
          seatmap_curved: !!data.seatmap_curved,
          seatmap_numbering_rtl: !!data.seatmap_numbering_rtl,
          seatmap_sections: data.seatmap_sections || [],
          seatmap_categories: data.seatmap_categories || {},
          seatmap_category_prices: data.seatmap_category_prices || {},
          group_discount_min_qty: data?.group_discount?.min_qty || 0,
          group_discount_pct_off: data?.group_discount?.pct_off || 0,
        });
        if (Array.isArray(data.tiers) && data.tiers.length) setTiers(data.tiers);
      } catch {
        toast.error("Could not load event");
      } finally {
        setLoading(false);
      }
    })();
  }, [isEdit, eventId]);
  const [seatmapFileId, setSeatmapFileId] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [detectResult, setDetectResult] = useState(null);
  const [describeText, setDescribeText] = useState("");
  const [showDescribe, setShowDescribe] = useState(false);

  const applyAiResult = (data) => {
    setDetectResult(data);
    if (data.rows > 0 && data.cols > 0) {
      setForm((f) => ({
        ...f,
        seat_rows: data.rows,
        seat_cols: data.cols,
        aisles: data.aisles || [],
        seatmap_sections: data.sections || [],
        seatmap_categories: data.seat_categories || {},
        seatmap_curved: !!data.curved,
      }));
      const cats = data.seat_categories || {};
      const catCount = Object.values(cats).reduce((n, arr) => n + (arr?.length || 0), 0);
      const conf = Math.round((data.confidence || 0) * 100);
      toast.success(
        `Layout set: ${data.rows} × ${data.cols} seats, ${(data.aisles || []).length} aisles, ${catCount} categorised (${conf}% confidence)`
      );
      if (conf < 70) {
        // Low-confidence AI run → push the organizer to verify in the grid editor.
        toast.warning("⚠️ AI confidence is low — please verify the layout below before saving.");
      }
    } else {
      toast.message("Couldn't build a clear grid — please tweak the layout below");
    }
  };

  const detectSeatmap = async () => {
    if (!seatmapFileId) { toast.error("Upload a floor-plan image first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/detect", { file_id: seatmapFileId });
      applyAiResult(data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Detection failed — try the 'Describe in words' option below");
    } finally {
      setDetecting(false);
    }
  };

  // Fast offline text-parser — no LLM call. Try this BEFORE /describe so the
  // organizer gets instant feedback for well-structured layouts (the common case).
  const parseTextLayout = async () => {
    if (!describeText.trim()) { toast.error("Type a description first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/parse-text", { text: describeText.trim() });
      if (data.rows > 0 && data.cols > 0) {
        applyAiResult(data);
      } else {
        // Could not parse deterministically — fall back to LLM
        toast.message("Text parser couldn't figure it out — trying the AI...");
        const { data: aiData } = await api.post("/organizer/seatmap/describe", { text: describeText.trim() });
        applyAiResult(aiData);
      }
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Couldn't parse");
    } finally {
      setDetecting(false);
    }
  };

  const describeSeatmap = async () => {
    if (!describeText.trim()) { toast.error("Type a description first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/describe", { text: describeText.trim() });
      applyAiResult(data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "AI couldn't parse — try simpler wording");
    } finally {
      setDetecting(false);
    }
  };

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.image_url) { toast.error("Please upload a cover photo"); return; }
    if (!form.date) { toast.error("Please pick an event date and time"); return; }
    const parsedDate = new Date(form.date);
    if (Number.isNaN(parsedDate.getTime())) {
      toast.error("That date doesn't look right — please pick it again");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        date: parsedDate.toISOString(),
        tiers: form.has_seatmap ? [] : tiers,
        group_discount: (Number(form.group_discount_min_qty) > 0 && Number(form.group_discount_pct_off) > 0)
          ? { min_qty: Number(form.group_discount_min_qty), pct_off: Number(form.group_discount_pct_off) }
          : null,
      };
      delete payload.group_discount_min_qty;
      delete payload.group_discount_pct_off;
      // Strip undefined values from category price map (cleared inputs)
      if (payload.seatmap_category_prices) {
        payload.seatmap_category_prices = Object.fromEntries(
          Object.entries(payload.seatmap_category_prices).filter(([, v]) => v !== undefined && v !== null && v !== "")
        );
      }
      if (isEdit) {
        const { data } = await api.patch(`/events/${eventId}`, payload);
        toast.success("Event updated");
        nav(`/organizer/events/${data.event_id}`);
      } else {
        const { data } = await api.post("/events", payload);
        toast.success("Event submitted! Pending approval.");
        nav(`/events/${data.event_id}`);
      }
    } catch (err) {
      // Surface the real reason instead of a generic "something went wrong".
      // Network/CORS failures (err.response undefined) get a friendlier hint;
      // server-side validation errors come through with err.response.data.detail.
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (!err?.response) {
        toast.error("Couldn't reach the server. Check your connection and try again.");
      } else if (status === 401) {
        toast.error("Your session expired — please sign in again.");
      } else if (status === 403) {
        toast.error("You need an organizer account to post events. Visit 'Become an organizer' first.");
      } else if (status === 422) {
        toast.error(formatApiErrorDetail(detail) || "Some fields look invalid — please review and try again.");
      } else {
        toast.error(formatApiErrorDetail(detail) || `Failed (HTTP ${status || "?"})`);
      }
    } finally { setSubmitting(false); }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>{isEdit ? "Edit event" : "New event"}</div>
        <h1 className="serif text-5xl">{isEdit ? "Update the details" : "Set the stage"}</h1>
      </div>
      {loading ? (
        <div className="py-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>
      ) : (
      <form onSubmit={onSubmit} className="space-y-6" data-testid="create-event-form">
        <Field label="Cover photo">
          <ImageUploader
            value={form.image_url}
            onUploaded={(url) => { update("image_url", url); if (!form.banner_url) update("banner_url", url); }}
            label="Drop cover photo or click to upload"
            aspect="16/9"
            testid="cover-uploader"
          />
        </Field>
        <Field label="Title">
          <input required value={form.title} onChange={(e) => update("title", e.target.value)} data-testid="event-title-input" />
        </Field>
        <Field label="Description">
          <textarea required rows={4} value={form.description} onChange={(e) => update("description", e.target.value)} data-testid="event-desc-input" />
        </Field>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Category">
            <select value={form.category} onChange={(e) => update("category", e.target.value)} data-testid="event-category-select">
              {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Currency">
            <select
              value={form.currency}
              onChange={(e) => update("currency", e.target.value)}
              data-testid="event-currency-select"
            >
              {SUPPORTED_CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.flag} {c.code} — {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date & time">
            <DateTimePicker value={form.date} onChange={(v) => update("date", v)} testid="event-datetime" />
          </Field>
          <Field label="Venue">
            <input required value={form.venue} onChange={(e) => update("venue", e.target.value)} />
          </Field>
          <Field label="City">
            <input required value={form.city} onChange={(e) => update("city", e.target.value)} data-testid="event-city" />
          </Field>
          <Field label="Country">
            <select
              required
              value={form.country}
              onChange={(e) => {
                const code = e.target.value;
                // Auto-update timezone + currency when the country changes — the
                // organizer can still override afterwards.
                setForm(prev => ({
                  ...prev,
                  country: code,
                  timezone: timezoneForCountry(code),
                  // Only auto-switch currency if the user hasn't manually
                  // changed it from the previous country's default.
                  currency: prev.currency === currencyForCountry(prev.country)
                    ? currencyForCountry(code)
                    : prev.currency,
                }));
              }}
              data-testid="event-country"
            >
              {COUNTRIES.map(c => (
                <option key={c.code} value={c.code}>{c.flag} {c.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Timezone" hint="Auto-picked from country; override for events that span timezones.">
            <input
              value={form.timezone || ""}
              onChange={(e) => update("timezone", e.target.value)}
              placeholder="e.g. Pacific/Auckland"
              data-testid="event-timezone"
            />
          </Field>
        </div>

        <div className="border rounded-xl p-5 space-y-4" style={{ borderColor: "var(--border)" }}>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <div className="font-medium">Interactive seat map</div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>Use this for cinemas, theaters and assigned-seating venues.</div>
            </div>
            <input type="checkbox" className="!w-5 !h-5" checked={form.has_seatmap} onChange={(e) => update("has_seatmap", e.target.checked)} data-testid="seatmap-toggle" />
          </label>

          {form.has_seatmap && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Rows"><input type="number" min={2} max={26} value={form.seat_rows} onChange={(e) => update("seat_rows", parseInt(e.target.value) || 2)} /></Field>
                <Field label="Cols"><input type="number" min={4} max={26} value={form.seat_cols} onChange={(e) => update("seat_cols", parseInt(e.target.value) || 4)} /></Field>
                <Field label={`Default price / seat (${form.currency})`}><input type="number" step="0.01" value={form.seat_price} onChange={(e) => update("seat_price", parseFloat(e.target.value) || 0)} /></Field>
              </div>

              {/* Per-category seat prices — only meaningful once at least one
                  category has actual seats assigned, so we surface this once
                  the categories map is non-empty. */}
              {Object.values(form.seatmap_categories || {}).some((arr) => (arr || []).length > 0) && (
                <Field label="Per-category seat prices (optional)" hint="Override the default price above for specific seat types.">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="category-pricing-grid">
                    {[
                      { key: "vip", label: "VIP", icon: "👑", placeholder: "e.g. 80" },
                      { key: "premium", label: "Premium", icon: "✨", placeholder: "e.g. 60" },
                      { key: "wheelchair", label: "Wheelchair", icon: "♿", placeholder: "e.g. 40" },
                      { key: "disabled", label: "Disabled", icon: "👁", placeholder: "e.g. 40" },
                      { key: "house", label: "House (comp)", icon: "🏠", placeholder: "0" },
                    ].map((c) => {
                      const seatCount = (form.seatmap_categories?.[c.key] || []).length;
                      if (seatCount === 0) return null;
                      return (
                        <div key={c.key}>
                          <label className="text-xs uppercase tracking-widest block mb-1" style={{ color: "var(--text-dim)" }}>
                            {c.icon} {c.label} <span className="opacity-60">({seatCount})</span>
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder={c.placeholder}
                            value={form.seatmap_category_prices?.[c.key] ?? ""}
                            onChange={(e) => {
                              const v = e.target.value;
                              setForm((f) => ({
                                ...f,
                                seatmap_category_prices: {
                                  ...(f.seatmap_category_prices || {}),
                                  ...(v === "" ? { [c.key]: undefined } : { [c.key]: parseFloat(v) || 0 }),
                                },
                              }));
                            }}
                            data-testid={`category-price-${c.key}`}
                          />
                        </div>
                      );
                    })}
                  </div>
                </Field>
              )}

              <Field label="Venue floor-plan (optional)">
                <ImageUploader
                  value={form.seat_map_image_url}
                  onUploaded={(url, fileId) => {
                    update("seat_map_image_url", url);
                    setSeatmapFileId(fileId || null);
                    setDetectResult(null);
                  }}
                  label="Upload a backdrop showing your venue layout"
                  aspect="16/7"
                  testid="seatmap-uploader"
                />
                {form.seat_map_image_url && (
                  <div className="mt-3 p-3 rounded-lg space-y-3" style={{ background: "var(--bg-elev)" }}>
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="text-xs flex-1 min-w-[200px]" style={{ color: "var(--text-muted)" }}>
                        <strong style={{ color: "var(--accent)" }}>Option 1 — Auto-detect from image:</strong> let Gemini read your floor-plan. Works best for clear rectangular grids.
                      </div>
                      <button
                        type="button"
                        onClick={detectSeatmap}
                        disabled={detecting || !seatmapFileId}
                        className="btn-primary !py-2 !px-3 text-xs"
                        data-testid="detect-seatmap-btn"
                      >
                        {detecting ? "Working…" : (detectResult ? "Re-detect" : (seatmapFileId ? "Detect seats with AI" : "Re-upload to detect"))}
                      </button>
                    </div>
                    <div className="border-t pt-3" style={{ borderColor: "var(--border)" }}>
                      <button
                        type="button"
                        onClick={() => setShowDescribe((s) => !s)}
                        className="text-xs underline-offset-2 hover:underline"
                        style={{ color: "var(--accent)" }}
                        data-testid="toggle-describe-btn"
                      >
                        {showDescribe ? "Hide" : "✏️ Or just describe your layout in words (most reliable)"}
                      </button>
                      {showDescribe && (
                        <div className="mt-2 space-y-2">
                          <div className="text-[11px] p-2 rounded bg-black/20 font-mono leading-relaxed" style={{ color: "var(--text-muted)" }}>
                            <strong style={{ color: "var(--accent)" }}>Syntax:</strong> one row per line.<br />
                            <code>A: 1-15, disabled 1-5, house 6-11, disabled 12-15</code><br />
                            <code>B: 1-2 aisle, 3-12</code><br />
                            <code>C-E: 1-10</code> &nbsp;<span style={{ color: "var(--text-dim)" }}>(C, D, E same)</span><br />
                            <code>H: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled</code><br />
                            <span style={{ color: "var(--text-dim)" }}>Keywords: <strong>aisle, wheelchair, disabled, house, vip, premium</strong></span>
                          </div>
                          <textarea
                            value={describeText}
                            onChange={(e) => setDescribeText(e.target.value)}
                            rows={6}
                            className="w-full font-mono text-xs"
                            placeholder={`A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`}
                            data-testid="describe-text-input"
                          />
                          <div className="flex gap-2 flex-wrap">
                            <button
                              type="button"
                              onClick={parseTextLayout}
                              disabled={detecting || describeText.trim().length < 5}
                              className="btn-primary !py-2 !px-3 text-xs"
                              data-testid="describe-submit-btn"
                            >
                              {detecting ? "Building layout…" : "⚡ Build layout from text"}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setDescribeText(
                                  `A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`
                                );
                              }}
                              className="btn-ghost !py-2 !px-3 text-xs"
                              data-testid="load-example-btn"
                            >
                              Load Hoyts example
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {detectResult && (
                  <div className="mt-2 text-xs p-3 rounded-lg border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }} data-testid="detect-result">
                    <strong style={{ color: "var(--text)" }}>AI result:</strong> {detectResult.rows} rows × {detectResult.cols} cols ·
                    {" "}{(detectResult.aisles || []).length} aisles ·
                    {" "}{(detectResult.sections || []).length} sections ·
                    {" "}<span style={{ color: detectResult.confidence > 0.7 ? "var(--success)" : "var(--warn)" }}>{Math.round((detectResult.confidence || 0) * 100)}% confidence</span>
                    {detectResult.notes && <div className="mt-1" style={{ color: "var(--text-dim)" }}>{detectResult.notes}</div>}
                  </div>
                )}
              </Field>

              {/* AI describe-in-words is also available WITHOUT an image */}
              {!form.seat_map_image_url && (
                <Field label="No floor-plan image? Describe your layout in words">
                  <div className="text-[11px] p-2 rounded bg-black/20 font-mono leading-relaxed mb-2" style={{ color: "var(--text-muted)" }}>
                    <strong style={{ color: "var(--accent)" }}>Syntax:</strong> one row per line. Examples:<br />
                    <code>A: 1-15, disabled 1-5, house 6-11, disabled 12-15</code><br />
                    <code>B: 1-2 aisle, 3-12</code><br />
                    <code>C-E: 1-10</code> &nbsp;<span style={{ color: "var(--text-dim)" }}>(C, D, E all same)</span><br />
                    <code>H: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled</code><br />
                    <span style={{ color: "var(--text-dim)" }}>Keywords: <strong>aisle, wheelchair, disabled, house, vip, premium</strong></span>
                  </div>
                  <textarea
                    value={describeText}
                    onChange={(e) => setDescribeText(e.target.value)}
                    rows={6}
                    className="w-full font-mono text-xs"
                    placeholder={`A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`}
                    data-testid="describe-text-input-noimg"
                  />
                  <div className="flex gap-2 flex-wrap mt-2">
                    <button
                      type="button"
                      onClick={parseTextLayout}
                      disabled={detecting || describeText.trim().length < 5}
                      className="btn-primary !py-2 !px-3 text-xs"
                      data-testid="describe-submit-btn-noimg"
                    >
                      {detecting ? "Building…" : "⚡ Build layout from text"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDescribeText(
                          `A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`
                        );
                      }}
                      className="btn-ghost !py-2 !px-3 text-xs"
                      data-testid="load-example-btn-noimg"
                    >
                      Load Hoyts example
                    </button>
                  </div>
                </Field>
              )}

              <Field label="Draw the seat arrangement">
                <div className="mb-3 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    id="seatmap_numbering_rtl"
                    checked={form.seatmap_numbering_rtl}
                    onChange={(e) => update("seatmap_numbering_rtl", e.target.checked)}
                    data-testid="numbering-rtl-toggle"
                  />
                  <label htmlFor="seatmap_numbering_rtl" style={{ color: "var(--text-muted)" }}>
                    Number seats <strong>right to left</strong> (e.g. seat #1 is on the right — standard for many Indian/ME cinemas)
                  </label>
                </div>
                <SeatDesigner
                  rows={form.seat_rows}
                  cols={form.seat_cols}
                  aisles={form.aisles}
                  sections={form.seatmap_sections}
                  categories={form.seatmap_categories || {}}
                  curved={form.seatmap_curved}
                  numberingRtl={form.seatmap_numbering_rtl}
                  backdropUrl={form.seat_map_image_url}
                  backdropOpacity={form.seatmap_backdrop_opacity}
                  backdropOffsetY={form.seatmap_backdrop_offset_y}
                  backdropOffsetX={form.seatmap_backdrop_offset_x}
                  backdropScale={form.seatmap_backdrop_scale}
                  onChange={(next) => setForm((f) => ({
                    ...f,
                    aisles: next.aisles,
                    seatmap_sections: next.sections,
                    seatmap_categories: next.categories ?? f.seatmap_categories,
                    seatmap_curved: next.curved,
                    seatmap_backdrop_opacity: next.backdrop_opacity,
                    seatmap_backdrop_offset_y: next.backdrop_offset_y,
                    seatmap_backdrop_offset_x: next.backdrop_offset_x,
                    seatmap_backdrop_scale: next.backdrop_scale,
                  }))}
                />
              </Field>
              {form.seatmap_sections?.length > 0 && (
                <Field label="Section pricing (optional)">
                  <div className="rounded-xl p-4" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
                    <div className="space-y-2">
                      {form.seatmap_sections.map((s, i) => (
                        <div key={i} className="flex items-center gap-3" data-testid={`section-price-row-${i}`}>
                          <span className="text-sm flex-1 truncate">{s.label}</span>
                          <input
                            type="number" min="0" step="1"
                            placeholder={`Default: ${currencySymbol(form.currency)}${form.seat_price}`}
                            value={s.price ?? ""}
                            onChange={(e) => {
                              const v = e.target.value === "" ? null : parseFloat(e.target.value);
                              const next = [...form.seatmap_sections];
                              next[i] = { ...next[i], price: v };
                              update("seatmap_sections", next);
                            }}
                            className="w-32"
                            data-testid={`section-price-input-${i}`}
                          />
                        </div>
                      ))}
                    </div>
                    <p className="text-xs mt-3" style={{ color: "var(--text-dim)" }}>
                      Leave blank to use the base seat price for that section.
                    </p>
                  </div>
                </Field>
              )}
            </>
          )}
        </div>

        {!form.has_seatmap && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Ticket tiers</label>
              <button type="button" onClick={() => setTiers((t) => [...t, { name: "VIP", price: 100, capacity: 50 }])} className="text-xs flex items-center gap-1" style={{ color: "var(--accent)" }} data-testid="add-tier-btn">
                <Plus className="w-3 h-3" /> Add tier
              </button>
            </div>
            <div className="space-y-3">
              {tiers.map((t, i) => (
                <div key={i} className="grid grid-cols-[1fr_120px_120px_auto] gap-2">
                  <input placeholder="Name" value={t.name} onChange={(e) => { const n = [...tiers]; n[i].name = e.target.value; setTiers(n); }} />
                  <input type="number" step="0.01" placeholder={`Price (${form.currency})`} value={t.price} onChange={(e) => { const n = [...tiers]; n[i].price = parseFloat(e.target.value); setTiers(n); }} />
                  <input type="number" placeholder="Capacity" value={t.capacity} onChange={(e) => { const n = [...tiers]; n[i].capacity = parseInt(e.target.value); setTiers(n); }} />
                  <button type="button" onClick={() => setTiers((arr) => arr.filter((_, x) => x !== i))} className="px-3 rounded-lg border" style={{ borderColor: "var(--border-strong)" }}><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div data-testid="group-discount-section">
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
            Group booking discount <span className="opacity-60">(optional)</span>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <input
                type="number"
                min="0"
                placeholder="Min tickets (e.g. 10)"
                value={form.group_discount_min_qty || ""}
                onChange={(e) => update("group_discount_min_qty", parseInt(e.target.value) || 0)}
                data-testid="group-discount-min-qty"
              />
              <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>Min tickets to qualify</div>
            </div>
            <div>
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                placeholder="% off (e.g. 15)"
                value={form.group_discount_pct_off || ""}
                onChange={(e) => update("group_discount_pct_off", parseFloat(e.target.value) || 0)}
                data-testid="group-discount-pct-off"
              />
              <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>Discount % off subtotal</div>
            </div>
          </div>
          <div className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
            Buyers automatically get the discount when their cart hits the threshold. Set both to 0 to disable.
          </div>
        </div>

        <button type="submit" disabled={submitting} className="btn-primary" data-testid="submit-event-btn">
          {submitting ? (isEdit ? "Saving..." : "Submitting...") : (isEdit ? "Save changes" : "Submit for approval")}
        </button>
      </form>
      )}
    </div>
  );
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>{label}</label>
      {children}
      {hint && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{hint}</div>}
    </div>
  );
}
