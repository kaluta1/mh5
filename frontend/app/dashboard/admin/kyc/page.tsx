'use client'

import AdminKYC from '@/components/admin/admin-kyc'

export default function KYCPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Gestion KYC</h1>
        <p className="text-gray-600 mt-2">Approuvez ou rejetez les vérifications d'identité</p>
      </div>
      <AdminKYC />
    </div>
  )
}
