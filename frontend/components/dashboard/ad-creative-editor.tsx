'use client'

import { useState } from 'react'
import { AdPlacementPreviews, CTA_LABELS, domainOf } from '@/components/ads/ad-creative-card'
import { call, errorDetail, type Json } from './ad-api'

const LIMITS = { headline: 40, body: 125, display_name: 60 }
const FIELDS = ['headline', 'body', 'display_name', 'cta_code', 'destination_url'] as const

function Counter({ value, max }: { value: string; max: number }) {
  const n = value.length
  return <span className={`text-[11px] ${n > max ? 'text-red-600' : 'text-gray-500'}`} data-testid="char-counter">{n}/{max}</span>
}

/** One creative: copy with live counters, call-to-action, approved display name, HTTPS destination (with a test
 * button that only opens it in a new tab), image / video upload with progress, placement previews.
 * A changed approved creative becomes a revision that needs a fresh approval; the approved one keeps serving. */
export function CreativeEditor({ campaignId, creative, placements, onSaved, closed = false }: {
  campaignId: number
  creative?: Json
  placements?: string[]
  onSaved: (message: string) => void
  closed?: boolean
}) {
  const [form, setForm] = useState<Json>(() => Object.fromEntries(FIELDS.map((k) => [k, creative?.[k] || ''])))
  const [error, setError] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const status = creative?.review_status || 'NEW'
  const id = creative?.id
  const editable = !closed && status !== 'ARCHIVED'
  const https = /^https:\/\//i.test(form.destination_url || '')
  const tooLong = (Object.keys(LIMITS) as (keyof typeof LIMITS)[]).some((k) => (form[k] || '').length > LIMITS[k])
  const missing = [
    !form.headline.trim() && 'headline', !form.display_name.trim() && 'advertiser display name',
    !form.cta_code && 'call-to-action', !https && 'HTTPS destination',
  ].filter(Boolean) as string[]
  const changed = FIELDS.some((k) => (form[k] || '') !== (creative?.[k] || ''))

  const payload = () => ({ ...Object.fromEntries(FIELDS.map((k) => [k, form[k] || null])) })
  const save = async (submit: boolean) => {
    setError('')
    try {
      let saved = creative
      if (!id) {
        saved = await call('post', `/advertiser/campaigns/${campaignId}/creatives`, { ...payload(), submit_for_review: submit })
      } else if (changed) {
        saved = await call('patch', `/advertiser/campaigns/${campaignId}/creatives/${id}`, payload())
      }
      if (submit && id && saved?.review_status === 'DRAFT') {
        saved = await call('post', `/advertiser/campaigns/${campaignId}/creatives/${saved.id}/submit`)
      }
      const revision = saved && id && saved.id !== id
      onSaved(revision ? 'Saved as a new version: it needs approval; the approved version keeps running until then.'
        : submit ? 'Creative submitted for review' : 'Draft saved')
    } catch (e) {
      setError(errorDetail(e))
    }
  }

  const upload = async (kind: 'image' | 'video' | 'poster', file: File | undefined) => {
    if (!file || !id) return
    setError('')
    const fd = new FormData()
    fd.append('file', file)
    const path = kind === 'video' ? 'video' : 'image'
    try {
      setProgress(0)
      await call('post', `/advertiser/campaigns/${campaignId}/creatives/${id}/${path}${kind === 'poster' ? '?as=poster' : ''}`, fd, {
        onUploadProgress: (ev: { loaded: number; total?: number }) =>
          setProgress(ev.total ? Math.round((ev.loaded * 100) / ev.total) : null),
      })
      onSaved(status === 'APPROVED' ? 'New media saved as a new version that needs approval' : 'Uploaded')
    } catch (e) {
      setError(errorDetail(e))
    } finally {
      setProgress(null)
    }
  }

  const testDestination = () => {
    if (https) window.open(form.destination_url, '_blank', 'noopener,noreferrer')
  }

  const preview = { ...creative, ...form, body: form.body, destination_domain: domainOf(form.destination_url) }
  const compat: Json | null = creative?.compatibility || null
  return (
    <div data-testid={`creative-editor-${id ?? 'new'}`} className="space-y-2 rounded border border-gray-200 p-3 text-sm dark:border-gray-700">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium">{id ? `Creative #${id}` : 'New creative'}</span>
        {id ? <span data-testid={`creative-status-${id}`} className="rounded-full bg-gray-100 px-2 py-0.5 dark:bg-gray-700">{status}</span> : null}
        {creative?.supersedes_creative_id ? <span className="text-gray-500">new version of #{creative.supersedes_creative_id}</span> : null}
        {creative?.serving ? <span className="text-green-700">serving</span> : null}
      </div>
      {(creative?.review_issues || []).length || (status === 'REJECTED' && creative?.review_note) ? (
        <ul data-testid={`creative-issues-${id}`} className="list-disc pl-5 text-xs text-amber-700 dark:text-amber-400">
          {(creative?.review_issues || []).map((i: Json, n: number) => <li key={n}>{i.category}: {i.note || 'needs changes'}</li>)}
          {creative?.review_note ? <li>{creative.review_note}</li> : null}
        </ul>
      ) : null}
      {editable ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <label>Headline (required) <Counter value={form.headline} max={LIMITS.headline} />
            <input value={form.headline} onChange={(e) => setForm({ ...form, headline: e.target.value })} aria-label="Headline"
              className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label>Advertiser display name <Counter value={form.display_name} max={LIMITS.display_name} />
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              aria-label="Advertiser display name" className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label className="sm:col-span-2">Description <Counter value={form.body} max={LIMITS.body} />
            <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} aria-label="Description" rows={2}
              className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
          </label>
          <label>Call-to-action
            <select value={form.cta_code} onChange={(e) => setForm({ ...form, cta_code: e.target.value })} aria-label="Call-to-action"
              className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900">
              <option value="">Choose…</option>
              {Object.entries(CTA_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>Destination (https://…)
            <input value={form.destination_url} onChange={(e) => setForm({ ...form, destination_url: e.target.value })}
              aria-label="Destination URL" className="mt-1 block w-full rounded border px-2 py-1 dark:bg-gray-900" />
            <span className="mt-1 flex items-center gap-2 text-xs text-gray-500">
              <span data-testid="destination-domain">{https ? `Shown as ${domainOf(form.destination_url)}` : form.destination_url ? 'Must start with https://' : ''}</span>
              <button type="button" className="rounded border px-1" disabled={!https} onClick={testDestination}>Test destination</button>
            </span>
          </label>
        </div>
      ) : null}

      {editable && id ? (
        <div className="grid gap-2 text-xs sm:grid-cols-3">
          <label className="block">Image (JPG, PNG or WebP, up to 5 MB; feed 1200×1200 or 1200×1500, sidebar 600×500)
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-label={`Upload image for creative ${id}`}
              onChange={(e) => upload('image', e.target.files?.[0])} className="mt-1 block" />
          </label>
          <label className="block">Video (MP4 H.264/AAC, 6–30 s, 1080×1920 or 1080×1080; preview only for now)
            <input type="file" accept="video/mp4" aria-label={`Upload video for creative ${id}`}
              onChange={(e) => upload('video', e.target.files?.[0])} className="mt-1 block" />
          </label>
          {creative?.video ? (
            <label className="block">Video thumbnail (image)
              <input type="file" accept="image/jpeg,image/png,image/webp" aria-label={`Upload thumbnail for creative ${id}`}
                onChange={(e) => upload('poster', e.target.files?.[0])} className="mt-1 block" />
            </label>
          ) : null}
          {progress != null ? <progress data-testid="upload-progress" max={100} value={progress} className="w-full sm:col-span-3" /> : null}
        </div>
      ) : null}
      {editable && !id ? <p className="text-xs text-gray-500">Save the draft first, then add an image or video.</p> : null}
      {compat ? (
        <ul data-testid={`creative-compat-${id}`} className="text-xs">
          {Object.entries(compat).map(([p, v]: [string, any]) => (
            <li key={p} className={v.compatible ? 'text-green-700' : 'text-amber-700 dark:text-amber-400'}>{p}: {v.message}</li>
          ))}
        </ul>
      ) : null}

      <AdPlacementPreviews creative={preview} placements={placements} />

      {error ? <p role="alert" className="text-xs text-red-600">{error}</p> : null}
      {editable ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded border px-2 py-1 disabled:opacity-50" disabled={tooLong || (!!id && !changed)}
            onClick={() => save(false)}>{status === 'APPROVED' ? 'Save changes (needs approval)' : 'Save draft'}</button>
          {status !== 'APPROVED' && status !== 'PENDING' ? (
            <button type="button" className="rounded bg-blue-600 px-2 py-1 text-white disabled:opacity-50"
              disabled={tooLong || missing.length > 0} onClick={() => save(true)} title={missing.length ? `Missing: ${missing.join(', ')}` : ''}>
              Submit creative for review</button>
          ) : null}
          {missing.length && status !== 'APPROVED' ? <span className="text-xs text-gray-500">Before review: {missing.join(', ')}</span> : null}
        </div>
      ) : null}
    </div>
  )
}
