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
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";

// Sensible fallbacks while the public-settings call is in-flight. These match
// the backend's env-var defaults in `fees.py` (PLATFORM_FEE_BPS=500 → 5%,
// STRIPE_FEE_FLAT=0.30). DB-stored admin overrides are fetched lazily.
const DEFAULT_PLATFORM_PCT = 5;        // 5 %
const DEFAULT_PLATFORM_FLAT = 0.30;    // $0.30 per ticket
const DEFAULT_STRIPE_PCT = 2.7;        // 2.7 %  (NZ domestic card)
const TICKET_PROTECTION_BPS = 650;     // 6.5 %

export function estimateBuyerFees(faceValue, opts = {}) {
  if (!faceValue || faceValue <= 0) return { fees: 0, total: 0, organizerNet: 0 };
  const platformPct = (opts.platformPct ?? DEFAULT_PLATFORM_PCT) / 100;
  const platformFlat = opts.platformFlat ?? DEFAULT_PLATFORM_FLAT;
  const stripePct = (opts.stripePct ?? DEFAULT_STRIPE_PCT) / 100;

  if (opts.absorbFees) {
    // Inclusive mode — buyer pays exactly `faceValue`; fees come out of the
    // organizer's payout instead. We return fees=0 so checkout UI hides the
    // "+ fees" line, plus `organizerNet` for the organizer-facing preview.
    const platform = faceValue * platformPct;
    const stripeFee = faceValue * stripePct + platformFlat;
    return {
      fees: 0,
      total: round2(faceValue),
      organizerNet: round2(Math.max(0, faceValue - platform - stripeFee)),
      absorbedFees: round2(platform + stripeFee),
    };
  }

  // Exclusive (default) — gross-up so buyer covers all fees.
  const platform = faceValue * platformPct;
  const total = (faceValue + platform + platformFlat) / Math.max(1e-6, 1 - stripePct);
  const fees = total - faceValue;
  return { fees: round2(fees), total: round2(total), organizerNet: round2(faceValue) };
}

export function estimateTicketProtection(subtotal) {
  if (!subtotal || subtotal <= 0) return 0;
  return round2(subtotal * (TICKET_PROTECTION_BPS / 10000));
}

// Single-flight cache so multiple components mounting at once only issue one
// network request. Refreshes when the user reloads.
let _settingsPromise = null;
function loadFeeSettings() {
  if (!_settingsPromise) {
    _settingsPromise = api.get("/fees/public-settings")
      .then((r) => ({
        platformPct: r.data?.platform_pct,
        platformFlat: r.data?.platform_flat_per_ticket,
        stripePct: r.data?.stripe_pct,
      }))
      .catch(() => ({
        platformPct: DEFAULT_PLATFORM_PCT,
        platformFlat: DEFAULT_PLATFORM_FLAT,
        stripePct: DEFAULT_STRIPE_PCT,
      }));
  }
  return _settingsPromise;
}

export function useFeeSettings() {
  const [settings, setSettings] = useState({
    platformPct: DEFAULT_PLATFORM_PCT,
    platformFlat: DEFAULT_PLATFORM_FLAT,
    stripePct: DEFAULT_STRIPE_PCT,
  });
  useEffect(() => {
    let cancelled = false;
    loadFeeSettings().then((s) => { if (!cancelled) setSettings(s); });
    return () => { cancelled = true; };
  }, []);
  return settings;
}

function round2(n) { return Math.round(n * 100) / 100; }
