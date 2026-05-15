/**
 * SeatDesigner — interactive theatre layout editor.
 *
 * Props:
 *  - rows, cols: grid dimensions
 *  - aisles: array of seat ids to render as aisles (e.g. ["A-3", "B-3"])
 *  - sections: array of {after_row: int, label: string} — inserts a labeled
 *    horizontal divider after row index (0-indexed). e.g. {after_row: 4, label: "Mezzanine"}
 *  - curved: bool — render rows as a gentle arc (closer rows curve less)
 *  - backdropUrl: optional reference image rendered behind the grid
 *  - backdropOpacity, backdropOffsetY: alignment controls
 *  - onChange: ({aisles, sections, curved, backdropOpacity, backdropOffsetY})
 */
import { useState } from "react";
import { Sparkles, ImageOff, Layers, MoveVertical } from "lucide-react";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export default function SeatDesigner({
  rows,
  cols,
  aisles = [],
  sections = [],
  curved = false,
  backdropUrl = null,
  backdropOpacity = 0.2,
  backdropOffsetY = 0,
  onChange,
}) {
  const [mode, setMode] = useState("aisle"); // "aisle" | "section"
  const aisleSet = new Set(aisles);
  const sectionMap = new Map(sections.map((s) => [s.after_row, s.label]));

  const emit = (patch) => {
    onChange?.({
      aisles,
      sections,
      curved,
      backdrop_opacity: backdropOpacity,
      backdrop_offset_y: backdropOffsetY,
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
      const label = window.prompt(
        `Label for the section after row ${LETTERS[afterRow]}?`,
        "Mezzanine"
      );
      if (label) emit({ sections: [...sections, { after_row: afterRow, label }] });
    }
  };

  // Curved rows: each row arcs slightly forward. Middle seats stay neutral,
  // outer seats nudge downward (toward the audience). Stronger for back rows.
  const curveOffset = (r, c) => {
    if (!curved) return 0;
    const center = (cols - 1) / 2;
    const dx = c - center;
    const rowFactor = 0.45 + (r / Math.max(rows - 1, 1)) * 0.55; // back rows curve more
    return Math.round((dx * dx) * 0.18 * rowFactor);
  };

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
          Tap a square to mark it as <span style={{ color: "var(--accent)" }}>aisle</span>, or use Section mode to insert a labeled divider between rows.
        </div>
        <div className="flex gap-1 p-1 rounded-full" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
          <button
            type="button"
            onClick={() => setMode("aisle")}
            className="px-3 py-1 rounded-full text-xs uppercase tracking-widest transition"
            style={{ background: mode === "aisle" ? "var(--accent)" : "transparent", color: mode === "aisle" ? "#000" : "var(--text-muted)" }}
            data-testid="designer-mode-aisle"
          >
            Aisle
          </button>
          <button
            type="button"
            onClick={() => setMode("section")}
            className="px-3 py-1 rounded-full text-xs uppercase tracking-widest transition"
            style={{ background: mode === "section" ? "var(--accent)" : "transparent", color: mode === "section" ? "#000" : "var(--text-muted)" }}
            data-testid="designer-mode-section"
          >
            Section
          </button>
        </div>
      </div>

      {/* Layout controls */}
      <div className="flex flex-wrap items-center gap-5 text-xs" style={{ color: "var(--text-muted)" }}>
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={curved}
            onChange={(e) => emit({ curved: e.target.checked })}
            data-testid="designer-curved-toggle"
          />
          <span className="inline-flex items-center gap-1"><Sparkles className="w-3 h-3" /> Curved rows</span>
        </label>
        {backdropUrl && (
          <>
            <label className="inline-flex items-center gap-2">
              <span className="inline-flex items-center gap-1"><ImageOff className="w-3 h-3" /> Backdrop opacity</span>
              <input
                type="range"
                min="0" max="1" step="0.05"
                value={backdropOpacity}
                onChange={(e) => emit({ backdrop_opacity: parseFloat(e.target.value) })}
                data-testid="designer-backdrop-opacity"
                className="w-32"
              />
              <span className="font-mono">{Math.round(backdropOpacity * 100)}%</span>
            </label>
            <label className="inline-flex items-center gap-2">
              <span className="inline-flex items-center gap-1"><MoveVertical className="w-3 h-3" /> Backdrop Y</span>
              <input
                type="range"
                min="-100" max="100" step="2"
                value={backdropOffsetY}
                onChange={(e) => emit({ backdrop_offset_y: parseInt(e.target.value, 10) })}
                data-testid="designer-backdrop-offset"
                className="w-32"
              />
              <span className="font-mono">{backdropOffsetY}px</span>
            </label>
          </>
        )}
      </div>

      {/* Grid */}
      <div className="border rounded-xl p-5 relative overflow-x-auto" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
        {backdropUrl && (
          <div
            className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden"
            style={{ opacity: backdropOpacity, transform: `translateY(${backdropOffsetY}px)` }}
          >
            <img src={backdropUrl} alt="" className="w-full h-full object-cover" />
          </div>
        )}
        <div className="relative z-10 stage-arc mb-1" />
        <div className="relative z-10 text-center text-[10px] uppercase tracking-[0.3em] mb-3" style={{ color: "var(--text-dim)" }}>Stage</div>

        <div className="relative z-10 flex flex-col items-center gap-1.5">
          {Array.from({ length: rows }).map((_, r) => (
            <div key={r}>
              <div className="flex items-center gap-1.5">
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
                      className="transition"
                      style={{
                        width: 24, height: 24, borderRadius: 5,
                        background: isAisle ? "transparent" : "var(--bg-card)",
                        border: isAisle ? "1px dashed var(--border-strong)" : "1px solid var(--border-strong)",
                        transform: `translateY(${dy}px)`,
                        cursor: mode === "section" ? "default" : "pointer",
                      }}
                      title={`${id} — ${isAisle ? "aisle" : "seat"}`}
                      data-testid={`designer-${id}`}
                    />
                  );
                })}
                <div className="w-5 text-[10px] font-mono text-center" style={{ color: "var(--text-dim)" }}>{LETTERS[r]}</div>
              </div>

              {/* Section divider after this row (clickable in section mode) */}
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
        {(aisleSet.size > 0 || sections.length > 0 || curved) && (
          <button
            type="button"
            onClick={() => emit({ aisles: [], sections: [], curved: false, backdrop_opacity: 0.2, backdrop_offset_y: 0 })}
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
