import Link from "next/link"
import { ExternalLink } from "lucide-react"
import type { TopHigh5Row } from "@/services/contest-service"

/** Anchor for deep links: `/dashboard/top-high5#th5-<contestId>-<contestantId>` scrolls to the row. */
export function topHigh5DomId(contestId: number, contestantId: number) {
  return `th5-${contestId}-${contestantId}`
}

/**
 * Row style only -- every row in contest.rows renders regardless. This is the
 * one place migrates_next_stage still matters: a genuinely advancing row gets
 * the highlight, a zero-vote (or otherwise non-advancing) row renders plainly.
 */
export function topHigh5RowClassName(row: Pick<TopHigh5Row, "migrates_next_stage">): string {
  return row.migrates_next_stage
    ? "bg-emerald-50/70 dark:bg-emerald-900/10 scroll-mt-20"
    : "scroll-mt-20"
}

/**
 * Purely presentational: renders every row the API returned for one contest
 * group, in API order. Kept out of page.tsx (a Next.js page file may only
 * export the framework's own special names) so the row-visibility contract
 * (all rows render; migrates_next_stage only styles) is directly unit-testable
 * without mounting the full connected page.
 */
export function TopHigh5ContestRows({
  contestId,
  rows,
  t,
}: {
  contestId: number
  rows: TopHigh5Row[]
  t: (key: string) => string
}) {
  return (
    <tbody>
      {rows.map((row) => (
        <tr
          key={row.contestant_id}
          id={topHigh5DomId(contestId, row.contestant_id)}
          className={topHigh5RowClassName(row)}
        >
          <td className="px-3 py-2 font-semibold">{row.rank}</td>
          <td className="px-3 py-2">
            <Link
              href={`/dashboard/contests/${contestId}/contestant/${row.contestant_id}?entryType=nomination`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-gray-900 dark:text-white font-medium hover:text-myhigh5-primary transition-colors"
              title={t("dashboard.myhigh5.open_top_entry") || "Watch this entry"}
              aria-label={t("dashboard.myhigh5.open_top_entry") || "Watch this entry"}
            >
              <span>{row.contestant_title || `Content #${row.contestant_id}`}</span>
              <ExternalLink className="h-4 w-4 text-myhigh5-primary" />
            </Link>
          </td>
          <td className="px-3 py-2">{row.stars_points}</td>
          <td className="px-3 py-2">{row.shares}</td>
          <td className="px-3 py-2">{row.likes}</td>
          <td className="px-3 py-2">{row.comments}</td>
          <td className="px-3 py-2">{row.views}</td>
        </tr>
      ))}
    </tbody>
  )
}
