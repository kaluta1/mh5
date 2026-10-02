import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it, vi } from 'vitest'

import {
  COMMISSIONS_MAX_PAGES,
  COMMISSIONS_PAGE_SIZE,
  loadAllCommissions,
  type CommissionsQuery,
} from './commissions-loader'

const API_MAX = 100 // backend: limit: int = Query(10, ge=1, le=100)
const STATUSES = ['pending', 'approved', 'paid', 'cancelled']

/** A fake of the real endpoint: validates limit like FastAPI, filters, slices. */
function fakeApi(all: Array<Record<string, unknown>>) {
  const calls: CommissionsQuery[] = []
  const fetchPage = vi.fn(async (params: CommissionsQuery) => {
    calls.push(params)
    const limit = Number(params.limit)
    if (limit > API_MAX || limit < 1) {
      return { status: 422, data: { detail: [{ type: 'less_than_equal', loc: ['query', 'limit'], input: String(limit) }] } }
    }
    const matching = all.filter(
      (r) => (!params.status || r.status === params.status) && (!params.product_type || r.product_type_code === params.product_type),
    )
    const skip = Number(params.skip)
    return { status: 200, data: matching.slice(skip, skip + limit) }
  })
  return { fetchPage, calls }
}

const rows = (n: number, extra: (i: number) => Record<string, unknown> = () => ({})) =>
  Array.from({ length: n }, (_, i) => ({ id: i + 1, amount: 1, status: 'paid', ...extra(i) }))

describe('loadAllCommissions', () => {
  it('uses the API maximum as page size', () => {
    expect(COMMISSIONS_PAGE_SIZE).toBe(API_MAX)
  })

  it('loads a short history in one valid request', async () => {
    const { fetchPage, calls } = fakeApi(rows(7))
    const result = await loadAllCommissions(fetchPage, { sort_by: 'date' })
    expect(result).toMatchObject({ ok: true, pages: 1, truncated: false })
    expect(result.ok && result.rows).toHaveLength(7)
    expect(calls).toEqual([{ sort_by: 'date', limit: 100, skip: 0 }])
  })

  it('loads an empty history without error', async () => {
    const { fetchPage } = fakeApi([])
    expect(await loadAllCommissions(fetchPage)).toEqual({ ok: true, rows: [], pages: 1, truncated: false })
  })

  it('reads every page, so a history above 100 rows is not truncated', async () => {
    const { fetchPage, calls } = fakeApi(rows(250))
    const result = await loadAllCommissions(fetchPage, { sort_by: 'date' })
    expect(result.ok && result.rows.map((r) => r.id)).toEqual(rows(250).map((r) => r.id))
    expect(calls.map((c) => c.skip)).toEqual([0, 100, 200])
    expect(result.ok && result.truncated).toBe(false)
  })

  it('asks for one more page when the history is an exact multiple of the page size', async () => {
    const { fetchPage, calls } = fakeApi(rows(200))
    const result = await loadAllCommissions(fetchPage)
    expect(result.ok && result.rows).toHaveLength(200)
    expect(calls.map((c) => c.skip)).toEqual([0, 100, 200])
  })

  it('never requests more than the API allows, whatever page size is asked for', async () => {
    for (const asked of [200, 1000, 0, -5, Number.NaN]) {
      const { fetchPage, calls } = fakeApi(rows(130))
      const result = await loadAllCommissions(fetchPage, {}, asked)
      expect(result.ok).toBe(true)
      expect(calls.every((c) => Number(c.limit) >= 1 && Number(c.limit) <= API_MAX)).toBe(true)
    }
  })

  it.each(STATUSES)('keeps the %s status filter on every page', async (status) => {
    const data = rows(520, (i) => ({ status: STATUSES[i % 4] }))
    const { fetchPage, calls } = fakeApi(data)
    const result = await loadAllCommissions(fetchPage, { sort_by: 'amount', status })
    expect(result.ok && result.rows).toHaveLength(130)
    expect(result.ok && result.rows.every((r) => r.status === status)).toBe(true)
    expect(calls).toHaveLength(2)
    expect(calls.every((c) => c.status === status && c.sort_by === 'amount')).toBe(true)
  })

  it('sends no status filter for All and keeps the product type filter', async () => {
    const data = rows(150, (i) => ({ product_type_code: i % 2 ? 'kyc_verification' : 'annual_membership' }))
    const all = fakeApi(data)
    expect((await loadAllCommissions(all.fetchPage, { sort_by: 'date' })).ok).toBe(true)
    expect(all.calls.every((c) => !('status' in c))).toBe(true)
    const typed = fakeApi(data)
    const result = await loadAllCommissions(typed.fetchPage, { sort_by: 'date', product_type: 'kyc_verification' })
    expect(result.ok && result.rows).toHaveLength(75)
    expect(typed.calls.every((c) => c.product_type === 'kyc_verification')).toBe(true)
  })

  it('reports a failed page as status + detail and stops', async () => {
    const fetchPage = vi.fn(async () => ({ status: 422, data: { detail: [{ type: 'less_than_equal' }] } }))
    const result = await loadAllCommissions(fetchPage)
    expect(result).toEqual({ ok: false, status: 422, detail: [{ type: 'less_than_equal' }] })
    expect(fetchPage).toHaveBeenCalledTimes(1)
  })

  it('stops at the safety cap and says the history is truncated', async () => {
    const fetchPage = vi.fn(async (p: CommissionsQuery) => ({ status: 200, data: rows(Number(p.limit)) }))
    const result = await loadAllCommissions(fetchPage)
    expect(fetchPage).toHaveBeenCalledTimes(COMMISSIONS_MAX_PAGES)
    expect(result.ok && result.truncated).toBe(true)
  })
})

describe('commissions page', () => {
  const root = join(__dirname, '..')
  const page = readFileSync(join(root, 'app', 'dashboard', 'commissions', 'page.tsx'), 'utf8')

  it('loads its history only through the paginated loader', () => {
    expect(page).toMatch(/loadAllCommissions\(/)
    expect(page).toMatch(/COMMISSIONS_ENDPOINT/)
    expect(page).not.toMatch(/limit:\s*\d+/)
    expect(page).not.toMatch(/\/api\/v1\/affiliates\/commissions['"`]/) // no second, unpaginated list call
  })

  it('still sends the sort, product type and status filters', () => {
    expect(page).toMatch(/sort_by: sortBy/)
    expect(page).toMatch(/listParams\.product_type = typeFilter/)
    expect(page).toMatch(/listParams\.status = filter/)
  })

  it('never renders a raw backend payload to the member', () => {
    expect(page).not.toMatch(/JSON\.stringify/)
    expect(page).not.toMatch(/setLoadError\([^)]*result\.(detail|status)/)
    expect(page).toMatch(/console\.error\('Commissions request failed', result\.status, result\.detail\)/)
    expect(page).toMatch(/onClick=\{\(\) => loadCommissionsData\(\)\}/) // retry stays available
  })

  it('has no export request that could bypass pagination', () => {
    // The Export button is not wired to any request today.
    expect(page).not.toMatch(/\/export|limit=\d+/)
  })
})

describe('dashboard list requests respect the API page ceiling', () => {
  it('commission and affiliate pages', () => {
    const root = join(__dirname, '..', 'app', 'dashboard')
    for (const file of [['commissions', 'page.tsx'], ['affiliates', 'page.tsx'], ['affiliates', 'list', 'page.tsx']]) {
      const source = readFileSync(join(root, ...file), 'utf8')
      for (const m of source.matchAll(/limit[:=]\s*(\d+)/g)) expect(Number(m[1]), file.join('/')).toBeLessThanOrEqual(100)
    }
  })
})
