/**
 * Kaluta KYC in the browser.
 *
 * The browser only ever holds the verification URL of a session that the
 * backend created with the secret API key. It opens that URL in the provider's
 * widget and then ASKS THE BACKEND what the result is: what the widget reports,
 * and the query parameters the provider appends on a redirect
 * (kyc_status, kyc_session_id), are hints the member could have edited.
 */

export const KALUTA_HOST = 'kalutakyc.com'
export const KALUTA_EMBED_SCRIPT = `https://${KALUTA_HOST}/embed.js`

/** Only an https page of the provider's own host is opened. */
export function isKalutaVerificationUrl(url: string | null | undefined): boolean {
  if (typeof url !== 'string' || !url.trim()) return false
  try {
    const parsed = new URL(url.trim())
    return parsed.protocol === 'https:' && parsed.host === KALUTA_HOST && !parsed.username && !parsed.password
  } catch {
    return false
  }
}

/** Statuses in which the provider's decision has not reached the backend yet. */
const UNDECIDED = new Set(['pending', 'in_progress'])

export function isUndecided(status: string | null | undefined): boolean {
  return typeof status === 'string' && UNDECIDED.has(status)
}

/**
 * The provider's decision reaches the backend on a webhook, usually a moment
 * after the widget closes. Read the status until it is decided, a few times
 * only: the page stays usable, and the member can always refresh later.
 */
export async function waitForDecision<T extends { status?: string | null }>(
  readStatus: () => Promise<T>,
  options: { attempts?: number; delayMs?: number; sleep?: (ms: number) => Promise<void> } = {},
): Promise<T> {
  const attempts = Math.max(1, options.attempts ?? 6)
  const delayMs = options.delayMs ?? 2500
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)))
  let last = await readStatus()
  for (let i = 1; i < attempts && isUndecided(last.status); i += 1) {
    await sleep(delayMs)
    last = await readStatus()
  }
  return last
}
