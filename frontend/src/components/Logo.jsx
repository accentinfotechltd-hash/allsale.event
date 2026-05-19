/**
 * Allsale Events logo lockup.
 *
 * Design language:
 *  - Hot-coral (#FF4F00) "A-peak" triangle with a ticket-perforation crossbar
 *    cut out of it — reads as both a stage and a ticket stub.
 *  - A bright spark dot to the upper right echoes the inline "·" separator
 *    used throughout the brand ("Allsale · Events").
 *  - Instrument Serif wordmark, General Sans uppercase tagline. Matches the
 *    existing header rhythm so the new mark drops in without restyling.
 *
 * Usage:
 *   <Logo />                    — full lockup (mark + wordmark + ·events)
 *   <Logo variant="mark" />     — just the mark (favicon / square avatar)
 *   <Logo variant="wordmark" /> — wordmark only, no mark
 *   <Logo size={48} />          — control the mark height in px
 */
const ACCENT = "var(--accent, #FF4F00)";
const BG = "var(--bg, #0B0B0E)";

export function LogoMark({ size = 28, accent = ACCENT, bg = BG, ...rest }) {
  // 40×32 viewBox keeps the spark dot from cropping at small sizes.
  return (
    <svg
      width={(size * 40) / 32}
      height={size}
      viewBox="0 0 40 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      {...rest}
    >
      {/* A-peak triangle / stage silhouette */}
      <path d="M14 3.2 L27 28 L1 28 Z" fill={accent} />
      {/* Ticket-perforation crossbar — the negative space forms the "A" bar */}
      <rect x="5.2" y="18.6" width="17.6" height="3.2" rx="0.6" fill={bg} />
      {/* 3 perforation dots inside the crossbar for ticket-stub texture */}
      <circle cx="9.5" cy="20.2" r="0.7" fill={accent} />
      <circle cx="14" cy="20.2" r="0.7" fill={accent} />
      <circle cx="18.5" cy="20.2" r="0.7" fill={accent} />
      {/* Spark dot — the "event" signifier (matches the inline · separator) */}
      <circle cx="34" cy="7.5" r="3.4" fill={accent} />
      <circle cx="34" cy="7.5" r="1.4" fill="#FFD6BD" />
    </svg>
  );
}

export default function Logo({
  variant = "lockup",
  size = 28,
  textColor = "var(--text)",
  tagColor = "var(--accent)",
  className = "",
  ...rest
}) {
  if (variant === "mark") {
    return <LogoMark size={size} className={className} {...rest} />;
  }

  return (
    <span
      className={`inline-flex items-baseline gap-2 ${className}`}
      data-testid="brand-logo"
      {...rest}
    >
      {variant === "lockup" && (
        <LogoMark size={size} style={{ alignSelf: "center" }} />
      )}
      <span
        className="serif tracking-tight leading-none"
        style={{ color: textColor, fontSize: `${size * 1.05}px` }}
      >
        Allsale
      </span>
      <span
        className="uppercase tracking-[0.3em] leading-none"
        style={{ color: tagColor, fontSize: `${size * 0.34}px` }}
      >
        ·events
      </span>
    </span>
  );
}
