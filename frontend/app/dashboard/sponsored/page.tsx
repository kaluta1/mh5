'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import api from '@/lib/api'
import { useAuth } from '@/hooks/use-auth'
import { Megaphone, AlertCircle, Loader2, User, RefreshCw } from 'lucide-react'
import { ANNUALADS_EMBED_URL, ANNUALADS_SSO_TARGET_ORIGIN } from '@/lib/config'

const embedUrl = ANNUALADS_EMBED_URL
const ssoTargetOrigin = ANNUALADS_SSO_TARGET_ORIGIN

type SsoPayload = {
  token: string
  tenant_api_key: string
  tenant_id: string
}

function messageForSsoFailure(status: number | undefined): string {
  if (status === 503) {
    return 'Sponsor sign-in is not set up on the server yet. Your administrator can finish configuration, then you can use Retry.'
  }
  if (status === 401) {
    return 'Your session expired. Sign in again, then return to this page.'
  }
  return 'Could not link your account to sponsors right now. Use Retry in a moment.'
}

export default function SponsoredPage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const ssoPayloadRef = useRef<SsoPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSsoToken, setHasSsoToken] = useState(false)
  const [ssoErrorText, setSsoErrorText] = useState<string | null>(null)
  const [embedMissing, setEmbedMissing] = useState(!embedUrl)

  const displayName =
    user?.full_name?.trim() ||
    [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim() ||
    user?.username ||
    ''

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
  }, [ssoTargetOrigin])

  const fetchSso = useCallback(async () => {
    if (!embedUrl || !isAuthenticated) return
    setLoading(true)
    setSsoErrorText(null)
    try {
      const res = await api.get<SsoPayload>('/api/v1/sponsor-embed/sso-token')
      if (res.status >= 400 || !res.data?.token) {
        ssoPayloadRef.current = null
        setHasSsoToken(false)
        setSsoErrorText(messageForSsoFailure(res.status))
        return
      }
      ssoPayloadRef.current = res.data
      setHasSsoToken(true)
      setSsoErrorText(null)
      postSsoToIframe()
    } catch (e: unknown) {
      ssoPayloadRef.current = null
      setHasSsoToken(false)
      const resp = e && typeof e === 'object' && 'response' in e ? (e as { response?: { status?: number } }).response : undefined
      setSsoErrorText(messageForSsoFailure(resp?.status))
    } finally {
      setLoading(false)
    }
  }, [isAuthenticated, postSsoToIframe])

  useEffect(() => {
    setEmbedMissing(!embedUrl)
    if (!embedUrl || !isAuthenticated) return
    void fetchSso()
  }, [embedUrl, isAuthenticated, fetchSso])

  const onIframeLoad = useCallback(() => {
    postSsoToIframe()
  }, [postSsoToIframe])

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Megaphone className="w-5 h-5 text-white" />
            </div>
            Sponsored
          </h1>

          {authLoading ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">Loading account…</p>
          ) : isAuthenticated && displayName ? (
            <p className="text-sm sm:text-base text-gray-600 dark:text-gray-300 flex items-center gap-2">
              <User className="w-4 h-4 text-myhigh5-primary flex-shrink-0" />
              <span>
                <span className="text-gray-500 dark:text-gray-400">Signed in as</span>{' '}
                <span className="font-semibold text-gray-900 dark:text-white">{displayName}</span>
                {user?.username && displayName !== user.username ? (
                  <span className="text-gray-500 dark:text-gray-500"> @{user.username}</span>
                ) : null}
              </span>
            </p>
          ) : isAuthenticated ? (
            <p className="text-sm text-gray-600 dark:text-gray-300 flex items-center gap-2">
              <User className="w-4 h-4 text-myhigh5-primary" />
              <span>
                <span className="text-gray-500">Signed in</span>
                {user?.email ? (
                  <span className="font-medium text-gray-900 dark:text-white"> · {user.email}</span>
                ) : null}
              </span>
            </p>
          ) : (
            <p className="text-sm text-amber-800 dark:text-amber-200/90">
              You are not signed in.{' '}
              <Link href="/" className="font-medium text-myhigh5-primary underline">
                Go to the home page to sign in
              </Link>
            </p>
          )}
        </div>

        {embedUrl && isAuthenticated && (
          <button
            type="button"
            onClick={() => void fetchSso()}
            disabled={loading}
            className="inline-flex items-center gap-2 self-start rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 disabled:opacity-50"
            title="Link your account to the embed again"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Retry
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
            <p className="font-medium">Sponsor page is not fully configured on this host</p>
            <p className="mt-1 text-amber-800/90 dark:text-amber-200/90">
              The embed URL must be set in the app environment, then a new build is required.
            </p>
          </div>
        </div>
      )}

      {isAuthenticated && embedUrl && ssoErrorText && !loading && (
        <p className="text-sm text-amber-800 dark:text-amber-200/90" role="status">
          {ssoErrorText}
        </p>
      )}

      {embedUrl && isAuthenticated && loading && !hasSsoToken && !ssoErrorText && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          Linking your account…
        </div>
      )}

      {embedUrl && isAuthenticated && !ssoErrorText && hasSsoToken && !loading && (
        <p className="text-xs text-gray-500 dark:text-gray-500">Your account is linked for this session.</p>
      )}

      {embedUrl && isAuthenticated && (
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

      {embedUrl && !isAuthenticated && !authLoading && (
        <p className="text-sm text-gray-500">Sign in to view sponsors and link your account.</p>
      )}
    </div>
  )
}
