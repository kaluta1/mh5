import { getEffectiveAppUrl } from '@/lib/config'

/**
 * A member's referral short URL: <site>/r/<code>. That page keeps the code for the sign-up and opens the
 * home page with ?ref=<code>. The site is the one the member is on (myhigh5.com in production).
 */
export function referralShortUrl(code: string): string {
  return `${getEffectiveAppUrl()}/r/${encodeURIComponent(code.trim())}`
}

/** Copies text; false when the browser refuses (no clipboard access, insecure page, permission denied). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to the older method */
  }
  if (typeof document === 'undefined') return false
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(area)
  }
}
