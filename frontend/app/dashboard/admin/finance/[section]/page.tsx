'use client'

import { notFound, useParams } from 'next/navigation'

import AdminFinance from '@/components/admin/admin-finance'
import { FINANCE_SECTIONS, isFinanceSection } from '@/lib/finance-admin'

export default function FinanceSectionPage() {
  const params = useParams<{ section: string }>()
  const section = params?.section
  if (!isFinanceSection(section)) notFound()
  const title = FINANCE_SECTIONS.find((s) => s.slug === section)?.label

  return (
    <div>
      <div className="mb-8">
        <p className="text-sm font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Finance &amp; Payments</p>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{title}</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Payment provider, cashout settings, payout security and cashout monitoring. Secrets are never shown, and no
          setting on these pages sends a payment by itself.
        </p>
      </div>
      <AdminFinance section={section} />
    </div>
  )
}
