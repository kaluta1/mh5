import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { topHigh5RowClassName, TopHigh5ContestRows, formatRegisteredOn } from "./top-high5-rows"
import type { TopHigh5Row } from "@/services/contest-service"

const identityT = (key: string) => key

function row(overrides: Partial<TopHigh5Row>): TopHigh5Row {
  return {
    rank: 1,
    migrates_next_stage: false,
    contestant_id: 1,
    contestant_title: "Contestant",
    stars_points: 0,
    shares: 0,
    likes: 0,
    comments: 0,
    views: 0,
    ...overrides,
  }
}

describe("topHigh5RowClassName", () => {
  it("does not include the advancing highlight when migrates_next_stage is false", () => {
    // TEST 6: a zero-vote / non-advancing row must not look like it advanced.
    expect(topHigh5RowClassName({ migrates_next_stage: false })).not.toContain("emerald")
  })

  it("keeps the advancing highlight when migrates_next_stage is true", () => {
    // TEST 7: a genuinely advancing row keeps its existing presentation.
    expect(topHigh5RowClassName({ migrates_next_stage: true })).toContain("emerald")
  })
})

describe("TopHigh5ContestRows", () => {
  it("renders a zero-vote row (TEST 1)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={9}
          t={identityT}
          rows={[
            row({
              contestant_id: 1229,
              contestant_title: "Kikuletwa Hot Springs",
              stars_points: 0,
              migrates_next_stage: false,
            }),
          ]}
        />
      </table>,
    )
    expect(screen.getByText("Kikuletwa Hot Springs")).toBeInTheDocument()
  })

  it("keeps an advancing row visible (TEST 2)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={11}
          t={identityT}
          rows={[row({ contestant_id: 1219, contestant_title: "Utanipenda", migrates_next_stage: true })]}
        />
      </table>,
    )
    expect(screen.getByText("Utanipenda")).toBeInTheDocument()
  })

  it("renders every row the API returned, mixed advancing/non-advancing (TEST 3)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          rows={[
            row({ contestant_id: 1, contestant_title: "Zero Vote A", migrates_next_stage: false }),
            row({ contestant_id: 2, contestant_title: "Advancing B", migrates_next_stage: true }),
            row({ contestant_id: 3, contestant_title: "Zero Vote C", migrates_next_stage: false }),
          ]}
        />
      </table>,
    )
    expect(screen.getByText("Zero Vote A")).toBeInTheDocument()
    expect(screen.getByText("Advancing B")).toBeInTheDocument()
    expect(screen.getByText("Zero Vote C")).toBeInTheDocument()
    expect(screen.getAllByRole("row")).toHaveLength(3)
  })

  it("renders zero rows for an empty group without throwing (TEST 4)", () => {
    render(
      <table>
        <TopHigh5ContestRows contestId={1} t={identityT} rows={[]} />
      </table>,
    )
    expect(screen.queryAllByRole("row")).toHaveLength(0)
  })

  it("preserves exact API row order (TEST 5)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          rows={[
            row({ contestant_id: 30, contestant_title: "Third", rank: 3 }),
            row({ contestant_id: 10, contestant_title: "First", rank: 1 }),
            row({ contestant_id: 20, contestant_title: "Second", rank: 2 }),
          ]}
        />
      </table>,
    )
    const names = screen.getAllByRole("link").map((el) => el.textContent)
    expect(names).toEqual(["Third", "First", "Second"])
  })

  it("does not show the advancing highlight class on a non-advancing row (TEST 6)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          rows={[row({ contestant_id: 1, migrates_next_stage: false })]}
        />
      </table>,
    )
    expect(screen.getByRole("row").className).not.toContain("emerald")
  })

  it("shows the advancing highlight class on an advancing row (TEST 7)", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          rows={[row({ contestant_id: 1, migrates_next_stage: true })]}
        />
      </table>,
    )
    expect(screen.getByRole("row").className).toContain("emerald")
  })
})

describe("formatRegisteredOn", () => {
  // PART 9 / TEST 7-8: registered_at is the API's own authoritative field
  // (Contestant.registration_date), rendered as a short, scannable date
  // ("23 Jun 2026" style) with the full timestamp only in the tooltip.
  it("formats a real ISO timestamp as a short human-readable date", () => {
    const { label } = formatRegisteredOn("2026-06-23T10:15:00", "en")
    expect(label).toBe("Jun 23, 2026")
  })

  it("puts the full date+time in the tooltip title, not the visible label", () => {
    const { label, title } = formatRegisteredOn("2026-06-23T10:15:00", "en")
    expect(title).toContain("2026")
    expect(title.length).toBeGreaterThan(label.length)
  })

  it("renders a placeholder, not a crash, for a missing registered_at", () => {
    expect(formatRegisteredOn(null, "en").label).toBe("—")
    expect(formatRegisteredOn(undefined, "en").label).toBe("—")
  })

  it("renders a placeholder for an unparseable value instead of 'Invalid Date'", () => {
    expect(formatRegisteredOn("not-a-date", "en").label).toBe("—")
  })
})

describe("TopHigh5ContestRows: Registered On column", () => {
  it("renders each row's registered_at as a short formatted date", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          language="en"
          rows={[row({ contestant_id: 1, contestant_title: "Entry A", registered_at: "2026-06-23T10:15:00" })]}
        />
      </table>,
    )
    expect(screen.getByText("Jun 23, 2026")).toBeInTheDocument()
  })

  it("does not throw and shows a placeholder when registered_at is missing", () => {
    render(
      <table>
        <TopHigh5ContestRows
          contestId={1}
          t={identityT}
          rows={[row({ contestant_id: 1, contestant_title: "Entry B" })]}
        />
      </table>,
    )
    expect(screen.getByText("Entry B")).toBeInTheDocument()
    expect(screen.getByText("—")).toBeInTheDocument()
  })
})

describe("Tanzania / round 28 production response simulation", () => {
  // Actual rows captured from the live production API (GET /api/v1/seasons/top-high5
  // ?level=country&country=Tanzania&round_id=28), one per named group, each zero-vote.
  const productionGroups: Array<{ contestId: number; name: string; row: TopHigh5Row }> = [
    { contestId: 25, name: "Hip Hop Song Contest", row: row({ contestant_id: 1231, contestant_title: "Kipi Sijasikia" }) },
    { contestId: 215, name: "Men Fashion", row: row({ contestant_id: 1221, contestant_title: "Mustafa Hassanali" }) },
    { contestId: 217, name: "Qaswida Contest", row: row({ contestant_id: 1220, contestant_title: "Ijuwe Sira Ya Mtume (S.A.W)" }) },
    { contestId: 21, name: "Taarab Song Contest", row: row({ contestant_id: 1225, contestant_title: "La Uchungu Halisahauliki" }) },
    { contestId: 37, name: "Traditional Music Contest", row: row({ contestant_id: 1224, contestant_title: "Sindimba" }) },
  ]

  it.each(productionGroups)("renders the real backend-returned row for $name", ({ contestId, row: r }) => {
    render(
      <table>
        <TopHigh5ContestRows contestId={contestId} t={identityT} rows={[r]} />
      </table>,
    )
    expect(screen.getByText(r.contestant_title as string)).toBeInTheDocument()
    expect(screen.getAllByRole("row")).toHaveLength(1)
  })
})
