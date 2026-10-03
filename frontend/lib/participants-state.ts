/**
 * A participant (or application) list is always in exactly one of these states.
 * A failed request is ERROR: it must never be shown as EMPTY ("no participants
 * yet"), because that tells the member something false.
 */
export type ListViewState = 'LOADING' | 'ERROR' | 'EMPTY' | 'READY'

export function listViewState(input: {
  loading: boolean
  error?: unknown
  count: number
}): ListViewState {
  if (input.loading) return 'LOADING'
  if (input.error) return 'ERROR'
  return input.count > 0 ? 'READY' : 'EMPTY'
}

/**
 * Runs a list request and reports its outcome explicitly, so callers cannot
 * confuse "the request failed" with "the list is empty".
 */
export async function loadList<T>(
  request: () => Promise<T[] | null | undefined>,
): Promise<{ ok: true; rows: T[] } | { ok: false; error: unknown }> {
  try {
    const rows = await request()
    if (!Array.isArray(rows)) {
      return { ok: false, error: new Error('Unexpected response') }
    }
    return { ok: true, rows }
  } catch (error) {
    return { ok: false, error }
  }
}
