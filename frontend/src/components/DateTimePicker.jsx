import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { CalendarIcon, Clock } from "lucide-react";

/**
 * DateTimePicker — shadcn Calendar + time HH:MM.
 * value: ISO datetime-local string (YYYY-MM-DDTHH:MM) or "".
 * onChange(newIsoLocal: string)
 */
export default function DateTimePicker({ value, onChange, testid = "datetime-picker" }) {
  const [open, setOpen] = useState(false);
  const date = value ? new Date(value) : null;
  const dateStr = date ? date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "Pick a date";
  const timeStr = date
    ? `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`
    : "19:00";

  const setDate = (d) => {
    if (!d) return;
    const cur = value ? new Date(value) : new Date();
    d.setHours(cur.getHours() || 19);
    d.setMinutes(cur.getMinutes() || 0);
    onChange(formatLocalIso(d));
    setOpen(false);
  };

  const setTime = (t) => {
    const [h, m] = t.split(":").map(Number);
    const d = value ? new Date(value) : new Date();
    d.setHours(h || 0);
    d.setMinutes(m || 0);
    onChange(formatLocalIso(d));
  };

  return (
    <div className="flex gap-2" data-testid={testid}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="flex-1 flex items-center gap-2 px-4 py-2.5 rounded-[10px] border text-left transition"
            style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: date ? "var(--text)" : "var(--text-dim)" }}
            data-testid={`${testid}-date-btn`}
          >
            <CalendarIcon className="w-4 h-4" style={{ color: "var(--accent)" }} />
            <span className="text-sm">{dateStr}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0 border" align="start" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <Calendar
            mode="single"
            selected={date || undefined}
            onSelect={setDate}
            disabled={{ before: new Date() }}
            initialFocus
          />
        </PopoverContent>
      </Popover>

      <div className="relative" style={{ width: 120 }}>
        <Clock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none" style={{ color: "var(--accent)" }} />
        <input
          type="time"
          value={timeStr}
          onChange={(e) => setTime(e.target.value)}
          className="!pl-9"
          data-testid={`${testid}-time`}
        />
      </div>
    </div>
  );
}

function formatLocalIso(d) {
  // Returns local YYYY-MM-DDTHH:MM for compatibility with the existing form
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
