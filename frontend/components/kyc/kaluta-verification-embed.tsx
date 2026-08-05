'use client'

import Script from 'next/script'
import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'

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
  onComplete?: (result: { status?: string; score?: number }) => void
  onClose?: () => void
}

export function KalutaVerificationEmbed({ verificationUrl, onComplete, onClose }: Props) {
  const openedRef = useRef(false)
  const scriptReadyRef = useRef(false)

  useEffect(() => {
    if (!verificationUrl || openedRef.current) return

    const openWidget = () => {
      if (!window.KalutaKYC || openedRef.current) return false
      openedRef.current = true
      window.KalutaKYC.open({
        url: verificationUrl,
        onComplete: (result) => onComplete?.(result),
        onClose: () => onClose?.(),
      })
      return true
    }

    if (scriptReadyRef.current && openWidget()) return

    const interval = setInterval(() => {
      if (window.KalutaKYC) {
        scriptReadyRef.current = true
        if (openWidget()) clearInterval(interval)
      }
    }, 150)

    return () => clearInterval(interval)
  }, [verificationUrl, onComplete, onClose])

  return (
    <>
      <Script
        src="https://kalutakyc.com/embed.js"
        strategy="afterInteractive"
        onLoad={() => {
          scriptReadyRef.current = true
        }}
      />
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <Loader2 className="h-10 w-10 animate-spin text-myhigh5-primary" />
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Opening secure identity verification…
        </p>
      </div>
    </>
  )
}
