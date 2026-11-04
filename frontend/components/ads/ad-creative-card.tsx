'use client'

import { normalizeMediaUrl } from '@/lib/media-url'

type Json = Record<string, any>

export type Placement = 'IN_FEED' | 'SIDEBAR' | 'IN_CONTENT'

export const CTA_LABELS: Record<string, string> = {
  LEARN_MORE: 'Learn more', SHOP_NOW: 'Shop now', SIGN_UP: 'Sign up', CONTACT_US: 'Contact us',
  BOOK_NOW: 'Book now', DOWNLOAD: 'Download', WATCH_MORE: 'Watch more', APPLY_NOW: 'Apply now',
}

export function domainOf(url?: string | null): string {
  if (!url) return ''
  try {
    const host = new URL(url).hostname.toLowerCase()
    return host.startsWith('www.') ? host.slice(4) : host
  } catch {
    return ''
  }
}

/** Media frame per rendered slot: in-feed keeps a square or 4:5 image, the 288 px desktop sidebar uses 6:5,
 * the contest-entry panel is square. */
function frameClass(placement: Placement, creative: Json): string {
  if (placement === 'SIDEBAR') return 'aspect-[6/5]'
  if (placement === 'IN_CONTENT') return 'aspect-square'
  const w = Number(creative.image_width || creative.image?.width || 0)
  const h = Number(creative.image_height || creative.image?.height || 0)
  return w && h && h > w ? 'aspect-[4/5]' : 'aspect-square'
}

/** The one markup for a MyHigh5 ad: the live slot and every preview render it, so a preview shows exactly
 * what members will see. It never requests or records anything (previews create no billable event). */
export function AdCreativeCard({ creative, placement = 'IN_FEED', href, preview = false }: {
  creative: Json
  placement?: Placement
  href?: string
  preview?: boolean
}) {
  const image = creative.image_url ? normalizeMediaUrl(creative.image_url) : ''
  const video = creative.video?.url ? normalizeMediaUrl(creative.video.url) : ''
  const poster = creative.video?.poster_url ? normalizeMediaUrl(creative.video.poster_url) : undefined
  const cta = CTA_LABELS[creative.cta_code || ''] || ''
  const domain = creative.destination_domain || domainOf(creative.destination_url)
  const body = (
    <>
      {creative.display_name ? (
        <span className="block text-xs font-medium text-gray-700 dark:text-gray-200" data-testid="ad-display-name">
          {creative.display_name}
        </span>
      ) : null}
      {preview && video ? (
        <video src={video} poster={poster} muted playsInline controls
          className={`mt-2 w-full rounded object-cover ${placement === 'IN_FEED' ? 'aspect-[9/16] max-h-96' : frameClass(placement, creative)}`} />
      ) : image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} alt="" className={`mt-2 w-full rounded object-cover ${frameClass(placement, creative)}`} />
      ) : null}
      <span className="mt-2 block font-semibold text-gray-900 dark:text-white" data-testid="ad-headline">
        {creative.headline || (preview ? 'Headline' : '')}
      </span>
      {creative.body ? <span className="block text-sm text-gray-600 dark:text-gray-300">{creative.body}</span> : null}
      <span className="mt-2 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-gray-500" data-testid="ad-domain">{domain}</span>
        {cta ? (
          <span className="flex-shrink-0 rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white" data-testid="ad-cta">
            {cta}
          </span>
        ) : null}
      </span>
    </>
  )
  return (
    <div data-testid="ad-creative-card" data-placement={placement}
      className={placement === 'SIDEBAR' ? 'w-72 max-w-full' : 'w-full'}>
      {href && !preview ? (
        <a href={href} target="_blank" rel="sponsored noopener noreferrer" className="block">{body}</a>
      ) : (
        <div className="block">{body}</div>
      )}
    </div>
  )
}

/** Placement-specific previews (in-feed, desktop sidebar, contest-entry panel). Rendering only. */
export function AdPlacementPreviews({ creative, placements }: { creative: Json; placements?: string[] }) {
  const list = (placements && placements.length ? placements : ['IN_FEED', 'SIDEBAR', 'IN_CONTENT']) as Placement[]
  const titles: Record<Placement, string> = {
    IN_FEED: 'In-feed', SIDEBAR: 'Desktop sidebar (288 px)', IN_CONTENT: 'Contest-entry panel',
  }
  const widths: Record<Placement, string> = { IN_FEED: 'max-w-md', SIDEBAR: 'w-72', IN_CONTENT: 'max-w-[400px]' }
  return (
    <div data-testid="ad-placement-previews" className="flex flex-wrap gap-4">
      {list.map((p) => (
        <figure key={p} className={`${widths[p]} w-full space-y-1`}>
          <figcaption className="text-[11px] text-gray-500">{titles[p]}</figcaption>
          <div data-testid="ad-preview" className="rounded-lg border border-gray-200 bg-white/70 p-3 dark:border-gray-700 dark:bg-gray-900/40">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500">Sponsored</p>
            <AdCreativeCard creative={creative} placement={p} preview />
          </div>
        </figure>
      ))}
    </div>
  )
}
