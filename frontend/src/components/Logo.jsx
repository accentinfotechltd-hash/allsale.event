/**
 * Allsale Events brand logo.
 *
 * Uses the official uploaded brand artwork (`/allsale-logo.png`).
 * The PNG is mostly transparent margin around the wordmark, so we
 * apply a generous negative-margin trim via CSS to keep the lockup
 * compact in headers and footers.
 *
 * Variants:
 *   <Logo />              — default header lockup (height-tuned for navbar)
 *   <Logo size={64} />    — taller (auth cards / hero)
 *   <Logo variant="mark" /> — kept for compatibility (still returns the image)
 */
export function LogoMark({ size = 28, className = "", ...rest }) {
  // Image is square (1254×1254) with the wordmark filling the middle band.
  // Using object-fit: contain inside a fixed box keeps it crisp at any size.
  return (
    <img
      src="/allsale-logo.png"
      alt="Allsale Events"
      width={size}
      height={size}
      style={{ width: size, height: size, objectFit: "contain", display: "inline-block" }}
      className={className}
      {...rest}
    />
  );
}

export default function Logo({
  size = 36,
  className = "",
  variant = "lockup",
  ...rest
}) {
  // The brand artwork already contains the "Allsale" + "EVENT" wordmark,
  // so the lockup variant is just the image itself rendered at a larger size.
  if (variant === "mark") {
    return <LogoMark size={size} className={className} {...rest} />;
  }

  // Lockup: render the artwork wider than tall (preserving aspect) so the
  // wordmark reads cleanly in headers without dwarfing nav links.
  const w = Math.round(size * 2.2);
  return (
    <img
      src="/allsale-logo.png"
      alt="Allsale Events"
      width={w}
      height={size}
      style={{ height: size, width: "auto", objectFit: "contain", display: "block" }}
      className={className}
      data-testid="brand-logo"
      {...rest}
    />
  );
}
