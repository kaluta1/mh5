'use client'

import { useEffect, useMemo, useState } from 'react'
import { browserTimeZone, call, durationMinutes, errorDetail, formatDuration, type Json, timeZones } from './ad-api'

const PLACEMENT_TEXT: Record<string, string> = {
  IN_FEED: 'In-feed', SIDEBAR: 'Desktop sidebar', IN_CONTENT: 'Contest-entry panel',
}
const PAGE_TEXT: Record<string, string> = {
  FEED: 'Feeds', CONTEST_LISTING: 'Contest listings', CONTEST_ENTRY: 'Contest-entry pages', DISCOVERY: 'Discovery',
  POST: 'Posts', PROFILE: 'Profiles', MARKETPLACE: 'Marketplace',
}

/** Package-first campaign setup: package -> budget -> targeting -> schedule. Saves a DRAFT (incomplete drafts
 * are allowed); nothing is charged or reserved until the campaign is submitted. */
export function CampaignForm({ catalog, onCreated }: { catalog: Json; onCreated: (message: string) => void }) {
  const packages: Json[] = catalog.packages || []
  const firstDraftable = packages.find((p) => p.can_draft)?.code || 'cpm'
  const [pkg, setPkg] = useState<string>(firstDraftable)
  const [name, setName] = useState('')
  const [budget, setBudget] = useState('')
  const [rate, setRate] = useState('')
  const [dailyCap, setDailyCap] = useState('')
  const [startMode, setStartMode] = useState<'approval' | 'scheduled'>('approval')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [tz, setTz] = useState(browserTimeZone())
  const [countriesMode, setCountriesMode] = useState<'ALL' | 'LIST'>('ALL')
  const [countries, setCountries] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [pagesMode, setPagesMode] = useState<'ALL' | 'LIST'>('ALL')
  const [pages, setPages] = useState<string[]>([])
  const [placements, setPlacements] = useState<string[]>(['IN_FEED'])
  const [estimate, setEstimate] = useState<Json | null>(null)
  const [error, setError] = useState('')

  const selected = packages.find((p) => p.code === pkg) || packages[0] || {}
  const countryNames: Record<string, string> = useMemo(
    () => Object.fromEntries((catalog.countries || []).map((c: Json) => [c.code, c.name])), [catalog.countries])
  const pageTypes: Json[] = useMemo(() => catalog.page_types || [], [catalog.page_types])
  const allowedPlacements = useMemo(() => {
    const rendered = pageTypes.filter((p) => p.rendered && (pagesMode === 'ALL' || pages.includes(p.code)))
    return Array.from(new Set(rendered.flatMap((p) => p.placements as string[])))
  }, [pageTypes, pagesMode, pages])
  const chosenPlacements = placements.filter((p) => allowedPlacements.includes(p))
  const matches = (catalog.countries || []).filter((c: Json) => !countries.includes(c.code) && query.trim()
    && (c.name.toLowerCase().includes(query.trim().toLowerCase()) || c.code.toLowerCase() === query.trim().toLowerCase()))
    .slice(0, 8)

  useEffect(() => {
    setEstimate(null)
    if (!(Number(budget) > 0)) return
    let cancelled = false
    call('get', `/advertiser/estimate?package=${encodeURIComponent(pkg)}&budget=${encodeURIComponent(budget)}`
      + (rate && pkg !== 'cpm' ? `&rate=${encodeURIComponent(rate)}` : ''))
      .then((r) => { if (!cancelled) setEstimate(r) })
      .catch((e) => { if (!cancelled) setEstimate({ error: errorDetail(e) }) })
    return () => { cancelled = true }
  }, [pkg, budget, rate])

  const belowMinimum = pkg === 'cpm' && selected.minimum_budget && budget !== ''
    && Number(budget) < Number(selected.minimum_budget)
  const duration = startMode === 'scheduled' ? durationMinutes(start, end) : null
  const listEmpty = (countriesMode === 'LIST' && countries.length === 0) || (pagesMode === 'LIST' && pages.length === 0)
  const problems = [
    !name.trim() && 'Enter a private campaign name',
    belowMinimum && `The minimum campaign budget is ${selected.minimum_budget} USD`,
    dailyCap && budget && Number(dailyCap) > Number(budget) && 'The daily limit cannot be above the budget',
    duration != null && duration <= 0 && 'The end must be after the start',
    listEmpty && 'Choose at least one country / page type, or select all eligible',
    !selected.can_draft && (selected.disabled_reason || 'This package is not available'),
  ].filter(Boolean) as string[]

  const save = async () => {
    setError('')
    try {
      await call('post', '/advertiser/campaigns', {
        name: name.trim(), package: pkg, budget: budget || null, daily_cap: dailyCap || null,
        unit_rate: pkg !== 'cpm' && rate ? rate : null, timezone: tz,
        start_at: startMode === 'scheduled' && start ? start : null, end_at: end || null,
        placements: chosenPlacements, countries_mode: countriesMode, countries: countriesMode === 'LIST' ? countries : [],
        page_types_mode: pagesMode, page_types: pagesMode === 'LIST' ? pages : [],
      })
      onCreated('Draft campaign saved. Add a creative, then submit it for review.')
    } catch (e) {
      setError(errorDetail(e))
    }
  }

  const budgetInfo: Json = catalog.budget || {}
  return (
    <section data-testid="campaign-form" className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
      <h2 className="font-semibold">New campaign</h2>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">1. Advertising package</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {packages.map((p) => (
            <label key={p.code} data-testid={`package-card-${p.code}`}
              className={`block rounded-lg border p-3 text-xs ${p.can_draft ? 'cursor-pointer' : 'opacity-60'} ${pkg === p.code
                ? 'border-blue-600 ring-1 ring-blue-600' : 'border-gray-200 dark:border-gray-700'}`}>
              <span className="flex items-center gap-2">
                <input type="radio" name="package" value={p.code} checked={pkg === p.code} disabled={!p.can_draft}
                  onChange={() => { setPkg(p.code); setRate('') }} aria-label={p.name} />
                <span className="text-sm font-semibold">{p.name}</span>
                <span className="ml-auto font-medium">{p.price_label}</span>
              </span>
              <span className="mt-1 block text-gray-600 dark:text-gray-300">Billed for: {p.billable_event}</span>
              <span className="block text-gray-500">{p.minimum_note || ''}{p.minimum_note ? ' · ' : ''}Media: {(p.supported_media || []).join(', ')}
                {' · '}Placements: {(p.supported_placements || []).map((x: string) => PLACEMENT_TEXT[x] || x).join(', ')}</span>
              {p.disabled_reason ? <span className="mt-1 block text-amber-700 dark:text-amber-400" data-testid={`package-reason-${p.code}`}>
                Not available: {p.disabled_reason}</span> : null}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="mb-1 text-sm font-medium">2. Name and budget</legend>
        <label className="text-sm">Private campaign name (only you and MyHigh5 see it)
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Campaign name" maxLength={160}
            className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
        </label>
        <label className="text-sm">Total budget (USD)
          <input type="number" min="0" step="0.01" value={budget} onChange={(e) => setBudget(e.target.value)}
            aria-label="Total budget (USD)" className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
        </label>
        {pkg !== 'cpm' && !selected.booking ? (
          <label className="text-sm">Your rate (USD per {selected.billing_unit}, at least {selected.minimum_rate})
            <input type="number" min={selected.minimum_rate} step="0.000001" value={rate} placeholder={selected.minimum_rate}
              onChange={(e) => setRate(e.target.value)} aria-label="Rate" className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
        ) : null}
        {!selected.booking ? (
          <label className="text-sm">Daily spending limit (USD, optional)
            <input type="number" min="0" step="0.01" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)}
              aria-label="Daily spending limit (USD, optional)" className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
        ) : null}
        <div data-testid="budget-panel" className="rounded border border-gray-200 p-2 text-xs dark:border-gray-700 sm:col-span-2">
          <p>Available advertiser credit: <strong>{budgetInfo.available_credit ?? '—'} USD</strong></p>
          <p>Reserved from your credit when you submit: <strong>{budget || '0'} USD</strong> · Maximum campaign spend:
            {' '}<strong>{budget || '0'} USD</strong>{dailyCap ? <> · Daily limit: <strong>{dailyCap} USD</strong> (UTC day)</> : null}</p>
          <p>Fees: {budgetInfo.fees}</p>
          <p>Unused budget: {budgetInfo.unused_credit}</p>
          {budget && budgetInfo.available_credit != null && Number(budget) > Number(budgetInfo.available_credit) ? (
            <p className="text-amber-700 dark:text-amber-400">Your credit is lower than this budget: add credit before submitting.</p>
          ) : null}
        </div>
        <p data-testid="ad-estimate" className="text-sm text-gray-600 dark:text-gray-300 sm:col-span-2">
          {estimate?.error ? <span className="text-red-600">{estimate.error}</span>
            : estimate?.units != null ? `Up to ${Number(estimate.units).toLocaleString('en-US')} ${estimate.unit} for ${estimate.budget} USD at ${estimate.rate} USD (a maximum, not a delivery promise).`
              : estimate?.note ? estimate.note : 'Enter a budget to see what it can buy with this package.'}
          {belowMinimum ? <span className="ml-1 text-red-600">The minimum campaign budget is {selected.minimum_budget} USD.</span> : null}
        </p>
      </fieldset>

      <fieldset className="space-y-2 text-sm">
        <legend className="mb-1 font-medium">3. Where it shows</legend>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2"><input type="radio" name="pages-mode" checked={pagesMode === 'ALL'}
            onChange={() => setPagesMode('ALL')} />All eligible pages</label>
          <label className="flex items-center gap-2"><input type="radio" name="pages-mode" checked={pagesMode === 'LIST'}
            onChange={() => setPagesMode('LIST')} />Chosen page types</label>
        </div>
        {pagesMode === 'LIST' ? (
          <div className="flex flex-wrap gap-4" data-testid="page-types">
            {pageTypes.map((p) => (
              <label key={p.code} className={`flex items-center gap-2 ${p.rendered ? '' : 'opacity-50'}`}>
                <input type="checkbox" disabled={!p.rendered} checked={pages.includes(p.code)}
                  onChange={(e) => setPages(e.target.checked ? [...pages, p.code] : pages.filter((x) => x !== p.code))} />
                {PAGE_TEXT[p.code] || p.code}{p.rendered ? '' : ' (no ad slot yet)'}
              </label>
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-4" data-testid="placements">
          <span className="w-full text-xs text-gray-500">Placements</span>
          {['IN_FEED', 'SIDEBAR', 'IN_CONTENT'].map((p) => (
            <label key={p} className={`flex items-center gap-2 ${allowedPlacements.includes(p) ? '' : 'opacity-50'}`}>
              <input type="checkbox" disabled={!allowedPlacements.includes(p)} checked={chosenPlacements.includes(p)}
                onChange={(e) => setPlacements(e.target.checked ? [...placements, p] : placements.filter((x) => x !== p))} />
              {PLACEMENT_TEXT[p]}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 pt-2">
          <label className="flex items-center gap-2"><input type="radio" name="countries-mode" checked={countriesMode === 'ALL'}
            onChange={() => setCountriesMode('ALL')} />All eligible countries</label>
          <label className="flex items-center gap-2"><input type="radio" name="countries-mode" checked={countriesMode === 'LIST'}
            onChange={() => setCountriesMode('LIST')} />Chosen countries</label>
        </div>
        {countriesMode === 'LIST' ? (
          <div className="space-y-1" data-testid="country-picker">
            <div className="flex flex-wrap gap-1">
              {countries.map((c) => (
                <span key={c} className="flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-700">
                  {countryNames[c] || c} ({c})
                  <button type="button" aria-label={`Remove ${countryNames[c] || c}`} onClick={() => setCountries(countries.filter((x) => x !== c))}>×</button>
                </span>
              ))}
            </div>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search countries"
              aria-label="Search countries" className="w-full rounded border px-2 py-1 dark:bg-gray-900" />
            {matches.length ? (
              <ul role="listbox" className="max-h-40 overflow-auto rounded border dark:border-gray-700">
                {matches.map((c: Json) => (
                  <li key={c.code}>
                    <button type="button" role="option" aria-selected={false} className="w-full px-2 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-700"
                      onClick={() => { setCountries([...countries, c.code]); setQuery('') }}>{c.name} ({c.code})</button>
                  </li>
                ))}
              </ul>
            ) : null}
            {countries.length === 0 ? <p className="text-xs text-amber-700">No country chosen: the campaign would show nowhere.</p> : null}
          </div>
        ) : null}
      </fieldset>

      <fieldset className="space-y-2 text-sm">
        <legend className="mb-1 font-medium">4. Schedule</legend>
        <label className="block">Time zone
          <select value={tz} onChange={(e) => setTz(e.target.value)} aria-label="Time zone"
            className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900">
            {timeZones(tz).map((z) => <option key={z} value={z}>{z}</option>)}
          </select>
        </label>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2"><input type="radio" name="start-mode" checked={startMode === 'approval'}
            onChange={() => setStartMode('approval')} />Start after approval</label>
          <label className="flex items-center gap-2"><input type="radio" name="start-mode" checked={startMode === 'scheduled'}
            onChange={() => setStartMode('scheduled')} />Schedule a start</label>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {startMode === 'scheduled' ? (
            <label>Start ({tz})
              <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Start"
                className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
            </label>
          ) : null}
          <label>End ({tz})
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="End"
              className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
        </div>
        <p data-testid="schedule-preview" className="text-xs text-gray-500">
          {duration != null ? `Duration: ${formatDuration(duration)}. ` : ''}
          {catalog.launch}
        </p>
      </fieldset>

      {problems.length ? (
        <ul data-testid="form-problems" className="list-disc pl-5 text-xs text-amber-700 dark:text-amber-400">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      ) : null}
      {error ? <p role="alert" className="text-sm text-red-600">{error}</p> : null}
      <button type="button" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        disabled={problems.length > 0} onClick={save}>Save draft campaign</button>
      <p className="text-xs text-gray-500">Drafts can be incomplete. Nothing is reserved from your credit until you submit.</p>
    </section>
  )
}
