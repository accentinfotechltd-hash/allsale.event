/**
 * Client-side fee estimator — mirrors backend `fees.py:compute_fees()`.
 * Used purely for display (per-tier "+ $X fees" line). The backend is the
 * source of truth for the actual charge.
 */
const PLATFORM_FEE_BPS = 500;   // 5%
const STRIPE_FEE_BPS = 270;     // 2.7%
const STRIPE_FEE_FLAT = 0.30;   // $0.30 per transaction
const TICKET_PROTECTION_BPS = 650; // 6.5%

export function estimateBuyerFees(faceValue) {
  if (!faceValue || faceValue <= 0) return { fees: 0, total: 0 };
  const platform = faceValue * (PLATFORM_FEE_BPS / 10000);
  const stripePct = STRIPE_FEE_BPS / 10000;
  const total = (faceValue + platform + STRIPE_FEE_FLAT) / Math.max(1e-6, 1 - stripePct);
  const fees = total - faceValue;
  return { fees: round2(fees), total: round2(total) };
}

export function estimateTicketProtection(subtotal) {
  if (!subtotal || subtotal <= 0) return 0;
  return round2(subtotal * (TICKET_PROTECTION_BPS / 10000));
}

function round2(n) { return Math.round(n * 100) / 100; }
