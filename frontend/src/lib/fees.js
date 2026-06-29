/**
 * Client-side fee estimator — mirrors backend `fees.py:compute_fees()`.
 *
 * The backend remains the source of truth for the actual charge. This module
 * is purely for display ("+ $X fees" line under each ticket tier).
 *
 * The numbers we *display* must match the admin's configured commission
 * (`platform_settings.commission`) or buyers see one price on the listing
 * page and a different price at checkout. Use `useFeeSettings()` (or
 * pre-fetch `/api/fees/public-settings`) and pass the values through.
 *
 * Formula MUST stay aligned with backend `fees.py::compute_fees` — both:
 *   platform_fee  = face × platform_pct/100 + platform_flat
 *   buyer_total   = (face + platform_fee + stripe_flat) / (1 - stripe_pct/100)
 *   stripe_fee    = buyer_total - face - platform_fee
 *   service_fee   = platform_fee + stripe_fee   ← this is "+ fees" on the listing
 *
 * The frontend used to OMIT `platform_flat` from the `platform_fee` term AND
 * substitute `platform_flat` where the `stripe_flat` should sit in the
 * gross-up denominator — which caused listings to under-quote by exactly
 * `(platform_flat - stripe_flat) / (1 - stripe_pct)` ≈ $0.20–0.30 on every
 * paid event. The fix below brings it into line with the backend.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";

// Sensible fallbacks while the public-settings call is in-flight. These match
// the admin's currently-configured values per `/api/fees/public-settings`
// (1% + $0.50 platform, 2.7% + $0.30 Stripe). If the public-settings call
// fails or the admin tweaks the DB, the real values arrive within ~100ms.
const DEFAULT_PLATFORM_PCT = 1;        // 1 %  (1% + $0.50 = Allsale rate)
const DEFAULT_PLATFORM_FLAT = 0.50;    // $0.50 per ticket
const DEFAULT_STRIPE_PCT = 2.7;        // 2.7 %  (NZ domestic card)
const DEFAULT_STRIPE_FLAT = 0.30;      // $0.30 per Stripe transaction
const TICKET_PROTECTION_BPS = 650;     // 6.5 %

export function estimateBuyerFees(faceValue, opts = {}) {
  if (!faceValue || faceValue <= 0) return { fees: 0, total: 0, organizerNet: 0 };
  const platformPct = (opts.platformPct ?? DEFAULT_PLATFORM_PCT) / 100;
  const platformFlat = opts.platformFlat ?? DEFAULT_PLATFORM_FLAT;
  const stripePct = (opts.stripePct ?? DEFAULT_STRIPE_PCT) / 100;
  const stripeFlat = opts.stripeFlat ?? DEFAULT_STRIPE_FLAT;

  // platform_fee = face × pct + flat   (matches backend `fees.py` exactly)
  const platform = faceValue * platformPct + platformFlat;

  if (opts.absorbFees) {
    // Inclusive mode — buyer pays exactly `faceValue`; fees come out of the
    // organizer's payout instead. We return fees=0 so checkout UI hides the
    // "+ fees" line, plus `organizerNet` for the organizer-facing preview.
    const stripeFee = faceValue * stripePct + stripeFlat;
    return {
      fees: 0,
      total: round2(faceValue),
      organizerNet: round2(Math.max(0, faceValue - platform - stripeFee)),
      absorbedFees: round2(platform + stripeFee),
    };
  }

  // Exclusive (default) — gross-up so buyer covers all fees.
  // buyer_total = (face + platform + stripe_flat) / (1 - stripe_pct)
  const total = (faceValue + platform + stripeFlat) / Math.max(1e-6, 1 - stripePct);
  const fees = total - faceValue;
  return { fees: round2(fees), total: round2(total), organizerNet: round2(faceValue) };
}

export function estimateTicketProtection(subtotal) {
  if (!subtotal || subtotal <= 0) return 0;
  return round2(subtotal * (TICKET_PROTECTION_BPS / 10000));
}

// Short-TTL cache so multiple components mounting at once share one fetch,
// but admin rate changes propagate to live buyer pages within ~60 seconds
// without requiring a hard refresh.
let _settingsPromise = null;
let _settingsFetchedAt = 0;
const FEE_SETTINGS_TTL_MS = 60_000;

function loadFeeSettings() {
  const now = Date.now();
  if (_settingsPromise && (now - _settingsFetchedAt) < FEE_SETTINGS_TTL_MS) {
    return _settingsPromise;
  }
  _settingsFetchedAt = now;
  _settingsPromise = api.get("/fees/public-settings")
    .then((r) => ({
      platformPct: r.data?.platform_pct ?? DEFAULT_PLATFORM_PCT,
      platformFlat: r.data?.platform_flat_per_ticket ?? DEFAULT_PLATFORM_FLAT,
      stripePct: r.data?.stripe_pct ?? DEFAULT_STRIPE_PCT,
      stripeFlat: r.data?.stripe_flat_per_ticket ?? DEFAULT_STRIPE_FLAT,
    }))
    .catch(() => ({
      platformPct: DEFAULT_PLATFORM_PCT,
      platformFlat: DEFAULT_PLATFORM_FLAT,
      stripePct: DEFAULT_STRIPE_PCT,
      stripeFlat: DEFAULT_STRIPE_FLAT,
    }));
  return _settingsPromise;
}

/** Invalidate the cache — call from /admin/settings after the admin saves a
 *  new commission rate so the next listing page render fetches fresh values. */
export function invalidateFeeSettingsCache() {
  _settingsPromise = null;
  _settingsFetchedAt = 0;
}

export function useFeeSettings() {
  const [settings, setSettings] = useState({
    platformPct: DEFAULT_PLATFORM_PCT,
    platformFlat: DEFAULT_PLATFORM_FLAT,
    stripePct: DEFAULT_STRIPE_PCT,
    stripeFlat: DEFAULT_STRIPE_FLAT,
  });
  useEffect(() => {
    let cancelled = false;
    loadFeeSettings().then((s) => { if (!cancelled) setSettings(s); });
    return () => { cancelled = true; };
  }, []);
  return settings;
}

function round2(n) { return Math.round(n * 100) / 100; }
