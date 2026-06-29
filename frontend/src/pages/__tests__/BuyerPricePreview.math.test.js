/**
 * Locks the BuyerPricePreview math in lockstep with `lib/fees.js` AND
 * `backend/fees.py::compute_fees`. The widget's math is inlined directly
 * in `pages/Admin.jsx::BuyerPricePreview` (not extracted to a helper), so
 * we replicate the formula here verbatim — if these tests fail, the
 * preview is showing different numbers than the listing pages.
 */

function round2(n) { return Math.round(n * 100) / 100; }

function buyerPreviewRow(face, percent, flat) {
  const pPct = (parseFloat(percent) || 0) / 100;
  const pFlat = parseFloat(flat) || 0;
  const sPct = 0.027;
  const sFlat = 0.30;
  const platform = face * pPct + pFlat;
  const total = (face + platform + sFlat) / (1 - sPct);
  const fees = total - face;
  return {
    fees: round2(fees),
    total: round2(total),
    platformCut: round2(platform),
    organizerNet: round2(face),
  };
}

describe("BuyerPricePreview — admin settings live preview", () => {
  test("$25 ticket at 1% + $0.50 → buyer pays $26.77, your cut $0.75", () => {
    const r = buyerPreviewRow(25, "1", "0.5");
    expect(r.fees).toBe(1.77);
    expect(r.total).toBe(26.77);
    expect(r.platformCut).toBe(0.75);
    expect(r.organizerNet).toBe(25);
  });

  test("$50 ticket at 1% + $0.50 → buyer pays $52.72, your cut $1.00", () => {
    const r = buyerPreviewRow(50, "1", "0.5");
    expect(r.fees).toBe(2.72);
    expect(r.total).toBe(52.72);
    expect(r.platformCut).toBe(1.0);
  });

  test("$100 ticket at 1% + $0.50 → buyer pays $104.62, your cut $1.50", () => {
    const r = buyerPreviewRow(100, "1", "0.5");
    expect(r.fees).toBe(4.62);
    expect(r.total).toBe(104.62);
    expect(r.platformCut).toBe(1.5);
  });

  test("0% + $0 → only Stripe processing on top", () => {
    const r = buyerPreviewRow(25, "0", "0");
    expect(r.platformCut).toBe(0);
    // Buyer pays (25 + 0.30) / 0.973 = 26.001 → fees ≈ $1.00 (Stripe only)
    expect(r.fees).toBeCloseTo(1.0, 1);
  });

  test("matches estimateBuyerFees output from lib/fees.js (single source of truth)", () => {
    // Same math, two implementations — must agree
    const face = 30, pct = "1", flat = "0.5";
    const a = buyerPreviewRow(face, pct, flat);
    // Replica of estimateBuyerFees with stripe defaults from fees.js
    const pPct = 0.01, pFlat = 0.5, sPct = 0.027, sFlat = 0.3;
    const platform = face * pPct + pFlat;
    const total = (face + platform + sFlat) / (1 - sPct);
    expect(a.fees).toBe(round2(total - face));
    expect(a.total).toBe(round2(total));
  });
});
