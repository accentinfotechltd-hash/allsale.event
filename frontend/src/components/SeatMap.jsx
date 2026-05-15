export default function SeatMap({ rows, cols, booked = [], held = [], selected = [], aisles = [], onToggle, backdropUrl = null }) {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const aisleSet = new Set(aisles || []);
  return (
    <div className="space-y-4 relative">
      {backdropUrl && (
        <div className="absolute inset-0 -m-2 pointer-events-none rounded-xl overflow-hidden opacity-20">
          <img src={backdropUrl} alt="" className="w-full h-full object-cover" />
        </div>
      )}

      <div className="relative z-10 stage-arc" />
      <div className="relative z-10 text-center text-xs uppercase tracking-[0.3em]" style={{ color: "var(--text-dim)" }}>Stage</div>

      <div className="relative z-10 flex flex-col items-center gap-2 overflow-x-auto pb-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex items-center gap-1.5">
            <div className="w-6 text-xs font-mono text-center" style={{ color: "var(--text-dim)" }}>{letters[r]}</div>
            {Array.from({ length: cols }).map((_, c) => {
              const id = `${letters[r]}-${c + 1}`;
              if (aisleSet.has(id)) {
                // Render an empty space for aisles
                return <div key={id} className="w-7 h-7" aria-hidden="true" />;
              }
              const isBooked = booked.includes(id);
              const isHeld = held.includes(id);
              const isSelected = selected.includes(id);
              const cls = isSelected
                ? "seat seat-selected"
                : isBooked
                ? "seat seat-booked"
                : isHeld
                ? "seat seat-held"
                : "seat";
              return (
                <button
                  key={id}
                  type="button"
                  className={cls}
                  disabled={isBooked || isHeld}
                  onClick={() => onToggle && onToggle(id)}
                  aria-label={`Seat ${id}`}
                  data-testid={`seat-${id}`}
                />
              );
            })}
            <div className="w-6 text-xs font-mono text-center" style={{ color: "var(--text-dim)" }}>{letters[r]}</div>
          </div>
        ))}
      </div>

      <div className="relative z-10 flex items-center justify-center gap-5 text-xs flex-wrap pt-2" style={{ color: "var(--text-muted)" }}>
        <div className="flex items-center gap-2"><div className="seat" style={{ width: 16, height: 16 }} /> Available</div>
        <div className="flex items-center gap-2"><div className="seat seat-selected" style={{ width: 16, height: 16 }} /> Selected</div>
        <div className="flex items-center gap-2"><div className="seat seat-held" style={{ width: 16, height: 16 }} /> On hold</div>
        <div className="flex items-center gap-2"><div className="seat seat-booked" style={{ width: 16, height: 16 }} /> Booked</div>
        {aisleSet.size > 0 && <div className="flex items-center gap-2"><div className="w-4 h-4 border border-dashed" style={{ borderColor: "var(--border-strong)" }} /> Aisle</div>}
      </div>
    </div>
  );
}
