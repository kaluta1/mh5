/**
 * The rate shown next to a commission is derived from that commission's own
 * amounts (commission / commissionable base). It is never a constant: the
 * current program pays the direct sponsor at the rate of the live policy, and
 * historical rows keep whatever rate they were really paid at.
 */
export function commissionRatePercent(amount: unknown, baseAmount: unknown): number | null {
  const a = Number(amount)
  const b = Number(baseAmount)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= 0 || a < 0) return null
  return Math.round((a / b) * 1000) / 10
}

/** "20%", "2.5%", or "" when the row carries no commissionable base. */
export function formatCommissionRate(amount: unknown, baseAmount: unknown): string {
  const rate = commissionRatePercent(amount, baseAmount)
  if (rate === null) return ''
  return `${Number.isInteger(rate) ? rate : rate.toFixed(1)}%`
}
