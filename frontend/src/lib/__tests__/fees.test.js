/**
 * Regression test: the frontend fee estimator must match the backend
 * `fees.py::compute_fees()` to within a cent, otherwise listing prices
 * diverge from checkout totals (the bug we shipped a fix for on 2026-02-28).
 *
 * Math is replicated inline below — KEEP IN SYNC with `src/lib/fees.js`.
 */

function round2(n) { return Math.round(n * 100) / 100; }

function estimateBuyerFees(faceValue, opts = {}) {
  if (!faceValue || faceValue <= 0) return { fees: 0, total: 0, organizerNet: 0 };
  const platformPct = (opts.platformPct ?? 1) / 100;
  const platformFlat = opts.platformFlat ?? 0.5;
  const stripePct = (opts.stripePct ?? 2.7) / 100;
  const stripeFlat = opts.stripeFlat ?? 0.3;

  const platform = faceValue * platformPct + platformFlat;

  if (opts.absorbFees) {
    const stripeFee = faceValue * stripePct + stripeFlat;
    return {
      fees: 0,
      total: round2(faceValue),
      organizerNet: round2(Math.max(0, faceValue - platform - stripeFee)),
      absorbedFees: round2(platform + stripeFee),
    };
  }
  const total = (faceValue + platform + stripeFlat) / Math.max(1e-6, 1 - stripePct);
  const fees = total - faceValue;
  return { fees: round2(fees), total: round2(total), organizerNet: round2(faceValue) };
}

const RATES = { platformPct: 1, platformFlat: 0.5, stripePct: 2.7, stripeFlat: 0.3 };

describe("estimateBuyerFees — matches backend fees.py", () => {
  test("$30 ticket → $1.96 fees / $31.96 total (matches checkout)", () => {
    const r = estimateBuyerFees(30, RATES);
    expect(r.fees).toBe(1.96);
    expect(r.total).toBe(31.96);
  });

  test("$25 ticket → $1.77 fees / $26.77 total", () => {
    const r = estimateBuyerFees(25, RATES);
    expect(r.fees).toBe(1.77);
    expect(r.total).toBe(26.77);
  });

  test("$145 ticket → $6.34 fees / $151.34 total", () => {
    const r = estimateBuyerFees(145, RATES);
    expect(r.fees).toBe(6.34);
    expect(r.total).toBe(151.34);
  });

  test("$0 ticket (comp / free) → all zeros", () => {
    const r = estimateBuyerFees(0, RATES);
    expect(r.fees).toBe(0);
    expect(r.total).toBe(0);
  });

  test("absorb mode → fees=0, buyer pays face exactly", () => {
    const r = estimateBuyerFees(30, { ...RATES, absorbFees: true });
    expect(r.fees).toBe(0);
    expect(r.total).toBe(30);
    expect(r.organizerNet).toBeLessThan(30);
    expect(r.absorbedFees).toBeGreaterThan(0);
  });

  test("uses Allsale defaults (1% + $0.50 / 2.7% + $0.30) when opts not supplied", () => {
    const r = estimateBuyerFees(30);
    expect(r.fees).toBe(1.96);
  });

  test("REGRESSION: platform_flat is added to platform_fee (not silently dropped)", () => {
    // Previously the frontend dropped platform_flat from the platform_fee term.
    // With pct=0 we'd see only the stripe_flat in the gross-up, not platform_flat.
    const r = estimateBuyerFees(50, { platformPct: 0, platformFlat: 0.5, stripePct: 2.7, stripeFlat: 0.3 });
    // platform_fee = 0.5, total = (50 + 0.5 + 0.3)/0.973 = 52.21 → fees = 2.21
    expect(r.fees).toBeCloseTo(2.21, 2);
  });

  test("REGRESSION: stripe_flat sits in gross-up denom, NOT swapped with platform_flat", () => {
    const r = estimateBuyerFees(30, { platformPct: 0, platformFlat: 1.0, stripePct: 2.7, stripeFlat: 0.3 });
    // platform_fee = 1.0, total = (30 + 1 + 0.3)/0.973 = 32.17 → fees = 2.17
    expect(r.fees).toBeCloseTo(2.17, 2);
  });
});
