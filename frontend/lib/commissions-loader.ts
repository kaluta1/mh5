/**
 * Loads a member's commission history through the paginated API.
 *
 * GET /api/v1/affiliates/commissions accepts `limit` between 1 and 100 and
 * returns a plain array (no total). A page shorter than the page size is the
 * last one. The whole history is read page by page so nothing is silently cut
 * off, and no request ever asks for more than the API allows.
 */
export const COMMISSIONS_ENDPOINT = '/api/v1/affiliates/commissions'

/** The API's own ceiling (FastAPI: `limit: int = Query(10, ge=1, le=100)`). */
export const COMMISSIONS_PAGE_SIZE = 100

/** Safety stop so a misbehaving API can never loop forever (50 x 100 rows). */
export const COMMISSIONS_MAX_PAGES = 50

export type CommissionsQuery = Record<string, string | number>

export type CommissionsPageResponse = { status: number; data: unknown }

export type CommissionsPageFetcher = (params: CommissionsQuery) => Promise<CommissionsPageResponse>

export type CommissionsLoadResult =
  | { ok: true; rows: Record<string, unknown>[]; pages: number; truncated: boolean }
  | { ok: false; status: number; detail: unknown }

export async function loadAllCommissions(
  fetchPage: CommissionsPageFetcher,
  filters: CommissionsQuery = {},
  pageSize: number = COMMISSIONS_PAGE_SIZE,
): Promise<CommissionsLoadResult> {
  const limit = Math.min(Math.max(1, Math.floor(pageSize) || COMMISSIONS_PAGE_SIZE), COMMISSIONS_PAGE_SIZE)
  const rows: Record<string, unknown>[] = []

  for (let page = 0; page < COMMISSIONS_MAX_PAGES; page += 1) {
    const response = await fetchPage({ ...filters, limit, skip: page * limit })
    if (response.status !== 200) {
      const body = response.data
      const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail?: unknown }).detail : body
      return { ok: false, status: response.status, detail }
    }
    const batch = Array.isArray(response.data) ? (response.data as Record<string, unknown>[]) : []
    rows.push(...batch)
    if (batch.length < limit) {
      return { ok: true, rows, pages: page + 1, truncated: false }
    }
  }
  return { ok: true, rows, pages: COMMISSIONS_MAX_PAGES, truncated: true }
}
