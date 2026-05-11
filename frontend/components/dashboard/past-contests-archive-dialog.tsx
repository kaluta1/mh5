"use client"

import * as React from "react"
import Link from "next/link"
import { CalendarClock, ChevronDown, ChevronRight, ExternalLink, Loader2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import ApiService, { type Contest, type Round } from "@/lib/api-service"
import { useLanguage } from "@/contexts/language-context"
import { regionalPoolForCountry } from "@/lib/regional-pool"

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  countryFallback: string
}

function formatYmd(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

function parseDay(s?: string): Date | null {
  if (!s) return null
  const d = new Date(s.includes("T") ? s : `${s}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

function roundDateBounds(r: Round): { start: Date; end: Date } | null {
  const keys = ["submission_start_date", "submission_end_date", "voting_start_date", "voting_end_date"] as const
  const dates: Date[] = []
  for (const k of keys) {
    const d = parseDay(r[k])
    if (d) dates.push(d)
  }
  if (!dates.length) return null
  const start = new Date(Math.min(...dates.map((x) => x.getTime())))
  const end = new Date(Math.max(...dates.map((x) => x.getTime())))
  return { start, end }
}

function rangesOverlap(aStart: Date, aEnd: Date, bStart: Date, bEnd: Date) {
  return aStart <= bEnd && aEnd >= bStart
}

function contestModeOf(c: Contest): "nomination" | "participation" {
  const m = (c as { contest_mode?: string }).contest_mode
  return m === "participation" ? "participation" : "nomination"
}

function buildViewOnlyContestHref(contest: Contest, roundId: number, country: string) {
  const params = new URLSearchParams()
  params.set("roundId", String(roundId))
  params.set("viewOnly", "true")
  const mode = contestModeOf(contest)
  params.set("entryType", mode)
  const level = String(contest.level || "").toLowerCase()
  if (["regional", "continent", "continental", "global"].includes(level)) {
    if (level === "regional") {
      const pool = regionalPoolForCountry(country)
      if (pool) params.set("region", pool)
    }
  } else if (country) {
    params.set("country", country)
  }
  return `/dashboard/contests/${contest.id}?${params.toString()}`
}

export function PastContestsArchiveDialog({ open, onOpenChange, countryFallback }: Props) {
  const { t } = useLanguage()
  const label =
    t("dashboard.contests.past_contests_archive") || "Past contests & Top High5"
  const subtitle =
    t("dashboard.contests.past_contests_archive_hint") ||
    "Browse completed periods: view-only categories and historical Top High5 for a date range."

  const [dateFrom, setDateFrom] = React.useState("")
  const [dateTo, setDateTo] = React.useState("")
  const [catalog, setCatalog] = React.useState<Round[]>([])
  const [loadingCatalog, setLoadingCatalog] = React.useState(false)
  const [expandedId, setExpandedId] = React.useState<number | null>(null)
  const [contestsByRound, setContestsByRound] = React.useState<Record<number, Contest[]>>({})
  const [loadingContestsRound, setLoadingContestsRound] = React.useState<number | null>(null)

  const country = (countryFallback || "").trim() || "Tanzania"

  React.useEffect(() => {
    if (!open) return
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - 30)
    setDateFrom(formatYmd(start))
    setDateTo(formatYmd(end))
  }, [open])

  const loadCatalog = React.useCallback(async () => {
    setLoadingCatalog(true)
    try {
      const data = await ApiService.getRounds({ limit: 100, contestLimit: 1, skip: 0 })
      setCatalog(Array.isArray(data) ? data : [])
    } catch {
      setCatalog([])
    } finally {
      setLoadingCatalog(false)
    }
  }, [])

  React.useEffect(() => {
    if (!open) return
    void loadCatalog()
  }, [open, loadCatalog])

  const filteredRounds = React.useMemo(() => {
    const ds = parseDay(dateFrom)
    const de = parseDay(dateTo)
    if (!ds || !de) return []
    const rangeStart = ds
    const rangeEnd = de
    if (rangeStart > rangeEnd) return []

    const out: Round[] = []
    for (const r of catalog) {
      const b = roundDateBounds(r)
      if (!b) continue
      if (rangesOverlap(b.start, b.end, rangeStart, rangeEnd)) {
        out.push(r)
      }
    }
    out.sort((a, b) => Number(b.id) - Number(a.id))
    return out
  }, [catalog, dateFrom, dateTo])

  const applyPresetDays = (days: number) => {
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - days)
    setDateFrom(formatYmd(start))
    setDateTo(formatYmd(end))
  }

  const toggleRound = async (rid: number) => {
    if (expandedId === rid) {
      setExpandedId(null)
      return
    }
    setExpandedId(rid)
    if (contestsByRound[rid]) return
    setLoadingContestsRound(rid)
    try {
      const data = await ApiService.getRounds({ roundId: rid, contestLimit: 200, contestSkip: 0 })
      const list = data?.[0]?.contests || []
      setContestsByRound((prev) => ({ ...prev, [rid]: list }))
    } finally {
      setLoadingContestsRound(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-left">
            <CalendarClock className="h-5 w-5 text-blue-600" aria-hidden />
            {label}
          </DialogTitle>
          <DialogDescription className="text-left">{subtitle}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => applyPresetDays(30)}>
              {t("dashboard.contests.past_range_last_30") || "Last 30 days"}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => applyPresetDays(90)}>
              {t("dashboard.contests.past_range_last_90") || "Last 90 days"}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => applyPresetDays(365)}>
              {t("dashboard.contests.past_range_last_12m") || "Last 12 months"}
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600 dark:text-gray-400">
                {t("dashboard.contests.past_range_from") || "From"}
              </span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-gray-600 dark:text-gray-400">
                {t("dashboard.contests.past_range_to") || "To"}
              </span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900"
              />
            </label>
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t("dashboard.contests.past_top_high5_country_note") || "Top High5 links use your country:"}{" "}
            <span className="font-medium text-gray-700 dark:text-gray-300">{country}</span>
          </p>

          {loadingCatalog ? (
            <div className="flex items-center gap-2 py-10 text-gray-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              {t("common.loading") || "Loading…"}
            </div>
          ) : !filteredRounds.length ? (
            <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-sm text-gray-500 dark:border-gray-700">
              {t("dashboard.contests.past_no_rounds") || "No contest periods overlap this range."}
            </div>
          ) : (
            <ul className="space-y-3">
              {filteredRounds.map((r) => {
                const b = roundDateBounds(r)
                const period =
                  b &&
                  `${b.start.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} – ${b.end.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`
                const isOpen = expandedId === r.id
                const contests = contestsByRound[r.id] || []
                const nomination = contests.filter((c) => contestModeOf(c) === "nomination")
                const participation = contests.filter((c) => contestModeOf(c) === "participation")
                const thCountry = `/dashboard/top-high5?round_id=${r.id}&country=${encodeURIComponent(country)}&level=country`
                const thRegional = `/dashboard/top-high5?round_id=${r.id}&country=${encodeURIComponent(country)}&level=regional`

                return (
                  <li
                    key={r.id}
                    className="rounded-xl border border-gray-200 bg-gray-50/80 dark:border-gray-700 dark:bg-gray-900/40"
                  >
                    <div className="flex flex-col gap-3 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="font-semibold text-gray-900 dark:text-white">{r.name || `Round ${r.id}`}</div>
                          {period && <div className="text-xs text-gray-500 dark:text-gray-400">{period}</div>}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" variant="secondary" size="sm" asChild>
                            <Link
                              href={`/dashboard/myhigh5?roundId=${r.id}`}
                              onClick={() => onOpenChange(false)}
                            >
                              {t("dashboard.contests.past_myhigh5") || "MyHigh5"}
                              <ExternalLink className="ml-1 h-3.5 w-3.5 opacity-70" />
                            </Link>
                          </Button>
                          <Button type="button" variant="secondary" size="sm" asChild>
                            <Link href={thCountry} onClick={() => onOpenChange(false)}>
                              {t("dashboard.contests.past_top_high5_country") || "Top High5 · Country"}
                              <ExternalLink className="ml-1 h-3.5 w-3.5 opacity-70" />
                            </Link>
                          </Button>
                          <Button type="button" variant="secondary" size="sm" asChild>
                            <Link href={thRegional} onClick={() => onOpenChange(false)}>
                              {t("dashboard.contests.past_top_high5_regional") || "Top High5 · Regional"}
                              <ExternalLink className="ml-1 h-3.5 w-3.5 opacity-70" />
                            </Link>
                          </Button>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => void toggleRound(r.id)}
                        className="flex w-full items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-sm font-medium text-gray-800 transition hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:hover:bg-gray-700/80"
                      >
                        <span>
                          {t("dashboard.contests.past_view_categories") || "Categories & participants (view only)"}
                        </span>
                        {loadingContestsRound === r.id ? (
                          <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                        ) : isOpen ? (
                          <ChevronDown className="h-4 w-4 text-gray-500" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-gray-500" />
                        )}
                      </button>

                      {isOpen && (
                        <div className="space-y-4 border-t border-gray-200 pt-3 dark:border-gray-600">
                          {loadingContestsRound === r.id ? (
                            <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              {t("common.loading") || "Loading…"}
                            </div>
                          ) : (
                            <>
                              {nomination.length > 0 && (
                                <div>
                                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    {t("dashboard.contests.nominate_tab") || "Nomination"}
                                  </div>
                                  <ul className="space-y-1.5">
                                    {nomination.map((c) => (
                                      <li
                                        key={`n-${c.id}`}
                                        className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-white px-2 py-1.5 text-sm dark:bg-gray-800"
                                      >
                                        <span className="font-medium text-gray-800 dark:text-gray-100">{c.name}</span>
                                        <Button variant="outline" size="sm" asChild>
                                          <Link
                                            href={buildViewOnlyContestHref(c, r.id, country)}
                                            onClick={() => onOpenChange(false)}
                                          >
                                            {t("dashboard.contests.past_view_participants") || "View"}
                                          </Link>
                                        </Button>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {participation.length > 0 && (
                                <div>
                                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    {t("dashboard.contests.participations") || "Participations"}
                                  </div>
                                  <ul className="space-y-1.5">
                                    {participation.map((c) => (
                                      <li
                                        key={`p-${c.id}`}
                                        className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-white px-2 py-1.5 text-sm dark:bg-gray-800"
                                      >
                                        <span className="font-medium text-gray-800 dark:text-gray-100">{c.name}</span>
                                        <Button variant="outline" size="sm" asChild>
                                          <Link
                                            href={buildViewOnlyContestHref(c, r.id, country)}
                                            onClick={() => onOpenChange(false)}
                                          >
                                            {t("dashboard.contests.past_view_participants") || "View"}
                                          </Link>
                                        </Button>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {!nomination.length && !participation.length && (
                                <div className="text-sm text-gray-500">
                                  {t("dashboard.contests.past_no_contests") || "No categories loaded for this period."}
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
