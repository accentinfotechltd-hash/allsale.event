import { useEffect } from "react";

/**
 * Swap the active PWA manifest while the scanner pages are mounted, then
 * restore the main-site manifest on unmount.
 *
 * Why we mutate the existing <link> instead of appending a new one:
 * browsers (Chrome, Safari) honour the FIRST <link rel="manifest"> in
 * tree order. The static <link rel="manifest" href="/manifest.json"> in
 * public/index.html is always first — appending a second one is dead
 * code for installability. By mutating its `href` in place we keep tree
 * order the same and the browser picks up the scanner manifest, so the
 * "Add to Home Screen" prompt installs the right app.
 *
 * On unmount (SPA navigation away from /scan) we restore the original
 * href so visiting other pages re-advertises the main Allsale app.
 *
 * Pass `enabled=false` (default true) to opt out without violating the
 * rules-of-hooks — useful when one component handles both scanner-public
 * and authenticated-internal modes.
 */
export function useScannerManifest(enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined;
    const link = document.querySelector('link[rel="manifest"]');
    if (!link) return undefined;
    const originalHref = link.getAttribute("href") || "/manifest.json";
    link.setAttribute("href", "/scanner.webmanifest");

    const theme = document.querySelector('meta[name="theme-color"]');
    const originalTheme = theme?.getAttribute("content") || null;
    theme?.setAttribute("content", "#0e0e10");

    return () => {
      link.setAttribute("href", originalHref);
      if (theme && originalTheme !== null) theme.setAttribute("content", originalTheme);
    };
  }, [enabled]);
}
