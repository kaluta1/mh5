'use client'

import AdminMarketplace from '@/components/admin/admin-marketplace'

export default function MarketplaceAdminPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Marketplace</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Listing moderation, orders, buyer support requests and the read-only marketplace reconciliation. Seller
          decisions stay under Seller verification.
        </p>
      </div>
      <AdminMarketplace />
    </div>
  )
}
