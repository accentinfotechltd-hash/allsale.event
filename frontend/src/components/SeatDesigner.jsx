/**
 * SeatDesigner — theatre layout editor with backdrop alignment controls.
 *
 * Designed for the common workflow: organizer uploads a real venue floor-plan
 * and then aligns the editable seat grid on top of it. The backdrop has
 * adjustable opacity / x-offset / y-offset / scale so seats line up with the
 * actual seats in the photo.
 */
import { useState } from "react";
import { Sparkles, ImageOff, MoveVertical, MoveHorizontal, ZoomIn, Layers, Accessibility, Eye, Crown, Home } from "lucide-react";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

// Paint categories — mirror backend `seat_categories` keys + visual mapping
// to the common cinema-map legend (Hoyts, Event Cinemas, AMC, etc.).
const PAINT_CATEGORIES = [
  { key: "aisle", label: "Aisle", color: "transparent", border: "dashed", icon: null },
  { key: "wheelchair", label: "Wheelchair", color: "#1E88E5", border: "solid", icon: Accessibility },
  { key: "disabled", label: "Disabled", color: "#4CAF50", border: "solid", icon: Eye },
  { key: "house", label: "House", color: "#FFD600", border: "solid", icon: Home },
  { key: "vip", label: "VIP", color: "#9C27B0", border: "solid", icon: Crown },
  { key: "premium", label: "Premium", color: "#F08A2A", border: "solid", icon: Crown },
];

export default function SeatDesigner({
  rows,
  cols,
  aisles = [],
  sections = [],
  categories = {},  // {wheelchair: ["A-1"], house: [...], etc.}
  rowOffsets = {},  // {C: 2} → row C col 3 displays as label "1"
  curved = false,
  numberingRtl = false,
  backdropUrl = null,
  backdropOpacity = 0.4,
  backdropOffsetY = 0,
  backdropOffsetX = 0,
  backdropScale = 1,
  onChange,
}) {
  const [mode, setMode] = useState("aisle");
  const [paintingDown, setPaintingDown] = useState(false);  // drag-paint state
  const aisleSet = new Set(aisles);
  const sectionMap = new Map(sections.map((s) => [s.after_row, s.label]));

  // Build a fast lookup: seat_id → category key (or null)
  const seatCategoryMap = new Map();
  Object.entries(categories || {}).forEach(([cat, ids]) => {
    (ids || []).forEach((id) => seatCategoryMap.set(id, cat));
  });

  const emit = (patch) => {
    onChange?.({
      aisles,
      sections,
      categories,
      curved,
      backdrop_opacity: backdropOpacity,
      backdrop_offset_y: backdropOffsetY,
      backdrop_offset_x: backdropOffsetX,
      backdrop_scale: backdropScale,
      ...patch,
    });
  };

  // Apply current `mode` to a seat. Aisle is mutually exclusive with any
  // category (a seat is EITHER bookable+categorised OR a non-seat aisle).
  const applyMode = (id) => {
    if (mode === "aisle") {
      const next = new Set(aisleSet);
      if (next.has(id)) next.delete(id);
      else {
        next.add(id);
        // Strip category — aisles can't have one
        if (seatCategoryMap.has(id)) {
          const cat = seatCategoryMap.get(id);
          const nextCats = { ...categories, [cat]: (categories[cat] || []).filter((s) => s !== id) };
          emit({ aisles: Array.from(next), categories: nextCats });
          return;
        }
      }
      emit({ aisles: Array.from(next) });
      return;
    }
    if (mode === "section") return;
    if (mode === "normal") {
      // Clear any category from this seat
      if (!seatCategoryMap.has(id)) return;
      const cat = seatCategoryMap.get(id);
      const nextCats = { ...categories, [cat]: (categories[cat] || []).filter((s) => s !== id) };
      emit({ categories: nextCats });
      return;
    }
    // Category paint mode (wheelchair / disabled / house / vip / premium)
    const nextAisles = new Set(aisleSet);
    nextAisles.delete(id); // category overrides aisle
    const cleanedCats = { ...categories };
    PAINT_CATEGORIES.forEach((c) => {
      if (c.key !== mode && cleanedCats[c.key]) {
        cleanedCats[c.key] = cleanedCats[c.key].filter((s) => s !== id);
      }
    });
    const current = new Set(cleanedCats[mode] || []);
    if (current.has(id)) {
      current.delete(id); // toggle off
    } else {
      current.add(id);
    }
    cleanedCats[mode] = Array.from(current);
    emit({ aisles: Array.from(nextAisles), categories: cleanedCats });
  };

  const toggleAisle = (id) => applyMode(id);  // kept for back-compat with existing handlers

  const toggleSection = (afterRow) => {
    if (sectionMap.has(afterRow)) {
      emit({ sections: sections.filter((s) => s.after_row !== afterRow) });
    } else {
      const label = window.prompt(`Label for the section after row ${LETTERS[afterRow]}?`, "Mezzanine");
      if (label) emit({ sections: [...sections, { after_row: afterRow, label }] });
    }
  };

  // Adaptive seat size based on column count (so 15-col venues fit on screen)
  const seatSize = cols <= 10 ? 26 : cols <= 14 ? 22 : cols <= 18 ? 18 : 14;
  const seatGap = cols <= 14 ? 6 : 4;

  const curveOffset = (r, c) => {
    if (!curved) return 0;
    const center = (cols - 1) / 2;
    const dx = c - center;
    const rowFactor = 0.45 + (r / Math.max(rows - 1, 1)) * 0.55;
    return Math.round((dx * dx) * 0.14 * rowFactor);
  };

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
          Pick a paint mode, then tap (or drag) seats. Aisle = non-bookable. Categories show as colored chips on the public seatmap.
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 p-1.5 rounded-xl" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }} data-testid="paint-toolbar">
        {PAINT_CATEGORIES.map((c) => {
          const Icon = c.icon;
          const active = mode === c.key;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => setMode(c.key)}
              className="px-2.5 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition"
              style={{
                background: active ? c.color : "transparent",
                color: active ? (c.key === "aisle" ? "var(--text)" : "#FFFFFF") : "var(--text-muted)",
                border: active ? `1px solid ${c.color === "transparent" ? "var(--accent)" : c.color}` : "1px solid var(--border)",
              }}
              data-testid={`designer-mode-${c.key}`}
            >
              {Icon && <Icon className="w-3 h-3" />} {c.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setMode("normal")}
          className="px-2.5 py-1.5 rounded-lg text-xs transition"
          style={{
            background: mode === "normal" ? "var(--bg)" : "transparent",
            color: mode === "normal" ? "var(--text)" : "var(--text-muted)",
            border: mode === "normal" ? "1px solid var(--text)" : "1px solid var(--border)",
          }}
          data-testid="designer-mode-normal"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={() => setMode("section")}
          className="px-2.5 py-1.5 rounded-lg text-xs transition ml-auto"
          style={{
            background: mode === "section" ? "var(--accent)" : "transparent",
            color: mode === "section" ? "#FFFFFF" : "var(--text-muted)",
            border: mode === "section" ? "1px solid var(--accent)" : "1px solid var(--border)",
          }}
          data-testid="designer-mode-section"
        >Section</button>
      </div>

      {/* Layout + Backdrop alignment controls */}
      <div className="space-y-3 rounded-xl p-4" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
        <div className="flex items-center gap-5 flex-wrap text-xs" style={{ color: "var(--text-muted)" }}>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox" checked={curved}
              onChange={(e) => emit({ curved: e.target.checked })}
              data-testid="designer-curved-toggle"
            />
            <span className="inline-flex items-center gap-1"><Sparkles className="w-3 h-3" /> Curved rows</span>
          </label>
        </div>

        {backdropUrl && (
          <div className="grid sm:grid-cols-2 gap-3 pt-2 border-t" style={{ borderColor: "var(--border)" }}>
            <div className="text-[10px] uppercase tracking-widest sm:col-span-2 pt-1" style={{ color: "var(--text-dim)" }}>
              Align floor-plan with seat grid
            </div>

            <Slider
              icon={<ImageOff className="w-3 h-3" />}
              label="Opacity"
              min={0} max={1} step={0.05}
              value={backdropOpacity}
              onChange={(v) => emit({ backdrop_opacity: v })}
              format={(v) => `${Math.round(v * 100)}%`}
              testid="designer-backdrop-opacity"
            />
            <Slider
              icon={<ZoomIn className="w-3 h-3" />}
              label="Scale"
              min={0.4} max={2.5} step={0.05}
              value={backdropScale}
              onChange={(v) => emit({ backdrop_scale: v })}
              format={(v) => `${v.toFixed(2)}×`}
              testid="designer-backdrop-scale"
            />
            <Slider
              icon={<MoveHorizontal className="w-3 h-3" />}
              label="Offset X"
              min={-200} max={200} step={2}
              value={backdropOffsetX}
              onChange={(v) => emit({ backdrop_offset_x: v })}
              format={(v) => `${v}px`}
              testid="designer-backdrop-offset-x"
            />
            <Slider
              icon={<MoveVertical className="w-3 h-3" />}
              label="Offset Y"
              min={-200} max={200} step={2}
              value={backdropOffsetY}
              onChange={(v) => emit({ backdrop_offset_y: v })}
              format={(v) => `${v}px`}
              testid="designer-backdrop-offset-y"
            />
          </div>
        )}
      </div>

      {/* Designer canvas */}
      <div className="border rounded-xl p-5 relative overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
        {backdropUrl && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              opacity: backdropOpacity,
              transform: `translate(${backdropOffsetX}px, ${backdropOffsetY}px) scale(${backdropScale})`,
              transformOrigin: "center center",
            }}
          >
            <img
              src={backdropUrl}
              alt=""
              className="w-full h-full"
              style={{ objectFit: "contain" }}
              draggable={false}
            />
          </div>
        )}
        <div className="relative z-10 stage-arc mb-1" />
        <div className="relative z-10 text-center text-[10px] uppercase tracking-[0.3em] mb-3" style={{ color: "var(--text-dim)" }}>Stage</div>

        <div className="relative z-10 flex flex-col items-center" style={{ gap: seatGap }}>
          {Array.from({ length: rows }).map((_, r) => (
            <div key={r} className="w-full">
              <div className="flex items-center justify-center" style={{ gap: seatGap }}>
                <div className="w-5 text-[10px] font-mono text-center" style={{ color: "var(--text-dim)" }}>{LETTERS[r]}</div>
                {Array.from({ length: cols }).map((_, c) => {
                  const seatNumber = numberingRtl ? cols - c : c + 1;
                  const id = `${LETTERS[r]}-${seatNumber}`;
                  const rowOffset = (rowOffsets || {})[LETTERS[r]] || 0;
                  const displayLabel = seatNumber - rowOffset;
                  const idStr = displayLabel > 0 ? `${LETTERS[r]}${displayLabel}` : id;
                  const isAisle = aisleSet.has(id);
                  const seatCategory = seatCategoryMap.get(id);
                  const catDef = PAINT_CATEGORIES.find((p) => p.key === seatCategory);
                  const bg = isAisle
                    ? "transparent"
                    : catDef
                      ? catDef.color
                      : "rgba(21,21,27,0.92)";
                  const border = isAisle
                    ? "1px dashed var(--border-strong)"
                    : catDef
                      ? `1px solid ${catDef.color}`
                      : "1px solid var(--border-strong)";
                  const dy = curveOffset(r, c);
                  const isClickable = mode !== "section";
                  return (
                    <button
                      key={id}
                      type="button"
                      onMouseDown={() => { if (isClickable) { setPaintingDown(true); applyMode(id); } }}
                      onMouseEnter={() => { if (isClickable && paintingDown) applyMode(id); }}
                      onMouseUp={() => setPaintingDown(false)}
                      onClick={(e) => { e.preventDefault(); /* handled in mousedown */ }}
                      disabled={!isClickable}
                      className="transition shrink-0"
                      style={{
                        width: seatSize, height: seatSize, borderRadius: 5,
                        background: bg,
                        border,
                        transform: dy ? `translateY(${dy}px)` : undefined,
                        cursor: isClickable ? "pointer" : "default",
                      }}
                      title={`${idStr} — ${isAisle ? "aisle" : (seatCategory || "normal seat")}`}
                      data-testid={`designer-${id}`}
                    />
                  );
                })}
                <div className="w-5 text-[10px] font-mono text-center" style={{ color: "var(--text-dim)" }}>{LETTERS[r]}</div>
              </div>

              {(mode === "section" || sectionMap.has(r)) && r < rows - 1 && (
                <button
                  type="button"
                  onClick={() => toggleSection(r)}
                  disabled={mode !== "section"}
                  className="block w-full my-2 group"
                  data-testid={`section-after-${LETTERS[r]}`}
                >
                  <div
                    className="h-px relative transition-all"
                    style={{
                      background: sectionMap.has(r) ? "var(--accent)" : "var(--border)",
                      height: sectionMap.has(r) ? 2 : 1,
                      opacity: mode === "section" ? 1 : 0.6,
                    }}
                  >
                    {sectionMap.has(r) && (
                      <span
                        className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
                        style={{ background: "var(--bg-elev)", color: "var(--accent)", border: "1px solid var(--accent)" }}
                      >
                        <Layers className="inline w-2.5 h-2.5 mr-1" />
                        {sectionMap.get(r)}
                      </span>
                    )}
                    {mode === "section" && !sectionMap.has(r) && (
                      <span
                        className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 rounded-full text-[10px] opacity-0 group-hover:opacity-100 transition"
                        style={{ background: "var(--bg-elev)", color: "var(--text-muted)", border: "1px dashed var(--border-strong)" }}
                      >
                        + section
                      </span>
                    )}
                  </div>
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs flex-wrap" style={{ color: "var(--text-muted)" }}>
        <span>Total seats: <strong style={{ color: "var(--text)" }}>{rows * cols - aisleSet.size}</strong></span>
        <span>Aisles: <strong style={{ color: "var(--text)" }}>{aisleSet.size}</strong></span>
        <span>Sections: <strong style={{ color: "var(--text)" }}>{sections.length}</strong></span>
        {(aisleSet.size > 0 || sections.length > 0 || curved || backdropOpacity !== 0.4 || backdropOffsetY || backdropOffsetX || backdropScale !== 1) && (
          <button
            type="button"
            onClick={() => emit({
              aisles: [], sections: [], curved: false,
              backdrop_opacity: 0.4, backdrop_offset_y: 0, backdrop_offset_x: 0, backdrop_scale: 1,
            })}
            className="underline"
            style={{ color: "var(--accent)" }}
            data-testid="clear-designer"
          >
            Reset layout
          </button>
        )}
      </div>
    </div>
  );
}

function Slider({ icon, label, min, max, step, value, onChange, format, testid }) {
  return (
    <label className="flex items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 min-w-[80px]" style={{ color: "var(--text-muted)" }}>
        {icon} {label}
      </span>
      <input
        type="range" min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        data-testid={testid}
        className="flex-1"
      />
      <span className="font-mono w-12 text-right" style={{ color: "var(--text-dim)" }}>{format(value)}</span>
    </label>
  );
}
