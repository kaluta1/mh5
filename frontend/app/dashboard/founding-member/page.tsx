'use client'

import { RetiredProgramNotice } from '@/components/dashboard/retired-program-notice'

export default function FoundingMemberPage() {
  return (
    <div className="space-y-6 pb-10">
      <RetiredProgramNotice
        titleKey="legacy_retired.founding_title"
        bodyKey="legacy_retired.founding_body"
        links={[
          { href: '/dashboard/referral-pool', labelKey: 'legacy_retired.link_referral_pool' },
          { href: '/dashboard/founding-member/fmr', labelKey: 'legacy_retired.link_fmp_history' },
          { href: '/dashboard/wallet', labelKey: 'legacy_retired.link_wallet' },
        ]}
      />
    </div>
  )
}
