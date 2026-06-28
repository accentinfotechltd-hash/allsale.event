import { useEffect, useState, useCallback } from "react";
import { Globe, ChevronDown } from "lucide-react";
import api from "@/lib/api";
import { COUNTRIES } from "@/lib/countries";

/**
 * Homepage country picker.
 *
 * Lets a buyer narrow the homepage feed to events in their country. We only
 * surface countries that actually have approved upcoming events (via
 * `/api/events/countries`) so the dropdown never offers an empty selection.
 *
 * The choice is persisted in `localStorage["allsale_selected_country"]` and
 * surfaced as a query param to whatever parent feed (featured / browse /
 * recommendations) needs it.
 *
 * Special value `"ALL"` = global feed.
 *
 * Props:
 *   value     – current country code ("NZ", "IN", "ALL", …)
 *   onChange  – fires (code) when the user picks a different country
 *   compact   – squashes padding for inline placement next to a search bar
 */
export default function CountryPicker({ value, onChange, compact = false }) {
  const [options, setOptions] = useState([]); // [{code, name, flag, count}]
  const [open, setOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/events/countries");
        const enriched = (Array.isArray(data) ? data : [])
          .map((row) => {
            const c = (row.country || "NZ").toUpperCase();
            const meta = COUNTRIES.find((x) => x.code === c) || {
              code: c, name: c, flag: "🌐",
            };
            return { ...meta, count: row.count };
          })
          .sort((a, b) => b.count - a.count);
        setOptions(enriched);
      } catch {
        setOptions([]);
      }
    })();
  }, []);

  // Close the dropdown when the user clicks outside.
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (!e.target.closest("[data-country-picker-root]")) setOpen(false);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [open]);

  const totalCount = options.reduce((sum, o) => sum + (o.count || 0), 0);
  const currentMeta = value === "ALL"
    ? { code: "ALL", name: "All countries", flag: "🌐", count: totalCount }
    : options.find((o) => o.code === value)
      || COUNTRIES.find((c) => c.code === value)
      || { code: value || "NZ", name: value || "New Zealand", flag: "🇳🇿", count: 0 };

  const select = useCallback((code) => {
    onChange?.(code);
    setOpen(false);
  }, [onChange]);

  const padding = compact ? "px-3 py-2" : "px-4 py-3";

  return (
    <div className="relative inline-block" data-country-picker-root data-testid="country-picker">
      <button
        type="button"
        className={`flex items-center gap-2 rounded-full border text-sm font-medium transition ${padding}`}
        style={{
          borderColor: "var(--border)",
          background: "var(--bg-card)",
          color: "var(--text)",
        }}
        onClick={() => setOpen((v) => !v)}
        data-testid="country-picker-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Globe className="w-4 h-4" aria-hidden style={{ color: "var(--accent)" }} />
        <span className="text-base" aria-hidden>{currentMeta.flag}</span>
        <span>{currentMeta.name}</span>
        <ChevronDown className="w-3.5 h-3.5 opacity-60" aria-hidden />
      </button>

      {open && (
        <div
          className="absolute z-50 mt-2 w-72 max-h-80 overflow-y-auto rounded-2xl border shadow-xl"
          style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
          role="listbox"
          data-testid="country-picker-menu"
        >
          <button
            type="button"
            onClick={() => select("ALL")}
            className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-black/5 transition"
            style={{ color: "var(--text)" }}
            data-testid="country-picker-option-ALL"
          >
            <span className="flex items-center gap-2">
              <span aria-hidden>🌐</span>
              <span>All countries</span>
            </span>
            <span className="text-xs opacity-60">{totalCount}</span>
          </button>
          <div className="h-px" style={{ background: "var(--border)" }} />
          {options.length === 0 ? (
            <div className="px-4 py-6 text-sm text-center" style={{ color: "var(--text-dim)" }}>
              No countries with live events yet.
            </div>
          ) : (
            options.map((o) => (
              <button
                key={o.code}
                type="button"
                onClick={() => select(o.code)}
                className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-black/5 transition"
                style={{ color: "var(--text)" }}
                data-testid={`country-picker-option-${o.code}`}
                aria-selected={value === o.code}
              >
                <span className="flex items-center gap-2">
                  <span aria-hidden>{o.flag}</span>
                  <span>{o.name}</span>
                </span>
                <span className="text-xs opacity-60">{o.count}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
