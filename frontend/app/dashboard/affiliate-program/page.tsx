'use client'

import { RetiredProgramNotice } from '@/components/dashboard/retired-program-notice'

export default function AffiliateProgramPage() {
  return (
    <div className="space-y-6 pb-10">
      <RetiredProgramNotice
        titleKey="legacy_retired.affiliate_title"
        bodyKey="legacy_retired.affiliate_body"
        links={[
          { href: '/dashboard/commissions', labelKey: 'legacy_retired.link_commissions' },
          { href: '/dashboard/wallet', labelKey: 'legacy_retired.link_wallet' },
        ]}
      />
    </div>
  )
}
