'use client'

import { useCallback, useEffect } from 'react'
import { useToast } from '@/components/ui/toast'
import { getReferralShareManager, shortenReferralUrl } from '@/lib/referral-share'

export function useReferralShare() {
  const { addToast } = useToast()

  useEffect(() => {
    const manager = getReferralShareManager({
      toast: (message) => addToast(message, 'success', 3000),
    })
    manager.bindShareButtons()
    manager.bindAutomaticCopy()
  }, [addToast])

  const shorten = useCallback(async (url: string) => {
    try {
      return await shortenReferralUrl(url)
    } catch {
      return url
    }
  }, [])

  return { shorten }
}
