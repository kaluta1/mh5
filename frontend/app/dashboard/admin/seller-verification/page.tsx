'use client'

import AdminSellerVerification from '@/components/admin/admin-seller-verification'

export default function SellerVerificationPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Seller Verification</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Marketplace seller applications, verification results, jurisdiction rules and private seller reviews. Separate from member KYC.
        </p>
      </div>
      <AdminSellerVerification />
    </div>
  )
}
