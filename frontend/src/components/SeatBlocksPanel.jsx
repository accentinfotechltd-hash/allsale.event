/**
 * SeatBlocksPanel — organizer-only seat management.
 *
 * Lets the organizer block individual seats off the public seatmap so they
 * can be set aside for sponsors, VIPs, complimentary gifts, staff, etc.
 * Built on top of the existing SeatMap component so the UI is consistent
 * with the public seat-picker — the organizer just clicks seats and presses
 * "Block selected".
 *
 * Backend contract (all under /api/organizer):
 *   GET    /events/{event_id}/seat-blocks       → { blocks: [...] }
 *   POST   /events/{event_id}/seat-blocks       → { seats, reason, note }
 *   DELETE /events/{event_id}/seat-blocks/{id}  → release one
 *   DELETE /events/{event_id}/seat-blocks       → release all
 */
import { useEffect, useMemo, useState } from "react";
import SeatMap from "./SeatMap";
import api from "@/lib/api";
import { toast } from "sonner";
import { Lock, Trash2, ShieldCheck, Gift, Star, Briefcase, RefreshCcw } from "lucide-react";

const REASONS = [
  { id: "VIP", label: "VIP", icon: Star },
  { id: "Sponsor", label: "Sponsor", icon: Briefcase },
  { id: "Gift", label: "Gift / Comp", icon: Gift },
  { id: "Staff", label: "Staff", icon: ShieldCheck },
  { id: "Other", label: "Other", icon: Lock },
];

export default function SeatBlocksPanel({ eventId, event }) {
  const [blocks, setBlocks] = useState([]);
  const [selected, setSelected] = useState([]);
  const [reason, setReason] = useState("VIP");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  // Pull the latest public availability so we know what's booked / on-hold /
  // already blocked. (Blocked seats come back as `booked_seats` per the
  // backend contract.)
  const [snapshot, setSnapshot] = useState({ booked: [], held: [] });

  const blockedSet = useMemo(() => new Set(blocks.map((b) => b.seat_id)), [blocks]);

  // Booked seats from public endpoint actually include blocked too — strip
  // blocks out so the public "Booked" colour only marks paid seats.
  const publicBooked = useMemo(
    () => (snapshot.booked || []).filter((s) => !blockedSet.has(s)),
    [snapshot.booked, blockedSet],
  );

  const load = async () => {
    try {
      const [b, e] = await Promise.all([
        api.get(`/organizer/events/${eventId}/seat-blocks`),
        api.get(`/events/${eventId}`),
      ]);
      setBlocks(b.data.blocks || []);
      setSnapshot({
        booked: e.data.booked_seats || [],
        held: e.data.held_seats || [],
      });
    } catch {
      toast.error("Could not load seat blocks");
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [eventId, refreshTick]);

  const onToggle = (seatId) => {
    // Clicking a currently-blocked seat selects it for release.
    setSelected((prev) =>
      prev.includes(seatId) ? prev.filter((s) => s !== seatId) : [...prev, seatId],
    );
  };

  const blockSelected = async () => {
    const toBlock = selected.filter((s) => !blockedSet.has(s));
    if (toBlock.length === 0) {
      toast.message("Pick at least one open seat first");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post(`/organizer/events/${eventId}/seat-blocks`, {
        seats: toBlock,
        reason,
        note,
      });
      toast.success(`Blocked ${data.count} seat${data.count === 1 ? "" : "s"}`);
      if (data.rejected?.length) toast.error(`Skipped: ${data.rejected.join(", ")}`);
      setSelected([]);
      setNote("");
      setRefreshTick((t) => t + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not block seats");
    } finally {
      setBusy(false);
    }
  };

  const releaseSelected = async () => {
    const toRelease = selected.filter((s) => blockedSet.has(s));
    if (toRelease.length === 0) return;
    setBusy(true);
    try {
      for (const s of toRelease) {
        await api.delete(`/organizer/events/${eventId}/seat-blocks/${s}`);
      }
      toast.success(`Released ${toRelease.length} seat${toRelease.length === 1 ? "" : "s"}`);
      setSelected([]);
      setRefreshTick((t) => t + 1);
    } catch {
      toast.error("Could not release some seats");
    } finally {
      setBusy(false);
    }
  };

  const releaseAll = async () => {
    if (!blocks.length) return;
    if (!window.confirm(`Release all ${blocks.length} blocked seats?`)) return;
    setBusy(true);
    try {
      await api.delete(`/organizer/events/${eventId}/seat-blocks`);
      toast.success("All blocks released");
      setRefreshTick((t) => t + 1);
    } catch {
      toast.error("Failed to release all blocks");
    } finally {
      setBusy(false);
    }
  };

  if (!event?.has_seatmap) return null;

  const blockedCount = blocks.length;
  const blockedToRelease = selected.filter((s) => blockedSet.has(s)).length;
  const openToBlock = selected.filter((s) => !blockedSet.has(s)).length;

  // Visual trick: blocked seats render in the "selected" slot with a custom
  // hint colour by inverting the selection map. We pass the blocked seats as
  // `held` so they pick up the on-hold yellow — distinct from booked grey.
  return (
    <div className="border rounded-2xl p-6 lg:p-8 mb-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="seat-blocks-panel">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Seat management</div>
          <h2 className="serif text-3xl">Hold seats for VIPs &amp; sponsors</h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Tap any open seat to select it, then press <em>Block selected</em>. Blocked seats disappear from public availability instantly. Tap a yellow seat to mark it for release.
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Currently blocked</div>
          <div className="serif text-3xl" data-testid="blocked-count">{blockedCount}</div>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_320px] gap-6">
        <div className="border rounded-xl p-4" style={{ borderColor: "var(--border)" }}>
          <SeatMap
            rows={event.seat_rows}
            cols={event.seat_cols}
            booked={publicBooked}
            held={blocks.map((b) => b.seat_id)}  /* show blocks as yellow */
            selected={selected}
            aisles={event.aisles || []}
            sections={event.seatmap_sections || []}
            curved={event.seatmap_curved}
            numberingRtl={!!event.seatmap_numbering_rtl}
            onToggle={onToggle}
          />
          <div className="text-xs mt-3 flex flex-wrap gap-4" style={{ color: "var(--text-dim)" }}>
            <span><strong style={{ color: "var(--text-muted)" }}>Yellow</strong> = your blocks · <strong style={{ color: "var(--text-muted)" }}>Grey</strong> = paid bookings</span>
          </div>
        </div>

        <div className="space-y-4">
          <div className="border rounded-xl p-4" style={{ borderColor: "var(--border)" }}>
            <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Bulk range select</div>
            <BulkRangePicker
              rows={event.seat_rows}
              cols={event.seat_cols}
              numberingRtl={!!event.seatmap_numbering_rtl}
              onAdd={(seatIds) => {
                const next = Array.from(new Set([...selected, ...seatIds]));
                setSelected(next);
                toast.success(`Added ${seatIds.length} seats to selection`);
              }}
            />
          </div>

          <div className="border rounded-xl p-4" style={{ borderColor: "var(--border)" }}>
            <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Reason</div>
            <div className="grid grid-cols-2 gap-2 mb-4">
              {REASONS.map((r) => {
                const Icon = r.icon;
                const active = reason === r.id;
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setReason(r.id)}
                    className={`text-left px-3 py-2 rounded-lg border text-xs flex items-center gap-2 transition`}
                    style={{
                      borderColor: active ? "var(--accent)" : "var(--border)",
                      background: active ? "rgba(234, 88, 12, 0.08)" : "transparent",
                      color: active ? "var(--accent)" : "var(--text)",
                    }}
                    data-testid={`reason-${r.id}`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {r.label}
                  </button>
                );
              })}
            </div>
            <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Note (optional)</div>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. ACME Corp - 2 guests"
              className="w-full"
              data-testid="block-note"
            />
          </div>

          <div className="space-y-2">
            <button
              type="button"
              onClick={blockSelected}
              disabled={busy || openToBlock === 0}
              className="btn-primary w-full justify-center"
              data-testid="block-selected-btn"
            >
              <Lock className="w-4 h-4" />
              {openToBlock > 0
                ? `Block ${openToBlock} seat${openToBlock === 1 ? "" : "s"}`
                : "Block selected"}
            </button>
            <button
              type="button"
              onClick={releaseSelected}
              disabled={busy || blockedToRelease === 0}
              className="btn-ghost w-full justify-center"
              data-testid="release-selected-btn"
            >
              <Trash2 className="w-4 h-4" />
              {blockedToRelease > 0
                ? `Release ${blockedToRelease} seat${blockedToRelease === 1 ? "" : "s"}`
                : "Release selected"}
            </button>
            <button
              type="button"
              onClick={() => setRefreshTick((t) => t + 1)}
              className="text-xs flex items-center gap-1 mx-auto"
              style={{ color: "var(--text-dim)" }}
              data-testid="refresh-blocks-btn"
            >
              <RefreshCcw className="w-3 h-3" /> Refresh availability
            </button>
          </div>

          {blocks.length > 0 && (
            <div className="border rounded-xl p-4" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Active blocks</div>
                <button onClick={releaseAll} className="text-xs" style={{ color: "var(--danger)" }} data-testid="release-all-btn">
                  Release all
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1.5">
                {blocks.map((b) => (
                  <div key={b.seat_id} className="flex items-center justify-between text-xs border-b py-1.5" style={{ borderColor: "var(--border)" }} data-testid={`block-row-${b.seat_id}`}>
                    <div>
                      <span className="font-medium" style={{ color: "var(--text)" }}>{b.seat_id}</span>
                      <span className="mx-1.5" style={{ color: "var(--text-dim)" }}>·</span>
                      <span style={{ color: "var(--text-muted)" }}>{b.reason}</span>
                      {b.note && <span style={{ color: "var(--text-dim)" }}> — {b.note}</span>}
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await api.delete(`/organizer/events/${eventId}/seat-blocks/${b.seat_id}`);
                          toast.success(`Released ${b.seat_id}`);
                          setRefreshTick((t) => t + 1);
                        } catch { toast.error("Failed"); }
                      }}
                      className="text-xs"
                      style={{ color: "var(--danger)" }}
                    >
                      <Trash2 className="w-3 h-3 inline" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


/**
 * Bulk range picker — admins/organizers pick row range + col range and we
 * generate the seat IDs (e.g. A1..A10, B1..B10) for one-shot blocking.
 *
 * Rows are 1-indexed letters (A, B, C ... AA, AB ...). Cols are 1-indexed.
 * The row letter generation matches the public SeatMap component so the
 * IDs we generate here line up perfectly with what the seatmap renders.
 */
function rowLetter(idx) {
  // 0 -> A, 25 -> Z, 26 -> AA, ...
  let n = idx;
  let s = "";
  do {
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return s;
}

function BulkRangePicker({ rows, cols, numberingRtl, onAdd }) {
  const [rowFrom, setRowFrom] = useState(1);
  const [rowTo, setRowTo] = useState(1);
  const [colFrom, setColFrom] = useState(1);
  const [colTo, setColTo] = useState(Math.min(cols || 1, 10));

  const totalRows = Math.max(0, Number(rows) || 0);
  const totalCols = Math.max(0, Number(cols) || 0);

  const apply = () => {
    const rStart = Math.max(1, Math.min(rowFrom, rowTo));
    const rEnd = Math.min(totalRows, Math.max(rowFrom, rowTo));
    const cStart = Math.max(1, Math.min(colFrom, colTo));
    const cEnd = Math.min(totalCols, Math.max(colFrom, colTo));
    if (rEnd < rStart || cEnd < cStart) return;
    const ids = [];
    for (let r = rStart - 1; r <= rEnd - 1; r += 1) {
      const letter = rowLetter(r);
      for (let c = cStart; c <= cEnd; c += 1) {
        // Honor right-to-left numbering preference.
        const colNum = numberingRtl ? totalCols - c + 1 : c;
        ids.push(`${letter}-${colNum}`);
      }
    }
    onAdd(ids);
  };

  const previewCount =
    Math.max(0, Math.min(totalRows, Math.max(rowFrom, rowTo)) - Math.max(1, Math.min(rowFrom, rowTo)) + 1)
    * Math.max(0, Math.min(totalCols, Math.max(colFrom, colTo)) - Math.max(1, Math.min(colFrom, colTo)) + 1);

  return (
    <div className="space-y-2" data-testid="bulk-range-picker">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-[11px]" style={{ color: "var(--text-dim)" }}>Row from</label>
          <input
            type="number" min={1} max={totalRows} value={rowFrom}
            onChange={(e) => setRowFrom(Math.max(1, Math.min(totalRows, Number(e.target.value))))}
            className="w-full px-2 py-1.5 rounded-md text-sm border bg-transparent"
            style={{ borderColor: "var(--border)" }}
            data-testid="bulk-row-from"
          />
          <div className="text-[10px] mt-0.5" style={{ color: "var(--text-dim)" }}>{rowLetter(rowFrom - 1)}</div>
        </div>
        <div>
          <label className="text-[11px]" style={{ color: "var(--text-dim)" }}>Row to</label>
          <input
            type="number" min={1} max={totalRows} value={rowTo}
            onChange={(e) => setRowTo(Math.max(1, Math.min(totalRows, Number(e.target.value))))}
            className="w-full px-2 py-1.5 rounded-md text-sm border bg-transparent"
            style={{ borderColor: "var(--border)" }}
            data-testid="bulk-row-to"
          />
          <div className="text-[10px] mt-0.5" style={{ color: "var(--text-dim)" }}>{rowLetter(rowTo - 1)}</div>
        </div>
        <div>
          <label className="text-[11px]" style={{ color: "var(--text-dim)" }}>Seat from</label>
          <input
            type="number" min={1} max={totalCols} value={colFrom}
            onChange={(e) => setColFrom(Math.max(1, Math.min(totalCols, Number(e.target.value))))}
            className="w-full px-2 py-1.5 rounded-md text-sm border bg-transparent"
            style={{ borderColor: "var(--border)" }}
            data-testid="bulk-col-from"
          />
        </div>
        <div>
          <label className="text-[11px]" style={{ color: "var(--text-dim)" }}>Seat to</label>
          <input
            type="number" min={1} max={totalCols} value={colTo}
            onChange={(e) => setColTo(Math.max(1, Math.min(totalCols, Number(e.target.value))))}
            className="w-full px-2 py-1.5 rounded-md text-sm border bg-transparent"
            style={{ borderColor: "var(--border)" }}
            data-testid="bulk-col-to"
          />
        </div>
      </div>
      <button
        onClick={apply}
        className="btn-ghost w-full justify-center text-xs"
        data-testid="bulk-add-btn"
        disabled={previewCount === 0}
      >
        Add {previewCount} seat{previewCount === 1 ? "" : "s"} to selection
      </button>
    </div>
  );
}
