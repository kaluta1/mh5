'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import api from '@/lib/api'
import { Megaphone, AlertCircle, Loader2 } from 'lucide-react'
import { ANNUALADS_EMBED_URL, ANNUALADS_SSO_TARGET_ORIGIN, API_URL } from '@/lib/config'

const embedUrl = ANNUALADS_EMBED_URL
const ssoTargetOrigin = ANNUALADS_SSO_TARGET_ORIGIN

type SsoPayload = {
  token: string
  tenant_api_key: string
  tenant_id: string
}

export default function SponsoredPage() {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const ssoPayloadRef = useRef<SsoPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSsoToken, setHasSsoToken] = useState(false)
  const [ssoError, setSsoError] = useState<string | null>(null)
  const [embedMissing, setEmbedMissing] = useState(!embedUrl)

  const postSsoToIframe = useCallback(() => {
    const w = iframeRef.current?.contentWindow
    const data = ssoPayloadRef.current
    if (!w || !data?.token) return
    w.postMessage(
      {
        type: 'SSO_LOGIN',
        token: data.token,
        tenant_api_key: data.tenant_api_key,
      },
      ssoTargetOrigin
    )
  }, [])

  const fetchSso = useCallback(async () => {
    if (!embedUrl) return
    setLoading(true)
    setSsoError(null)
    try {
      const res = await api.get<SsoPayload>('/api/v1/sponsor-embed/sso-token')
      if (res.status >= 400 || !res.data?.token) {
        ssoPayloadRef.current = null
        setHasSsoToken(false)
        const detail = (res.data as { detail?: string })?.detail
        setSsoError(detail || 'SSO token not available')
        return
      }
      ssoPayloadRef.current = res.data
      setHasSsoToken(true)
      postSsoToIframe()
    } catch (e: unknown) {
      ssoPayloadRef.current = null
      setHasSsoToken(false)
      const resp = e && typeof e === 'object' && 'response' in e ? (e as { response?: { data?: { detail?: string }; status?: number } }).response : undefined
      setSsoError(
        resp?.data?.detail ||
          (resp?.status === 503
            ? 'SSO is not configured on the API (ANNUALADS_SSO_SECRET / ANNUALADS_TENANT_ID).'
            : 'Could not load SSO token.')
      )
    } finally {
      setLoading(false)
    }
  }, [postSsoToIframe])

  useEffect(() => {
    setEmbedMissing(!embedUrl)
    if (!embedUrl) return
    void fetchSso()
  }, [embedUrl, fetchSso])

  const onIframeLoad = useCallback(() => {
    postSsoToIframe()
  }, [postSsoToIframe])

  const webhookDisplay = `${API_URL.replace(/\/$/, '')}/api/v1/webhooks/sponsor-payment`

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Megaphone className="w-5 h-5 text-white" />
            </div>
            Sponsored
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2 max-w-2xl">
            Sponsor opportunities (Annual Ads embed). SSO signs in the current MyHigh5 member when the API is
            configured.
          </p>
        </div>
        {embedUrl && (
          <button
            type="button"
            onClick={() => void fetchSso()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Refresh SSO
          </button>
        )}
      </div>

      {embedMissing && (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 p-4 text-amber-900 dark:text-amber-100"
          role="status"
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">Set the embed URL for this environment</p>
            <p className="mt-1 text-amber-800/90 dark:text-amber-200/90">
              Add <code className="rounded bg-amber-100/80 dark:bg-amber-900/50 px-1">NEXT_PUBLIC_ANNUALADS_EMBED_URL</code> with
              the full Annual Ads iframe <code>src</code> (host, path, <code>key</code> query). For{' '}
              <strong>local dev</strong>, use <code className="rounded px-1">.env.local</code>. For{' '}
              <strong>myhigh5.com (production)</strong>, set the same variable in your host (Vercel / server) and run a{' '}
              <strong>new build</strong> — laptop-only <code className="rounded px-1">.env</code> files are not used there.
            </p>
          </div>
        </div>
      )}

      {ssoError && (
        <div
          className="flex items-start gap-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-900/50 p-3 text-sm text-gray-600 dark:text-gray-400"
          role="status"
        >
          <span className="font-medium text-gray-700 dark:text-gray-300">SSO:</span>
          {ssoError}
        </div>
      )}

      {embedUrl && loading && !hasSsoToken && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading SSO…
        </div>
      )}

      {embedUrl && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden shadow-sm">
          <iframe
            ref={iframeRef}
            title="Sponsors"
            src={embedUrl}
            onLoad={onIframeLoad}
            className="w-full min-h-[800px] border-0 block"
            allow="payment *; fullscreen *"
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      )}

      <div className="text-xs text-gray-500 dark:text-gray-500 space-y-2 border-t border-gray-100 dark:border-gray-800 pt-6">
        <p>
          <span className="font-medium text-gray-600 dark:text-gray-400">Webhook URL for Annual Ads tenant</span>
        </p>
        <code className="block rounded bg-gray-100 dark:bg-gray-900 px-2 py-1.5 text-[11px] sm:text-xs break-all text-gray-800 dark:text-gray-200">
          {webhookDisplay}
        </code>
        <p>
          Set the matching secret in backend <code className="rounded px-0.5 bg-gray-100 dark:bg-gray-900">ANNUALADS_WEBHOOK_SECRET</code>
          . SSO secret: <code className="rounded px-0.5 bg-gray-100 dark:bg-gray-900">ANNUALADS_SSO_SECRET</code>, tenant id:{' '}
          <code className="rounded px-0.5 bg-gray-100 dark:bg-gray-900">ANNUALADS_TENANT_ID</code>, API key:{' '}
          <code className="rounded px-0.5 bg-gray-100 dark:bg-gray-900">ANNUALADS_TENANT_API_KEY</code>.
        </p>
        <p>Keep all secrets only in server environment variables, not in the repo or frontend.</p>
      </div>
    </div>
  )
}
