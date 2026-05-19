/**
 * Allsale Events brand logo (uses the official uploaded artwork).
 *
 * The PNG has been pre-trimmed so the artwork fills the file with only
 * a small transparent margin. Aspect ratio is ~1.49 : 1 (W : H).
 *
 *   <Logo />          — default header lockup (height-based)
 *   <Logo size={56} /> — taller for auth cards / hero
 *   <Logo variant="mark" /> — square crop for favicons / avatars
 */
const ASPECT = 1254 / 841; // matches the trimmed asset

export function LogoMark({ size = 40, className = "", ...rest }) {
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
  size = 48,
  className = "",
  variant = "lockup",
  ...rest
}) {
  if (variant === "mark") {
    return <LogoMark size={size} className={className} {...rest} />;
  }
  const w = Math.round(size * ASPECT);
  return (
    <img
      src="/allsale-logo.png"
      alt="Allsale Events"
      width={w}
      height={size}
      style={{ height: size, width: w, objectFit: "contain", display: "block" }}
      className={className}
      data-testid="brand-logo"
      {...rest}
    />
  );
}
