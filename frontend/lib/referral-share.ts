import { getEffectiveApiUrl, getEffectiveAppUrl } from '@/lib/config'

type ShareLinkResponse = {
  short_code: string
  short_url: string
  destination_url: string
}

type ReferralShareOptions = {
  apiBaseUrl?: string
  getAccessToken: () => Promise<string | null> | string | null
  allowedHosts?: string[]
  toast?: (message: string) => void
}

function hostsFromAppOrigin(): string[] {
  const hosts = new Set<string>(['myhigh5.com', 'www.myhigh5.com', 'localhost', '127.0.0.1'])
  try {
    const origin = getEffectiveAppUrl()
    const parsed = new URL(origin)
    if (parsed.hostname) {
      hosts.add(parsed.hostname)
      if (parsed.port) {
        hosts.add(`${parsed.hostname}:${parsed.port}`)
      }
    }
  } catch {
    /* ignore */
  }
  return [...hosts]
}

export class ReferralShareManager {
  private readonly apiBaseUrl: string
  private readonly getAccessToken: ReferralShareOptions['getAccessToken']
  private readonly allowedHosts: Set<string>
  private readonly toast: (message: string) => void
  private cache = new Map<string, string>()

  constructor(options: ReferralShareOptions) {
    this.apiBaseUrl = (options.apiBaseUrl ?? getEffectiveApiUrl()).replace(/\/+$/, '')
    this.getAccessToken = options.getAccessToken
    this.allowedHosts = new Set(options.allowedHosts ?? hostsFromAppOrigin())
    this.toast =
      options.toast ??
      ((message) => {
        console.info(message)
      })
  }

  async shorten(url: string): Promise<string> {
    const parsed = new URL(url, typeof window !== 'undefined' ? window.location.origin : getEffectiveAppUrl())

    const hostKey = parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname
    if (!this.allowedHosts.has(parsed.hostname) && !this.allowedHosts.has(hostKey)) {
      return url
    }

    const canonical = parsed.toString()
    const cached = this.cache.get(canonical)
    if (cached) return cached

    const token = await this.getAccessToken()
    if (!token) return url

    const response = await fetch(`${this.apiBaseUrl}/api/v1/share-links`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ url: canonical }),
    })

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error((payload as { detail?: string; error?: string }).detail ?? (payload as { error?: string }).error ?? 'Unable to create share link.')
    }

    const payload = (await response.json()) as ShareLinkResponse
    this.cache.set(canonical, payload.short_url)
    return payload.short_url
  }

  bindShareButtons(root: ParentNode = document): void {
    root.addEventListener('click', async (event) => {
      const target = event.target as HTMLElement | null
      const button = target?.closest<HTMLElement>('[data-referral-share]')
      if (!button) return

      event.preventDefault()

      const rawUrl =
        button.dataset.url ||
        button.closest('a')?.getAttribute('href') ||
        window.location.href

      try {
        const shortUrl = await this.shorten(rawUrl)
        await navigator.clipboard.writeText(shortUrl)
        this.toast('Referral share link copied.')
      } catch (error) {
        console.error(error)
        this.toast('The share link could not be created.')
      }
    })
  }

  bindAutomaticCopy(root: Document = document): void {
    root.addEventListener('copy', async (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null
      const anchor = target?.closest<HTMLAnchorElement>('a[href]')

      const selectedText = window.getSelection()?.toString().trim() ?? ''
      const candidate =
        anchor?.href ||
        this.extractInternalUrl(selectedText) ||
        this.getCanonicalPageUrl()

      if (!candidate) return

      event.preventDefault()

      try {
        const shortUrl = await this.shorten(candidate)

        if (event.clipboardData) {
          event.clipboardData.setData('text/plain', shortUrl)
        } else {
          await navigator.clipboard.writeText(shortUrl)
        }

        this.toast('Referral share link copied.')
      } catch (error) {
        console.error(error)

        if (event.clipboardData) {
          event.clipboardData.setData('text/plain', candidate)
        }

        this.toast('Original link copied because shortening failed.')
      }
    })
  }

  private getCanonicalPageUrl(): string | null {
    const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href
    const candidate = canonical || window.location.href
    return this.isInternal(candidate) ? candidate : null
  }

  private extractInternalUrl(text: string): string | null {
    if (!text) return null
    const match = text.match(/https?:\/\/[^\s<>"']+/i)
    if (!match) return null
    return this.isInternal(match[0]) ? match[0] : null
  }

  private isInternal(value: string): boolean {
    try {
      const url = new URL(value, window.location.origin)
      const hostKey = url.port ? `${url.hostname}:${url.port}` : url.hostname
      return this.allowedHosts.has(url.hostname) || this.allowedHosts.has(hostKey)
    } catch {
      return false
    }
  }
}

let sharedManager: ReferralShareManager | null = null

export function getReferralShareManager(
  options?: Partial<ReferralShareOptions>
): ReferralShareManager {
  if (!sharedManager) {
    sharedManager = new ReferralShareManager({
      getAccessToken: () =>
        typeof window !== 'undefined' ? localStorage.getItem('access_token') : null,
      ...options,
    })
  }
  return sharedManager
}

export async function shortenReferralUrl(url: string): Promise<string> {
  return getReferralShareManager().shorten(url)
}
