'use client'

import AdminAdvertising from '@/components/admin/admin-advertising'

export default function AdminAdvertisingPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Advertising</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Prices, campaign review, impressions, contest-entry revenue sharing, AdSense reconciliation and Annual Ads records.
          Ordinary MyHigh5 ads, Google AdSense and Annual Ads are accounted separately.
        </p>
      </div>
      <AdminAdvertising />
    </div>
  )
}
