'use client'

import { useEffect } from 'react'
import {
  isChunkLoadError,
  isNextStaticScript,
  recoverFromChunkLoadError,
} from '@/lib/chunk-load-error'

export function ChunkLoadRecovery() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      const target = event.target
      if (target instanceof HTMLScriptElement && target.src && isNextStaticScript(target.src)) {
        recoverFromChunkLoadError()
        return
      }
      if (isChunkLoadError(event.message)) {
        recoverFromChunkLoadError()
      }
    }

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) {
        event.preventDefault()
        recoverFromChunkLoadError()
      }
    }

    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onUnhandledRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onUnhandledRejection)
    }
  }, [])

  return null
}
