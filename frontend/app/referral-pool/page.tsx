"use client"

import Link from "next/link"
import { Users } from "lucide-react"
import { Header } from "@/components/layout/header"
import { Footer } from "@/components/sections/footer"
import { useLanguage } from "@/contexts/language-context"
import { referralPoolLaunchText, useReferralPoolStatus } from "@/lib/referral-pool-status"
import { ReferralPoolFaq, ReferralPoolRules } from "@/components/sections/referral-pool-explainer"

/** Public explanation of the Multi-Unit Referral Pool, with its launch status. Until the server
 * says otherwise (or when it cannot be reached), purchases and allocation are shown as unavailable. */
export default function ReferralPoolPublicPage() {
  const { t } = useLanguage()
  const status = useReferralPoolStatus()

  return (
    <div className="min-h-screen bg-gradient-to-br from-myhigh5-blue-50 via-white to-myhigh5-cyan-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      <Header />
      <main className="pt-24 pb-16">
        <div className="container px-4 md:px-6 max-w-3xl mx-auto space-y-6">
          <div className="text-center space-y-2">
            <Users className="w-10 h-10 mx-auto text-myhigh5-primary" aria-hidden="true" />
            <h1 className="text-3xl md:text-4xl font-black text-gray-900 dark:text-white">{t("referral_pool.page_title")}</h1>
            <p className="text-gray-600 dark:text-gray-300">{t("referral_pool.public_subtitle")}</p>
          </div>

          <div role="status" data-testid="pool-public-status" className="rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-4 text-sm space-y-1">
            <p className="font-semibold text-gray-900 dark:text-white">{t("referral_pool.status_title")}</p>
            <p>{referralPoolLaunchText(t, status)}</p>
            <p className="text-gray-600 dark:text-gray-300">{t("referral_pool.not_guaranteed")}</p>
          </div>

          <p className="text-gray-700 dark:text-gray-200">{t("referral_pool.intro")}</p>
          <ReferralPoolRules />
          <ReferralPoolFaq />
          <p className="text-center text-sm">
            <Link href="/dashboard/referral-pool" className="text-myhigh5-primary underline">
              {t("referral_pool.cta_dashboard")}
            </Link>
          </p>
        </div>
      </main>
      <Footer />
    </div>
  )
}
