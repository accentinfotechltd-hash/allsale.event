/**
 * SeatDesigner — theatre layout editor with backdrop alignment controls.
 *
 * Designed for the common workflow: organizer uploads a real venue floor-plan
 * and then aligns the editable seat grid on top of it. The backdrop has
 * adjustable opacity / x-offset / y-offset / scale so seats line up with the
 * actual seats in the photo.
 */
import { useState } from "react";
import { Sparkles, ImageOff, MoveVertical, MoveHorizontal, ZoomIn, Layers } from "lucide-react";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export default function SeatDesigner({
  rows,
  cols,
  aisles = [],
  sections = [],
  curved = false,
  backdropUrl = null,
  backdropOpacity = 0.4,
  backdropOffsetY = 0,
  backdropOffsetX = 0,
  backdropScale = 1,
  onChange,
}) {
  const [mode, setMode] = useState("aisle");
  const aisleSet = new Set(aisles);
  const sectionMap = new Map(sections.map((s) => [s.after_row, s.label]));

  const emit = (patch) => {
    onChange?.({
      aisles,
      sections,
      curved,
      backdrop_opacity: backdropOpacity,
      backdrop_offset_y: backdropOffsetY,
      backdrop_offset_x: backdropOffsetX,
      backdrop_scale: backdropScale,
      ...patch,
    });
  };

  const toggleAisle = (id) => {
    const next = new Set(aisleSet);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    emit({ aisles: Array.from(next) });
  };

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
          Tap a square to mark it as <span style={{ color: "var(--accent)" }}>aisle</span>, or switch to Section mode to insert a labeled divider.
        </div>
        <div className="flex gap-1 p-1 rounded-full" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
          <button
            type="button" onClick={() => setMode("aisle")}
            className="px-3 py-1 rounded-full text-xs uppercase tracking-widest transition"
            style={{ background: mode === "aisle" ? "var(--accent)" : "transparent", color: mode === "aisle" ? "#000" : "var(--text-muted)" }}
            data-testid="designer-mode-aisle"
          >Aisle</button>
          <button
            type="button" onClick={() => setMode("section")}
            className="px-3 py-1 rounded-full text-xs uppercase tracking-widest transition"
            style={{ background: mode === "section" ? "var(--accent)" : "transparent", color: mode === "section" ? "#000" : "var(--text-muted)" }}
            data-testid="designer-mode-section"
          >Section</button>
        </div>
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
                  const id = `${LETTERS[r]}-${c + 1}`;
                  const isAisle = aisleSet.has(id);
                  const dy = curveOffset(r, c);
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => mode === "aisle" && toggleAisle(id)}
                      disabled={mode === "section"}
                      className="transition shrink-0"
                      style={{
                        width: seatSize, height: seatSize, borderRadius: 5,
                        background: isAisle ? "transparent" : "rgba(21,21,27,0.92)",
                        border: isAisle ? "1px dashed var(--border-strong)" : "1px solid var(--border-strong)",
                        transform: dy ? `translateY(${dy}px)` : undefined,
                        cursor: mode === "section" ? "default" : "pointer",
                      }}
                      title={`${id} — ${isAisle ? "aisle" : "seat"}`}
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
