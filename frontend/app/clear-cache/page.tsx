'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import { CheckCircle2, Home, LayoutDashboard, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { clearAppCache } from '@/lib/clear-app-cache'

function ClearCacheContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [cleared, setCleared] = useState<string[]>([])
  const [status, setStatus] = useState<'loading' | 'done' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    void (async () => {
      try {
        const result = await clearAppCache()
        if (cancelled) return
        setCleared(result.cleared.length > 0 ? result.cleared : ['No cached data was stored in this browser'])
        setStatus('done')

        const redirect = searchParams.get('redirect')
        if (redirect && redirect.startsWith('/') && !redirect.startsWith('//')) {
          timer = setTimeout(() => {
            router.replace(redirect)
          }, 1500)
        }
      } catch {
        if (!cancelled) setStatus('error')
      }
    })()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [router, searchParams])

  const redirectTarget = searchParams.get('redirect')
  const showRedirectHint =
    status === 'done' &&
    redirectTarget &&
    redirectTarget.startsWith('/') &&
    !redirectTarget.startsWith('//')

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 via-blue-50/40 to-purple-50/40 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 p-6">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl p-8 text-center">
        {status === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto mb-4 text-myhigh5-primary animate-spin" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Clearing cache…</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Removing stale data from this browser. Your login will stay active.
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Could not clear cache</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Try a hard refresh (Ctrl+Shift+R or Cmd+Shift+R) or clear site data in your browser settings.
            </p>
            <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
              <Button asChild variant="default" className="bg-myhigh5-primary hover:bg-myhigh5-primary/90">
                <Link href="/dashboard">
                  <LayoutDashboard className="w-4 h-4 mr-2" />
                  Go to Dashboard
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/">
                  <Home className="w-4 h-4 mr-2" />
                  Go Home
                </Link>
              </Button>
            </div>
          </>
        )}

        {status === 'done' && (
          <>
            <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-green-600 dark:text-green-400" aria-hidden />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">Cache cleared</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Stale app data was removed. You are still signed in.
            </p>
            <ul className="mt-4 text-left text-sm text-gray-700 dark:text-gray-300 space-y-1.5 bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
              {cleared.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-green-600 dark:text-green-400 shrink-0">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            {showRedirectHint && (
              <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
                Redirecting to {redirectTarget}…
              </p>
            )}
            <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
              <Button asChild variant="default" className="bg-myhigh5-primary hover:bg-myhigh5-primary/90">
                <Link href="/dashboard">
                  <LayoutDashboard className="w-4 h-4 mr-2" />
                  Go to Dashboard
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/">
                  <Home className="w-4 h-4 mr-2" />
                  Go Home
                </Link>
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function ClearCachePage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <Loader2 className="w-10 h-10 animate-spin text-myhigh5-primary" />
        </div>
      }
    >
      <ClearCacheContent />
    </Suspense>
  )
}
