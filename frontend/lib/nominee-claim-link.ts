/**
 * The one-time link a nominator passes on to the person they nominated.
 *
 * The token comes from the submission response and from nowhere else: the
 * backend returns it once, to the nominator, and keeps only its hash. A
 * nomination is published without being claimed, so the link is offered
 * whatever the entry's publication status; it is never a condition of it.
 * The token rides in the URL fragment, which browsers do not send to servers.
 */
export function nomineeClaimLink(
  response: { nominee_claim_token?: unknown } | null | undefined,
  origin: string | null | undefined,
): string | null {
  const token = response?.nominee_claim_token
  if (typeof token !== 'string' || !token.trim() || !origin) return null
  return `${origin.replace(/\/+$/, '')}/nominations/claim#token=${token}`
}
