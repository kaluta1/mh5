'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import api from '@/lib/api'
import { isAdRoute, type AdPageType, type AdSlotKind } from '@/lib/ads/placement'
import { useAdEligibility } from '@/hooks/use-ad-eligibility'
import { COOKIE_CONSENT_EVENT } from '@/components/ui/cookie-consent'
import { hasAdvertisingConsent } from '@/components/ads/adsense-loader'
import { normalizeMediaUrl } from '@/lib/media-url'
import { getEffectiveApiUrl } from '@/lib/config'

type Decision =
  | { fill: false; reason?: string }
  | {
      fill: true
      decision_id: string
      source: 'MYHIGH5' | 'ADSENSE'
      sponsored_label: string
      creative?: { headline: string; body?: string | null; image_url?: string | null; destination_url: string
        click_url?: string | null }
      adsense?: { client: string; slot: string }
    }

/** MRC/IAB display viewability: >= 50% of pixels in view for >= 1 continuous second. */
export const VIEWABLE_RATIO = 0.5
export const VIEWABLE_MS = 1000

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function sendEvent(decisionId: string, eventType: 'SERVED' | 'VIEWABLE', extra: Record<string, unknown> = {}) {
  api
    .post('/api/v1/ads/events', { decision_id: decisionId, event_id: uuid(), event_type: eventType, ...extra })
    .catch(() => undefined)
}

function useConsent(): boolean {
  const [consented, setConsented] = useState(false)
  useEffect(() => {
    const refresh = () => setConsented(hasAdvertisingConsent())
    refresh()
    window.addEventListener('storage', refresh)
    window.addEventListener(COOKIE_CONSENT_EVENT, refresh)
    return () => {
      window.removeEventListener('storage', refresh)
      window.removeEventListener(COOKIE_CONSENT_EVENT, refresh)
    }
  }, [])
  return consented
}

export interface AdSlotProps {
  pageType: AdPageType
  slotKind: AdSlotKind
  slotKey: string
  contestantId?: number | null
  className?: string
}

/**
 * One controlled ad placement. Renders nothing (no gap) unless: the route is allowed, the viewer
 * consented to advertising cookies, the backend says the viewer may receive ads, and the server
 * filled the slot. Always labelled "Sponsored". Reports one SERVED and at most one VIEWABLE event;
 * the server validates and charges. Google's ad code is never modified: AdSense units are measured
 * on their container only, and an unfilled AdSense unit is never reported as viewable.
 */
export function AdSlot({ pageType, slotKind, slotKey, contestantId, className }: AdSlotProps) {
  const pathname = usePathname()
  const allowedRoute = isAdRoute(pathname)
  const eligibility = useAdEligibility()
  const consented = useConsent()
  const [decision, setDecision] = useState<Decision | null>(null)
  const ref = useRef<HTMLDivElement | null>(null)
  const viewableSent = useRef(false)
  const eligible = eligibility.adsense || eligibility.myhigh5_ads

  useEffect(() => {
    if (!allowedRoute || !consented || !eligible) return
    let cancelled = false
    api
      .post('/api/v1/ads/decide', {
        page_type: pageType,
        slot_kind: slotKind,
        slot_key: slotKey.slice(0, 80),
        contestant_id: contestantId ?? null,
      })
      .then((res) => {
        if (!cancelled && res.status < 400) setDecision(res.data as Decision)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [allowedRoute, consented, eligible, pageType, slotKind, slotKey, contestantId])

  const filled = decision && decision.fill ? decision : null

  useEffect(() => {
    if (!filled) return
    sendEvent(filled.decision_id, 'SERVED')
    if (filled.source === 'ADSENSE') {
      try {
        const w = window as Window & { adsbygoogle?: unknown[] }
        ;(w.adsbygoogle = w.adsbygoogle || []).push({})
      } catch {
        /* provider script not loaded yet */
      }
    }
  }, [filled])

  useEffect(() => {
    const node = ref.current
    if (!filled || !node || typeof IntersectionObserver === 'undefined') return
    let timer: ReturnType<typeof setTimeout> | null = null
    let ratio = 0
    let since = 0
    const clear = () => {
      if (timer) clearTimeout(timer)
      timer = null
    }
    const fire = () => {
      if (viewableSent.current) return
      if (document.visibilityState !== 'visible') return
      const ins = node.querySelector('ins.adsbygoogle') as HTMLElement | null
      if (filled.source === 'ADSENSE' && (!ins || ins.getAttribute('data-ad-status') === 'unfilled')) return
      viewableSent.current = true
      sendEvent(filled.decision_id, 'VIEWABLE', {
        visible_ms: Math.round(performance.now() - since),
        visible_ratio: Math.min(1, Math.round(ratio * 1000) / 1000),
        page_visible: document.visibilityState === 'visible',
      })
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          ratio = entry.intersectionRatio
          if (ratio >= VIEWABLE_RATIO && !timer && !viewableSent.current) {
            since = performance.now()
            timer = setTimeout(fire, VIEWABLE_MS + 50)
          } else if (ratio < VIEWABLE_RATIO) {
            clear()
          }
        }
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1] },
    )
    observer.observe(node)
    const onHide = () => {
      if (document.visibilityState !== 'visible') clear()
    }
    document.addEventListener('visibilitychange', onHide)
    return () => {
      clear()
      observer.disconnect()
      document.removeEventListener('visibilitychange', onHide)
    }
  }, [filled])

  if (!allowedRoute || !consented || !eligible || !filled) return null

  const sidebarOnly = slotKind === 'SIDEBAR' ? 'hidden lg:block' : ''
  return (
    <aside
      ref={ref}
      aria-label="Sponsored"
      data-ad-source={filled.source}
      data-testid="ad-slot"
      className={`rounded-lg border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-3 ${sidebarOnly} ${className || ''}`}
    >
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {filled.sponsored_label || 'Sponsored'}
      </p>
      {filled.source === 'MYHIGH5' && filled.creative ? (
        <a
          // Clicks go through MyHigh5 (counted, then redirected to the reviewed destination) when offered.
          href={filled.creative.click_url
            ? `${getEffectiveApiUrl().replace(/\/+$/, '')}${filled.creative.click_url}`
            : filled.creative.destination_url}
          target="_blank"
          rel="sponsored noopener noreferrer"
          className="flex gap-3 items-start"
        >
          {filled.creative.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={normalizeMediaUrl(filled.creative.image_url)} alt="" className="h-16 w-16 rounded object-cover flex-shrink-0" />
          ) : null}
          <span>
            <span className="block font-semibold text-gray-900 dark:text-white">{filled.creative.headline}</span>
            {filled.creative.body ? (
              <span className="block text-sm text-gray-600 dark:text-gray-300">{filled.creative.body}</span>
            ) : null}
          </span>
        </a>
      ) : null}
      {filled.source === 'ADSENSE' && filled.adsense ? (
        <ins
          className="adsbygoogle"
          style={{ display: 'block' }}
          data-ad-client={filled.adsense.client}
          data-ad-slot={filled.adsense.slot}
          data-ad-format="auto"
          data-full-width-responsive="true"
        />
      ) : null}
    </aside>
  )
}
