import { useEffect, useState } from "react";
import { Clock } from "lucide-react";

export default function Countdown({ expiresAt, onExpire }) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    const calc = () => {
      const t = new Date(expiresAt).getTime() - Date.now();
      setRemaining(Math.max(0, t));
      if (t <= 0 && onExpire) onExpire();
    };
    calc();
    const i = setInterval(calc, 1000);
    return () => clearInterval(i);
  }, [expiresAt, onExpire]);

  const mins = Math.floor(remaining / 60000);
  const secs = Math.floor((remaining % 60000) / 1000);
  const expired = remaining <= 0;

  return (
    <div
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-full border ${expired ? "" : "pulse-accent"}`}
      style={{
        background: expired ? "rgba(239,68,68,0.1)" : "var(--accent-soft)",
        borderColor: expired ? "var(--danger)" : "var(--accent)",
        color: expired ? "var(--danger)" : "var(--accent)",
      }}
      data-testid="checkout-countdown"
    >
      <Clock className="w-4 h-4" />
      <span className="font-mono text-sm">
        {expired ? "Hold expired" : `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`}
      </span>
    </div>
  );
}
