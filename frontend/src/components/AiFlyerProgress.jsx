import { useEffect, useState, useRef } from "react";
import { Wand2, Loader2, Sparkles, FileText, PenLine, CheckCircle2 } from "lucide-react";

/**
 * AI flyer text generation progress card.
 *
 * Backend (`POST /api/events/{id}/flyer/generate-text`) is a single blocking
 * call with a model fallback chain (Gemini 2.5 Flash → Gemini 2.5 Pro →
 * GPT-5.2). End-to-end can take 5–25 seconds. The old UI was just
 * "Writing..." text on a button — users assumed it was broken.
 *
 * This component shows:
 *   • Rotating stage messages so it feels like real progress (4 stages,
 *     ~5s each based on observed P50 latency).
 *   • Synthetic progress bar that asymptotes to 95% (it will never claim
 *     100% until the API actually returns). Logarithmic curve so it moves
 *     fast at the start (rewarding feel) and slows near the cap.
 *   • Animated wand icon + spinner.
 *   • Success flash at 100% before fading out (caller hides the component
 *     by switching `active` to false after consuming the result).
 */
const STAGES = [
  { at: 0, icon: Sparkles, label: "Reading your event details…" },
  { at: 5, icon: PenLine, label: "Drafting a punchy headline…" },
  { at: 10, icon: FileText, label: "Polishing the tagline & CTA…" },
  { at: 16, icon: Wand2, label: "Almost done — finalising the text…" },
];

const TARGET_PROGRESS = 95; // cap until API returns
const SUCCESS_FLASH_MS = 700;

export default function AiFlyerProgress({ active, finished, onDoneFlash }) {
  const [elapsed, setElapsed] = useState(0);
  const [progress, setProgress] = useState(0);
  const [doneFlashed, setDoneFlashed] = useState(false);
  const startRef = useRef(null);
  const rafRef = useRef(null);

  // Drive elapsed timer + synthetic progress while `active` is true.
  useEffect(() => {
    if (!active) {
      // reset on unmount/inactive
      setElapsed(0);
      setProgress(0);
      setDoneFlashed(false);
      startRef.current = null;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return undefined;
    }
    startRef.current = Date.now();
    const tick = () => {
      if (!startRef.current) return;
      const e = (Date.now() - startRef.current) / 1000;
      setElapsed(e);
      // Asymptotic curve toward 95%: progress = 95 * (1 - exp(-e/8))
      // - At t=3s  → ~31%
      // - At t=8s  → ~62%
      // - At t=15s → ~82%
      // - At t=25s → ~93%
      const p = TARGET_PROGRESS * (1 - Math.exp(-e / 8));
      setProgress(p);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  // When parent marks `finished=true`, jump to 100% with a success flash,
  // then call `onDoneFlash` so parent can unmount us.
  useEffect(() => {
    if (!finished || doneFlashed) return;
    setProgress(100);
    setDoneFlashed(true);
    const t = setTimeout(() => onDoneFlash?.(), SUCCESS_FLASH_MS);
    return () => clearTimeout(t);
  }, [finished, doneFlashed, onDoneFlash]);

  if (!active) return null;

  // Pick the current stage based on elapsed time.
  let stage = STAGES[0];
  for (const s of STAGES) {
    if (elapsed >= s.at) stage = s;
  }
  const isDone = progress >= 100;
  const Icon = isDone ? CheckCircle2 : stage.icon;

  return (
    <div
      data-testid="ai-flyer-progress"
      className="mt-3 rounded-xl border p-4 transition-all"
      style={{
        borderColor: isDone ? "var(--accent)" : "var(--border)",
        background: "var(--bg-card)",
      }}
    >
      <div className="flex items-center gap-3 mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{
            background: isDone ? "var(--accent-soft)" : "var(--accent-soft)",
          }}
        >
          {isDone ? (
            <CheckCircle2 size={18} style={{ color: "var(--accent)" }} />
          ) : (
            <div className="relative">
              <Icon size={18} style={{ color: "var(--accent)" }} className="animate-pulse" />
              <Loader2
                size={28}
                className="absolute inset-0 animate-spin opacity-30"
                style={{ color: "var(--accent)", margin: -5 }}
              />
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div
            className="text-sm font-medium"
            style={{ color: isDone ? "var(--accent)" : "var(--text)" }}
            data-testid="ai-progress-stage"
          >
            {isDone ? "Done — applying your text overlay…" : stage.label}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            {isDone
              ? `Finished in ${elapsed.toFixed(1)}s`
              : `Writing with AI · ${elapsed.toFixed(0)}s elapsed`}
          </div>
        </div>
        <div
          className="text-xs font-mono tabular-nums"
          style={{ color: "var(--text-muted)" }}
          data-testid="ai-progress-percent"
        >
          {Math.round(progress)}%
        </div>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full overflow-hidden"
        style={{ background: "var(--border)" }}
      >
        <div
          className="h-full transition-all duration-300 ease-out"
          style={{
            width: `${progress}%`,
            background: isDone
              ? "var(--accent)"
              : "linear-gradient(90deg, var(--accent) 0%, var(--accent) 60%, color-mix(in srgb, var(--accent), white 30%) 100%)",
          }}
        />
      </div>

      {/* Honest expectation setting after 15s */}
      {elapsed > 15 && !isDone && (
        <div
          className="text-[11px] mt-3 leading-relaxed"
          style={{ color: "var(--text-muted)" }}
        >
          Taking a bit longer than usual — the model is still thinking. Sometimes
          the first attempt has to fall back to a backup model.
        </div>
      )}
    </div>
  );
}
