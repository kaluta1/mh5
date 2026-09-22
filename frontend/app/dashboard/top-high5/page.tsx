"use client"

import * as React from "react"
import { useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@/hooks/use-auth"
import { useLanguage } from "@/contexts/language-context"
import { contestService, TopHigh5Contest, TopHigh5Level, TopHigh5Response } from "@/services/contest-service"
import { nextRoundIdOnLevelChange, resolveTopHigh5RequestRoundId, topHigh5RoundIdPlaceholder } from "@/lib/top-high5-round-selection"
// `isRoundVotingLive` and the contest-round-tabs vote-calendar helpers are
// deliberately NOT imported here -- they answer "which cohort is voting
// right now" for the live Vote page, not "which round has finalized
// results", which is what Top High5 needs. See top-high5-round-selection.ts.
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Trophy, Search, ArrowRightCircle } from "lucide-react"
import { GeographyLevelIcon, type GeographyLevelIconKey } from "@/components/dashboard/geography-level-icons"
import { TopHigh5ContestRows } from "./top-high5-rows"

const LEVEL_OPTIONS: Array<{
  value: TopHigh5Level
  label: string
  geographyIcon: GeographyLevelIconKey
  requiresCountry: boolean
  helper: string
}> = [
  { value: "city", label: "City", geographyIcon: "city", requiresCountry: true, helper: "Top 5 per city (filtered by country)" },
  { value: "country", label: "Country", geographyIcon: "country", requiresCountry: true, helper: "Top 5 for the selected country" },
  { value: "regional", label: "Regional", geographyIcon: "regional", requiresCountry: true, helper: "Top 5 per region (filtered by country)" },
  { value: "continent", label: "Continent", geographyIcon: "continent", requiresCountry: true, helper: "Top 5 per continent (filtered by country)" },
  { value: "global", label: "Global", geographyIcon: "global", requiresCountry: false, helper: "Top 5 worldwide - no country filter" },
]

function getTopHigh5EmptyMessage(level: TopHigh5Level, t: (key: string) => string) {
  switch (level) {
    case "city":
      return t("dashboard.contests.empty_nomination_city") || "No nominated yet."
    case "regional":
      return t("dashboard.contests.empty_nomination_regional") || "No regional migration."
    case "continent":
      return t("dashboard.contests.empty_nomination_continental") || "No continental migration."
    case "global":
      return t("dashboard.contests.empty_nomination_global") || "No global migration."
    case "country":
    default:
      return t("dashboard.contests.empty_nomination_country") || "No country winners found for this selection."
  }
}

const topHigh5Cache = new Map<string, { data: TopHigh5Response; timestamp: number }>()
const TOP_HIGH5_CACHE_TTL = 30 * 1000
const TOP_HIGH5_BACKGROUND_REFRESH_MS = 15 * 1000

function topHigh5CacheKey(country: string, level: TopHigh5Level, roundId?: number, regionQuery?: string) {
  return `${level}-${roundId || "auto"}-${country.trim().toLowerCase() || "global"}-${(regionQuery || "").trim().toLowerCase()}`
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
  const { t, language } = useLanguage()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [countryInput, setCountryInput] = useState("")
  const [roundIdInput, setRoundIdInput] = useState("")
  const [categorySearch, setCategorySearch] = useState("")
  const [activeLevel, setActiveLevel] = useState<TopHigh5Level>("country")
  const [data, setData] = useState<TopHigh5Response | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeCountry, setActiveCountry] = useState("")
  const [activeRoundId, setActiveRoundId] = useState<number | undefined>(undefined)
  const [activeRegionQuery, setActiveRegionQuery] = useState("")
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
  // Only trust `data.target_month` when it's actually a response for the
  // level currently showing -- otherwise a stale month from a level the
  // user just switched away from would flash before the new request
  // resolves. See topHigh5RoundIdPlaceholder's own doc comment.
  const roundIdPlaceholder = useMemo(
    () => topHigh5RoundIdPlaceholder(data?.level === activeLevel ? data?.target_month : undefined, language),
    [data, activeLevel, language],
  )
  const levelOptions = useMemo(
    () =>
      LEVEL_OPTIONS.map((opt) => ({
        ...opt,
        label:
          opt.value === "city"
            ? t("dashboard.contests.level_city") || opt.label
            : opt.value === "country"
              ? t("dashboard.contests.level_country") || opt.label
              : opt.value === "regional"
                ? t("dashboard.contests.level_regional") || opt.label
                : opt.value === "continent"
                  ? t("dashboard.contests.level_continental") || opt.label
                  : t("dashboard.contests.level_global") || opt.label,
      })),
    [t],
  )

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/")
    }
  }, [isLoading, isAuthenticated, router])

  useEffect(() => {
    if (didSeedCountry) return
    if (!isLoading && isAuthenticated) {
      const seed = async () => {
        const fallbackCountry =
          (user as any)?.country || (user as any)?.author_country || "Tanzania"
        const urlRoundIdRaw = searchParams?.get("round_id") || searchParams?.get("roundId") || ""
        const urlLevelRaw = (searchParams?.get("level") || "").toLowerCase() as TopHigh5Level
        const urlCountryRaw = searchParams?.get("country") || ""
        // No explicit round (deep link or otherwise): defer entirely to the
        // backend's own resolution, which finds the latest round with real
        // finalized results for this level -- see top-high5-round-selection.ts.
        const resolvedRoundId = resolveTopHigh5RequestRoundId({ explicitRoundId: urlRoundIdRaw })
        const initialLevel: TopHigh5Level = LEVEL_OPTIONS.some((o) => o.value === urlLevelRaw)
          ? urlLevelRaw
          : "country"
        const initialCountry = urlCountryRaw || fallbackCountry
        setCountryInput(initialCountry)
        setRoundIdInput(resolvedRoundId ? String(resolvedRoundId) : "")
        setActiveLevel(initialLevel)
        setDidSeedCountry(true)

        void fetchData({ country: initialCountry, roundId: resolvedRoundId, level: initialLevel })
      }
      void seed()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, isAuthenticated, user?.id, didSeedCountry])

  const fetchData = async (opts: {
    country: string
    level: TopHigh5Level
    roundId?: number
    silent?: boolean
    regionQuery?: string
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
      const cacheKey = topHigh5CacheKey(isGlobal ? "" : trimmedCountry, opts.level, opts.roundId, opts.regionQuery)
      const cached = topHigh5Cache.get(cacheKey)
      if (
        opts.silent &&
        cached &&
        Date.now() - cached.timestamp < TOP_HIGH5_BACKGROUND_REFRESH_MS
      ) {
        setIsAutoRefreshing(false)
        return
      }
      if (!opts.silent && cached && Date.now() - cached.timestamp < TOP_HIGH5_CACHE_TTL) {
        setData(cached.data)
        setActiveCountry(isGlobal ? "" : trimmedCountry)
        setActiveRoundId(opts.roundId)
        setActiveRegionQuery(opts.level === "regional" ? (opts.regionQuery || "").trim().toLowerCase() : "")
        setLastUpdatedAt(new Date(cached.timestamp))
        setLoading(false)
      }
      const response = await contestService.getTopHigh5ByCountry({
        country: isGlobal ? undefined : trimmedCountry,
        roundId: opts.roundId,
        level: opts.level,
      })
      const normalizedRegionQuery = (opts.regionQuery || "").trim().toLowerCase()
      const nextData =
        opts.level === "regional" && normalizedRegionQuery
          ? {
              ...response,
              contests: (response.contests || []).filter((contest) =>
                (contest.country_group || "").toLowerCase().includes(normalizedRegionQuery),
              ),
            }
          : response
      setData(nextData)
      topHigh5Cache.set(cacheKey, { data: nextData, timestamp: Date.now() })
      setActiveCountry(isGlobal ? "" : trimmedCountry)
      setActiveRoundId(opts.roundId)
      setActiveRegionQuery(opts.level === "regional" ? normalizedRegionQuery : "")
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
    // A round finalized for the previous level is not necessarily finalized
    // for this one (e.g. Country closed for round 27 does not mean Regional
    // has closed for round 27 too) -- always re-resolve fresh via the
    // backend rather than carrying the old round over.
    const nextRoundId = nextRoundIdOnLevelChange()
    setRoundIdInput("")
    fetchData({ country: countryInput, level: nextLevel, roundId: nextRoundId })
  }

  const isLikelyRegionalSearch = (value: string) => {
    const text = value.trim().toLowerCase()
    if (!text) return false
    return /(west|east|north|south|central|africa|asia|europe|america|oceania|middle east|caribbean)/i.test(text)
  }

  const handleSearch = () => {
    const parsed = resolveTopHigh5RequestRoundId({ explicitRoundId: roundIdInput })
    if (activeLevel === "regional") {
      const raw = countryInput.trim()
      const fallbackCountry = (activeCountry || (user as any)?.country || (user as any)?.author_country || "").trim()
      const useRegionQuery = isLikelyRegionalSearch(raw)
      const countryForRequest = useRegionQuery ? fallbackCountry : raw
      fetchData({
        country: countryForRequest,
        level: activeLevel,
        roundId: parsed,
        regionQuery: useRegionQuery ? raw : "",
      })
      return
    }
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

  const visibleCategories = useMemo(() => {
    const q = categorySearch.trim().toLowerCase()
    if (!q) return contestsByCategory
    return contestsByCategory.filter(({ category }) =>
      category.toLowerCase().includes(q),
    )
  }, [contestsByCategory, categorySearch])

  // Near real-time refresh loop. Fifteen seconds keeps rankings fresh while
  // avoiding a continuous expensive request every five seconds per open tab.
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
        regionQuery: activeRegionQuery,
      })

    const tick = () => {
      if (document.visibilityState !== "visible") return
      void refresh()
    }

    intervalId = setInterval(tick, TOP_HIGH5_BACKGROUND_REFRESH_MS)

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
  }, [isAuthenticated, activeCountry, activeRoundId, activeLevel, activeRegionQuery])

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

  if (isLoading) {
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("dashboard.myhigh5.title") || "Top High5"}
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t("dashboard.myhigh5.description") ||
              "Top 5 by country for each nomination category and migration preview."}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-4">
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {t("dashboard.contests.filter_level") || "Stage"}
          </div>
          <Tabs value={activeLevel} onValueChange={handleLevelChange}>
            <TabsList className="flex flex-wrap h-auto gap-1 bg-gray-100 dark:bg-gray-800 p-1">
              {levelOptions.map((opt) => (
                <TabsTrigger key={opt.value} value={opt.value} className="gap-1.5">
                  <GeographyLevelIcon level={opt.geographyIcon} size={22} className="hidden sm:block" />
                  {opt.label}
                </TabsTrigger>
              ))}
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
              placeholder={activeLevel === "regional" ? "Search region or country" : (t("settings.country") || "Country")}
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
            placeholder={roundIdPlaceholder}
            className="md:w-72"
            inputMode="numeric"
          />
          <Button onClick={handleSearch}>{t("dashboard.myhigh5.show_top_high5") || "Show Top High5"}</Button>
        </div>

        <div className="flex flex-col md:flex-row gap-3 md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              value={categorySearch}
              onChange={(e) => setCategorySearch(e.target.value)}
              placeholder={t("dashboard.contests.search_placeholder") || "Search category"}
              className="pl-9"
            />
          </div>
        </div>

        {data && (
          <div className="text-xs text-gray-500 dark:text-gray-400 flex flex-wrap items-center gap-2">
            <span title={data.mixed_cohorts ? "Freshest cohort represented below -- individual contests may show an older cohort; see each contest's own stage line." : undefined}>
              {data.mixed_cohorts ? "Freshest round shown: " : "Round: "}
              {data.round_name} (id {data.round_id})
            </span>
            {data.mixed_cohorts && (
              <span className="text-amber-700 dark:text-amber-400">
                (results below span multiple cohorts -- each contest shows its own)
              </span>
            )}
            <span>|</span>
            <span>{t("dashboard.contests.filter_level") || "Stage"}: {(data.level || activeLevel).toUpperCase()}</span>
            {activeLevel !== "global" && (
              <>
                <span>|</span>
                <span>{t("settings.country") || "Country"}: {data.country || activeCountry}</span>
              </>
            )}
            <span>|</span>
            <span>{isAutoRefreshing ? (t("common.loading") || "Refreshing live...") : "Live sync every 5s"}</span>
            {lastUpdatedAt && (
              <>
                <span>|</span>
                <span>{t("common.refresh") || "Last update"}: {lastUpdatedAt.toLocaleTimeString()}</span>
              </>
            )}
            {data.fallback_applied && (
              <>
                <span>|</span>
                <span className="text-amber-700 dark:text-amber-400">
                  {t("dashboard.myhigh5.auto_selected_round") || "Auto-selected latest round with winners"}
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
            {loading
              ? (t("common.loading") || "Preparing Top High5...")
              : getTopHigh5EmptyMessage(activeLevel, t)}
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
      ) : !visibleCategories.length ? (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 p-5">
          <div className="text-center text-gray-500 py-6">
            {t("dashboard.contests.no_contests") || "No category matches your search."}
          </div>
        </div>
      ) : (
        <div className="space-y-8">
          {visibleCategories.map(({ category, contests }, categoryIndex) => (
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
                        {contest.round_name && (
                          <span className="ml-1">
                            {" | "}Cohort: {contest.round_name}
                            {contest.contest_mode ? ` (${contest.contest_mode})` : ""}
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-gray-100 dark:bg-gray-800">
                          <tr>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.rank") || "Rank"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.content") || "Content"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.registered_on") || "Registered On"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.points") || "Points"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.shares") || "Shares"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.likes") || "Likes"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.comments") || "Comments"}</th>
                            <th className="px-3 py-2 text-left">{t("dashboard.myhigh5.views") || "Views"}</th>
                          </tr>
                        </thead>
                        <TopHigh5ContestRows contestId={contest.contest_id} rows={contest.rows} t={t} language={language} />
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

