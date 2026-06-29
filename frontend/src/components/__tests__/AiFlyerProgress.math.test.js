/**
 * Unit tests for AI flyer progress math + stage selection.
 * Pure-function tests — no React rendering needed.
 */

// Same math as in AiFlyerProgress.jsx — keep in sync if the curve changes.
const TARGET_PROGRESS = 95;
const progressAt = (e) => TARGET_PROGRESS * (1 - Math.exp(-e / 8));

const STAGES = [
  { at: 0, label: "Reading your event details…" },
  { at: 5, label: "Drafting a punchy headline…" },
  { at: 10, label: "Polishing the tagline & CTA…" },
  { at: 16, label: "Almost done — finalising the text…" },
];
const stageAt = (e) => {
  let s = STAGES[0];
  for (const c of STAGES) if (e >= c.at) s = c;
  return s.label;
};

describe("AI flyer progress curve", () => {
  test("starts at 0 when elapsed=0", () => {
    expect(progressAt(0)).toBe(0);
  });
  test("hits ~30% by 3 seconds (rewarding fast start)", () => {
    expect(progressAt(3)).toBeGreaterThan(28);
    expect(progressAt(3)).toBeLessThan(35);
  });
  test("hits ~60% by 8 seconds", () => {
    expect(progressAt(8)).toBeGreaterThan(58);
    expect(progressAt(8)).toBeLessThan(64);
  });
  test("never reaches 100% even at long elapsed", () => {
    expect(progressAt(60)).toBeLessThan(TARGET_PROGRESS);
    expect(progressAt(60)).toBeGreaterThan(94);
  });
  test("asymptotes toward 95%", () => {
    expect(progressAt(1000)).toBeCloseTo(95, 1);
  });
});

describe("AI flyer progress stages", () => {
  test("stage 1 at start", () => {
    expect(stageAt(0)).toBe("Reading your event details…");
    expect(stageAt(4.9)).toBe("Reading your event details…");
  });
  test("stage 2 at 5s", () => {
    expect(stageAt(5)).toBe("Drafting a punchy headline…");
    expect(stageAt(7)).toBe("Drafting a punchy headline…");
  });
  test("stage 3 at 10s", () => {
    expect(stageAt(10)).toBe("Polishing the tagline & CTA…");
    expect(stageAt(15.9)).toBe("Polishing the tagline & CTA…");
  });
  test("stage 4 at 16s+", () => {
    expect(stageAt(16)).toBe("Almost done — finalising the text…");
    expect(stageAt(30)).toBe("Almost done — finalising the text…");
  });
});
