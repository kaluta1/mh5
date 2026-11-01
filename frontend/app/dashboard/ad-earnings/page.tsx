'use client'

import { AdEarnings } from '@/components/dashboard/advertiser-dashboard'

export default function AdEarningsPage() {
  return (
    <div className="mx-auto max-w-5xl p-4">
      <h1 className="mb-1 text-2xl font-bold text-gray-900 dark:text-white">Contest page ad earnings</h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
        Your share of the advertising revenue earned on your contest-entry pages, and your 1% as a direct sponsor.
      </p>
      <AdEarnings />
    </div>
  )
}
