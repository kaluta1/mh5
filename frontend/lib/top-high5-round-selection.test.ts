import { describe, expect, it } from "vitest"
import { nextRoundIdOnLevelChange, resolveTopHigh5RequestRoundId, topHigh5RoundIdPlaceholder } from "./top-high5-round-selection"

describe("resolveTopHigh5RequestRoundId", () => {
  it("returns undefined (auto) when nothing was explicitly selected", () => {
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: undefined })).toBeUndefined()
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: null })).toBeUndefined()
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "" })).toBeUndefined()
  })

  it("honors an explicit round id exactly as given, for COUNTRY", () => {
    // Regression example from the empty-results investigation: round 27 is
    // the currently-finalized Country round, but the point of this test is
    // that ANY explicit value passes through unchanged -- the function must
    // never recompute or override it.
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "27" })).toBe(27)
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: 27 })).toBe(27)
  })

  it("honors an explicit round id exactly as given, for REGIONAL", () => {
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "26" })).toBe(26)
  })

  it("does not silently redirect a manually selected, not-yet-finalized round", () => {
    // Round 28 has no finalized data yet (still voting) -- this function's
    // job is only to pass through what the user asked for; the backend (and
    // the UI's empty state) are responsible for communicating "not finalized
    // yet", not this resolver pretending a different round was meant.
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "28" })).toBe(28)
  })

  it("treats a non-numeric or non-positive value as auto rather than throwing", () => {
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "not-a-number" })).toBeUndefined()
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "0" })).toBeUndefined()
    expect(resolveTopHigh5RequestRoundId({ explicitRoundId: "-5" })).toBeUndefined()
  })
})

describe("nextRoundIdOnLevelChange", () => {
  it("always resolves to auto (undefined), regardless of the previous level's round", () => {
    // Proves COUNTRY -> REGIONAL, REGIONAL -> CONTINENTAL, CONTINENTAL -> GLOBAL,
    // GLOBAL -> COUNTRY (Phase 6) all re-resolve fresh instead of carrying a
    // round that may not be finalized at the newly-selected level.
    expect(nextRoundIdOnLevelChange()).toBeUndefined()
  })
})

describe("topHigh5RoundIdPlaceholder", () => {
  // Exact worked example from KALUTASOCIETY_TOPHIGH5_CALENDAR_MONTH_FIX:
  // current month = September 2026 -> City=Jul, Country=Jun, Regional=May,
  // Continental=Apr, Global=Mar. Each level's own target_month must show
  // its OWN right month/year, not a generic or hardcoded example.
  it("shows the right month/year for City's target_month", () => {
    expect(topHigh5RoundIdPlaceholder("2026-07-01", "en")).toBe("Round id (optional — showing July 2026)")
  })

  it("shows the right month/year for Country's target_month", () => {
    expect(topHigh5RoundIdPlaceholder("2026-06-01", "en")).toBe("Round id (optional — showing June 2026)")
  })

  it("shows the right month/year for Regional's target_month", () => {
    expect(topHigh5RoundIdPlaceholder("2026-05-01", "en")).toBe("Round id (optional — showing May 2026)")
  })

  it("shows the right month/year for Continental's target_month", () => {
    expect(topHigh5RoundIdPlaceholder("2026-04-01", "en")).toBe("Round id (optional — showing April 2026)")
  })

  it("shows the right month/year for Global's target_month", () => {
    expect(topHigh5RoundIdPlaceholder("2026-03-01", "en")).toBe("Round id (optional — showing March 2026)")
  })

  it("rolls over the year boundary correctly (January target)", () => {
    expect(topHigh5RoundIdPlaceholder("2026-11-01", "en")).toBe("Round id (optional — showing November 2026)")
  })

  it("falls back to a plain label when no target_month is available yet", () => {
    expect(topHigh5RoundIdPlaceholder(undefined, "en")).toBe("Round id (optional)")
    expect(topHigh5RoundIdPlaceholder(null, "en")).toBe("Round id (optional)")
    expect(topHigh5RoundIdPlaceholder("", "en")).toBe("Round id (optional)")
  })

  it("falls back to a plain label rather than 'Invalid Date' for an unparseable value", () => {
    expect(topHigh5RoundIdPlaceholder("not-a-date", "en")).toBe("Round id (optional)")
  })
})
