/**
 * SeatDesigner — interactive grid where organizer can toggle cells between
 * "seat" and "aisle/gap". Output: array of aisle ids ("A-3", "B-3", ...).
 */
export default function SeatDesigner({ rows, cols, aisles, onChange, backdropUrl }) {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const aisleSet = new Set(aisles || []);

  const toggle = (id) => {
    const next = new Set(aisleSet);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(Array.from(next));
  };

  return (
    <div className="space-y-3">
      <div className="text-xs" style={{ color: "var(--text-dim)" }}>
        Tap a square to toggle it between <span style={{ color: "var(--accent)" }}>seat</span> and aisle/gap. Use this to model non-rectangular venues.
      </div>
      <div className="border rounded-xl p-4 relative overflow-x-auto" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
        {backdropUrl && (
          <div className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden opacity-20">
            <img src={backdropUrl} alt="" className="w-full h-full object-cover" />
          </div>
        )}
        <div className="relative z-10 stage-arc mb-1" />
        <div className="relative z-10 text-center text-[10px] uppercase tracking-[0.3em] mb-3" style={{ color: "var(--text-dim)" }}>Stage</div>
        <div className="relative z-10 flex flex-col items-center gap-1.5">
          {Array.from({ length: rows }).map((_, r) => (
            <div key={r} className="flex items-center gap-1.5">
              <div className="w-5 text-[10px] font-mono text-center" style={{ color: "var(--text-dim)" }}>{letters[r]}</div>
              {Array.from({ length: cols }).map((_, c) => {
                const id = `${letters[r]}-${c + 1}`;
                const isAisle = aisleSet.has(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggle(id)}
                    className="transition"
                    style={{
                      width: 24, height: 24, borderRadius: 5,
                      background: isAisle ? "transparent" : "var(--bg-card)",
                      border: isAisle ? "1px dashed var(--border-strong)" : "1px solid var(--border-strong)",
                    }}
                    title={`${id} — ${isAisle ? "aisle" : "seat"}`}
                    data-testid={`designer-${id}`}
                  />
                );
              })}
              <div className="w-5 text-[10px] font-mono text-center" style={{ color: "var(--text-dim)" }}>{letters[r]}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4 text-xs flex-wrap" style={{ color: "var(--text-muted)" }}>
        <span>Total seats: <strong style={{ color: "var(--text)" }}>{rows * cols - aisleSet.size}</strong></span>
        <span>Aisles: <strong style={{ color: "var(--text)" }}>{aisleSet.size}</strong></span>
        {aisleSet.size > 0 && (
          <button type="button" onClick={() => onChange([])} className="underline" style={{ color: "var(--accent)" }} data-testid="clear-aisles">Clear all</button>
        )}
      </div>
    </div>
  );
}
