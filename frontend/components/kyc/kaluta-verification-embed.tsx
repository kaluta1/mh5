'use client'

import Script from 'next/script'
import { useEffect, useRef, useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'
import { KALUTA_EMBED_SCRIPT, isKalutaVerificationUrl } from '@/lib/kaluta-verification'

declare global {
  interface Window {
    KalutaKYC?: {
      open: (opts: {
        url: string
        onReady?: () => void
        onStep?: (step: string) => void
        onComplete?: (result: { status?: string; score?: number }) => void
        onClose?: (result?: { status?: string; score?: number }) => void
      }) => void
      redirect: (url: string) => void
    }
  }
}

type Props = {
  verificationUrl: string
  /** The widget finished or was closed. Called ONCE; the result is then read from the backend. */
  onFinished?: () => void
  /** How long to wait for the provider's script before offering the hosted page instead. */
  scriptTimeoutMs?: number
}

export function KalutaVerificationEmbed({ verificationUrl, onFinished, scriptTimeoutMs = 10000 }: Props) {
  const openedRef = useRef(false)
  const finishedRef = useRef(false)
  const onFinishedRef = useRef(onFinished)
  onFinishedRef.current = onFinished
  const [scriptUnavailable, setScriptUnavailable] = useState(false)
  const allowed = isKalutaVerificationUrl(verificationUrl)

  useEffect(() => {
    if (!allowed || openedRef.current) return

    const finish = () => {
      // The widget reports both "complete" and "close": one refresh, not two.
      if (finishedRef.current) return
      finishedRef.current = true
      onFinishedRef.current?.()
    }

    const openWidget = () => {
      if (!window.KalutaKYC || openedRef.current) return false
      openedRef.current = true
      window.KalutaKYC.open({
        url: verificationUrl,
        onComplete: finish,
        onClose: finish,
      })
      return true
    }

    if (openWidget()) return

    const interval = setInterval(() => {
      if (openWidget()) clearInterval(interval)
    }, 150)
    const giveUp = setTimeout(() => {
      if (!openedRef.current) {
        clearInterval(interval)
        setScriptUnavailable(true)
      }
    }, scriptTimeoutMs)

    return () => {
      clearInterval(interval)
      clearTimeout(giveUp)
    }
  }, [verificationUrl, allowed, scriptTimeoutMs])

  if (!allowed) {
    return (
      <div className="py-16 px-6 text-center" role="alert">
        <p className="text-sm text-red-600 dark:text-red-400">
          This verification link cannot be opened. Please request a new one.
        </p>
      </div>
    )
  }

  return (
    <>
      <Script src={KALUTA_EMBED_SCRIPT} strategy="afterInteractive" onError={() => setScriptUnavailable(true)} />
      <div className="flex flex-col items-center justify-center py-16 gap-4 px-6 text-center">
        {scriptUnavailable ? (
          <>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              The verification window could not be opened here. You can continue on the secure verification page.
            </p>
            <a
              href={verificationUrl}
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-myhigh5-primary px-4 py-2 text-sm font-medium text-white"
            >
              <ExternalLink className="h-4 w-4" />
              Continue on the secure page
            </a>
          </>
        ) : (
          <>
            <Loader2 className="h-10 w-10 animate-spin text-myhigh5-primary" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Opening secure identity verification…</p>
          </>
        )}
      </div>
    </>
  )
}
