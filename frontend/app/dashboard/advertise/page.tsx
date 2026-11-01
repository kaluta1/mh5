'use client'

import { AdvertiserDashboard } from '@/components/dashboard/advertiser-dashboard'

export default function AdvertisePage() {
  return (
    <div className="mx-auto max-w-5xl p-4">
      <h1 className="mb-1 text-2xl font-bold text-gray-900 dark:text-white">Advertise on MyHigh5</h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
        Campaigns, budgets, credit and delivery. All amounts in USD.
      </p>
      <AdvertiserDashboard />
    </div>
  )
}
