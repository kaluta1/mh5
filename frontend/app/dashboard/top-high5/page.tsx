"use client"

import * as React from "react"
import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@/hooks/use-auth"
import { useLanguage } from "@/contexts/language-context"
import { contestService, TopHigh5Contest, TopHigh5Level, TopHigh5Response } from "@/services/contest-service"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Trophy,
  Search,
  ArrowRightCircle,
  Building2,
  Flag,
  Map as MapIcon,
  Globe2,
  Globe,
  ExternalLink,
} from "lucide-react"

const LEVEL_OPTIONS: Array<{
  value: TopHigh5Level
  label: string
  icon: React.ComponentType<{ className?: string }>
  requiresCountry: boolean
  helper: string
}> = [
  { value: "city", label: "City", icon: Building2, requiresCountry: true, helper: "Top 5 per city (filtered by country)" },
  { value: "country", label: "Country", icon: Flag, requiresCountry: true, helper: "Top 5 for the selected country" },
  { value: "regional", label: "Regional", icon: MapIcon, requiresCountry: true, helper: "Top 5 per region (filtered by country)" },
  { value: "continent", label: "Continent", icon: Globe2, requiresCountry: true, helper: "Top 5 per continent (filtered by country)" },
  { value: "global", label: "Global", icon: Globe, requiresCountry: false, helper: "Top 5 worldwide — no country filter" },
]

/** Anchor for deep links: `/dashboard/top-high5#th5-<contestId>-<contestantId>` scrolls to the row. */
function topHigh5DomId(contestId: number, contestantId: number) {
  return `th5-${contestId}-${contestantId}`
}

function TopHigh5Skeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-56 w-full" />
      <Skeleton className="h-56 w-full" />
    </div>
  )
}

export default function TopHigh5Page() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [countryInput, setCountryInput] = useState("")
  const [roundIdInput, setRoundIdInput] = useState("")
  const [activeLevel, setActiveLevel] = useState<TopHigh5Level>("country")
  const [data, setData] = useState<TopHigh5Response | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeCountry, setActiveCountry] = useState("")
  const [activeRoundId, setActiveRoundId] = useState<number | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)
  const [isAutoRefreshing, setIsAutoRefreshing] = useState(false)
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  // Flag so we only seed the country input from the signed-in user once, never
  // overwriting whatever the user has typed afterwards.
  const [didSeedCountry, setDidSeedCountry] = useState(false)

  const currentLevelMeta = useMemo(
    () => LEVEL_OPTIONS.find((opt) => opt.value === activeLevel) ?? LEVEL_OPTIONS[1],
    [activeLevel],
  )

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/")
    }
  }, [isLoading, isAuthenticated, router])

  useEffect(() => {
    if (didSeedCountry) return
    if (!isLoading && isAuthenticated) {
      const fallbackCountry =
        (user as any)?.country || (user as any)?.author_country || "Tanzania"
      const urlRoundIdRaw = searchParams?.get("round_id") || ""
      const urlLevelRaw = (searchParams?.get("level") || "").toLowerCase() as TopHigh5Level
      const urlCountryRaw = searchParams?.get("country") || ""
      const parsedRoundId = urlRoundIdRaw && !Number.isNaN(Number(urlRoundIdRaw)) ? Number(urlRoundIdRaw) : undefined
      const initialLevel: TopHigh5Level = LEVEL_OPTIONS.some((o) => o.value === urlLevelRaw)
        ? urlLevelRaw
        : "country"
      const initialCountry = urlCountryRaw || fallbackCountry

      setCountryInput(initialCountry)
      setRoundIdInput(urlRoundIdRaw)
      setActiveLevel(initialLevel)
      setDidSeedCountry(true)
      fetchData({ country: initialCountry, roundId: parsedRoundId, level: initialLevel })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isAuthenticated, user?.id, didSeedCountry])

  const fetchData = async (opts: {
    country: string
    level: TopHigh5Level
    roundId?: number
    silent?: boolean
  }) => {
    try {
      if (!opts.silent) {
        setLoading(true)
      } else {
        setIsAutoRefreshing(true)
      }
      setError(null)
      const isGlobal = opts.level === "global"
      const trimmedCountry = opts.country.trim()
      const response = await contestService.getTopHigh5ByCountry({
        country: isGlobal ? undefined : trimmedCountry,
        roundId: opts.roundId,
        level: opts.level,
      })
      setData(response)
      setActiveCountry(isGlobal ? "" : trimmedCountry)
      setActiveRoundId(opts.roundId)
      setLastUpdatedAt(new Date())
    } catch (e: any) {
      setError(e?.message || "Failed to load Top High5")
      setData(null)
    } finally {
      if (!opts.silent) {
        setLoading(false)
      } else {
        setIsAutoRefreshing(false)
      }
    }
  }

  const handleLevelChange = (next: string) => {
    const nextLevel = next as TopHigh5Level
    if (nextLevel === activeLevel) return
    setActiveLevel(nextLevel)
    const parsed = roundIdInput && !Number.isNaN(Number(roundIdInput)) ? Number(roundIdInput) : undefined
    fetchData({ country: countryInput, level: nextLevel, roundId: parsed })
  }

  const handleSearch = () => {
    const parsed = roundIdInput && !Number.isNaN(Number(roundIdInput)) ? Number(roundIdInput) : undefined
    fetchData({ country: countryInput, level: activeLevel, roundId: parsed })
  }

  const filteredContests = useMemo<TopHigh5Contest[]>(() => data?.contests || [], [data])

  // Group contests by category so the dashboard renders one section per category,
  // matching the per-category layout requested by the team.
  const contestsByCategory = useMemo<Array<{ category: string; contests: TopHigh5Contest[] }>>(() => {
    const groups = new Map<string, TopHigh5Contest[]>()
    for (const c of filteredContests) {
      const key = (c.category_name && c.category_name.trim()) || "Uncategorized"
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(c)
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => a.localeCompare(b, undefined, { sensitivity: "base" }))
      .map(([category, contests]) => ({ category, contests }))
  }, [filteredContests])

  // Near real-time refresh loop: poll every 5s when tab is visible and page is active.
  useEffect(() => {
    if (!isAuthenticated) return
    // Non-global levels require a country context to refresh; global does not.
    if (activeLevel !== "global" && !activeCountry) return
    let intervalId: ReturnType<typeof setInterval> | null = null

    const refresh = () =>
      fetchData({
        country: activeCountry,
        level: activeLevel,
        roundId: activeRoundId,
        silent: true,
      })

    const tick = () => {
      if (document.visibilityState !== "visible") return
      void refresh()
    }

    intervalId = setInterval(tick, 5000)

    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh()
    }
    const onWindowFocus = () => void refresh()
    // Same-tab refresh signal from MyHigh5 reorder flow
    const onVoteChanged = () => void refresh()

    document.addEventListener("visibilitychange", onVisibility)
    window.addEventListener("focus", onWindowFocus)
    window.addEventListener("vote-changed", onVoteChanged)

    return () => {
      if (intervalId) clearInterval(intervalId)
      document.removeEventListener("visibilitychange", onVisibility)
      window.removeEventListener("focus", onWindowFocus)
      window.removeEventListener("vote-changed", onVoteChanged)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, activeCountry, activeRoundId, activeLevel])

  // Deep link: scroll to `#th5-<contestId>-<contestantId>` after rows render (category funnel).
  useEffect(() => {
    if (loading || !filteredContests.length) return
    const id = window.location.hash.replace(/^#/, "")
    if (!id || !id.startsWith("th5-")) return
    const el = document.getElementById(id)
    if (!el) return
    requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
    })
  }, [loading, filteredContests, contestsByCategory])

  if (isLoading || loading) {
    return <TopHigh5Skeleton />
  }
  if (!isAuthenticated) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center text-white shadow">
          <Trophy className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Top High5</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t("dashboard.myhigh5.description") ||
              "Top 5 by country for each nomination category and migration preview."}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-4">
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Stage
          </div>
          <Tabs value={activeLevel} onValueChange={handleLevelChange}>
            <TabsList className="flex flex-wrap h-auto gap-1 bg-gray-100 dark:bg-gray-800 p-1">
              {LEVEL_OPTIONS.map((opt) => {
                const Icon = opt.icon
                return (
                  <TabsTrigger key={opt.value} value={opt.value} className="gap-1.5">
                    <Icon className="w-4 h-4" />
                    {opt.label}
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </Tabs>
          <p className="text-xs text-gray-500 dark:text-gray-400">{currentLevelMeta.helper}</p>
        </div>

        <div className="flex flex-col md:flex-row gap-3 md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              value={countryInput}
              onChange={(e) => setCountryInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch()
              }}
              placeholder={
                currentLevelMeta.requiresCountry
                  ? "Country (e.g. Tanzania, Benin)"
                  : "Country filter disabled for Global"
              }
              disabled={!currentLevelMeta.requiresCountry}
              className="pl-9"
            />
          </div>
          <Input
            value={roundIdInput}
            onChange={(e) => setRoundIdInput(e.target.value.replace(/[^0-9]/g, ""))}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSearch()
            }}
            placeholder="Round id (optional, e.g. 3 = March 2026)"
            className="md:w-72"
            inputMode="numeric"
          />
          <Button onClick={handleSearch}>Show Top High5</Button>
        </div>

        {data && (
          <div className="text-xs text-gray-500 dark:text-gray-400 flex flex-wrap items-center gap-2">
            <span>Round: {data.round_name} (id {data.round_id})</span>
            <span>|</span>
            <span>Stage: {(data.level || activeLevel).toUpperCase()}</span>
            {activeLevel !== "global" && (
              <>
                <span>|</span>
                <span>Country: {data.country || activeCountry}</span>
              </>
            )}
            <span>|</span>
            <span>{isAutoRefreshing ? "Refreshing live..." : "Live sync every 5s"}</span>
            {lastUpdatedAt && (
              <>
                <span>|</span>
                <span>Last update: {lastUpdatedAt.toLocaleTimeString()}</span>
              </>
            )}
            {data.fallback_applied && (
              <>
                <span>|</span>
                <span className="text-amber-700 dark:text-amber-400">
                  Auto-selected latest round with winners
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 text-red-700 p-3 text-sm">
          {error}
        </div>
      )}

      {!filteredContests.length ? (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 p-5">
          <div className="text-center text-gray-500 py-6">
            No country winners found for this selection.
          </div>
          {data?.diagnostics && (
            <div className="mt-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  Diagnostics (helps explain empty results)
                </div>
                <button
                  type="button"
                  className="text-xs text-myhigh5-primary hover:underline"
                  onClick={() => setShowDiagnostics((v) => !v)}
                >
                  {showDiagnostics ? "Hide" : "Show"}
                </button>
              </div>
              {showDiagnostics && (
                <pre className="mt-2 text-xs bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded-lg p-3 overflow-x-auto">
                  {JSON.stringify(data.diagnostics, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-8">
          {contestsByCategory.map(({ category, contests }, categoryIndex) => (
            <section
              key={category}
              id={`th5-cat-${categoryIndex}`}
              className="space-y-3 scroll-mt-24"
            >
              <h2 className="text-lg font-bold text-gray-900 dark:text-white border-l-4 border-myhigh5-primary pl-3">
                {category}
              </h2>
              <div className="space-y-4">
                {contests.map((contest, idx) => (
                  <div
                    key={`${contest.contest_id}-${contest.country_group ?? "group"}-${idx}`}
                    className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden"
                  >
                    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/60 border-b border-gray-200 dark:border-gray-700">
                      <h3 className="font-semibold text-gray-900 dark:text-white">
                        {contest.contest_name}
                        {contest.country_group && (
                          <span className="ml-2 inline-flex items-center rounded-full bg-myhigh5-primary/10 text-myhigh5-primary px-2 py-0.5 text-xs font-medium">
                            {contest.country_group}
                          </span>
                        )}
                      </h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {contest.from_level}
                        {contest.to_level ? (
                          <>
                            <ArrowRightCircle className="inline w-3 h-3 mx-1" />
                            {contest.to_level}
                          </>
                        ) : (
                          <span className="ml-1">(final stage)</span>
                        )}
                        {" | "}Top {contest.promotion_limit} migrate
                      </p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-gray-100 dark:bg-gray-800">
                          <tr>
                            <th className="px-3 py-2 text-left">Rank</th>
                            <th className="px-3 py-2 text-left">Nominator</th>
                            <th className="px-3 py-2 text-left">Stars</th>
                            <th className="px-3 py-2 text-left">Shares</th>
                            <th className="px-3 py-2 text-left">Likes</th>
                            <th className="px-3 py-2 text-left">Comments</th>
                            <th className="px-3 py-2 text-left">Views</th>
                          </tr>
                        </thead>
                        <tbody>
                          {/*
                            Only show the "Top High5" — i.e. the nominators who would migrate
                            to the next stage. Anything outside the top 5 is excluded.
                          */}
                          {contest.rows
                            .filter((row) => row.migrates_next_stage)
                            .map((row) => (
                              <tr
                                key={row.contestant_id}
                                id={topHigh5DomId(contest.contest_id, row.contestant_id)}
                                className="bg-emerald-50/70 dark:bg-emerald-900/10 scroll-mt-20"
                              >
                                <td className="px-3 py-2 font-semibold">{row.rank}</td>
                                <td className="px-3 py-2">
                                  <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0">
                                      <div className="font-medium text-gray-900 dark:text-white">
                                        {row.author_name || row.contestant_title || `Nominator #${row.contestant_id}`}
                                      </div>
                                      {row.contestant_title && (
                                        <div className="text-xs text-gray-500">{row.contestant_title}</div>
                                      )}
                                    </div>
                                    <Link
                                      href={`/dashboard/contests/${contest.contest_id}/contestant/${row.contestant_id}?entryType=nomination`}
                                      className="flex-shrink-0 rounded-md p-1 text-myhigh5-primary hover:bg-myhigh5-primary/10"
                                      title={t("dashboard.myhigh5.open_top_entry") || "Watch this entry"}
                                      aria-label={t("dashboard.myhigh5.open_top_entry") || "Watch this entry"}
                                    >
                                      <ExternalLink className="h-4 w-4" />
                                    </Link>
                                  </div>
                                </td>
                                <td className="px-3 py-2">{row.stars_points}</td>
                                <td className="px-3 py-2">{row.shares}</td>
                                <td className="px-3 py-2">{row.likes}</td>
                                <td className="px-3 py-2">{row.comments}</td>
                                <td className="px-3 py-2">{row.views}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

