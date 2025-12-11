'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { BookOpen, DollarSign, Users, Gift, CheckCircle2, AlertCircle } from 'lucide-react'

export default function FoundingMemberPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="h-96 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="space-y-6 pb-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-myfav-primary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            MyHigh5 Founding Membership: Benefits & Eligibility
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            Become a MyHigh5 Founding Member and unlock exclusive financial rewards and opportunities.
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="p-6 sm:p-8 space-y-8">
          
          {/* Exclusive Financial Benefits Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myfav-primary/10 dark:bg-myfav-primary/20 flex items-center justify-center">
                <DollarSign className="w-6 h-6 text-myfav-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Exclusive Financial Benefits
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Founding Members participate in several exclusive commission and profit pools:
            </p>

            <div className="space-y-6">
              {/* Monthly Revenue Commission Pool */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-myfav-primary flex items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold text-lg">1</span>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                      Monthly Revenue Commission Pool (10%)
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300 mb-3">
                      Ten percent (10%) of MyHigh5's monthly net revenue is allocated to the Founding Members Commission Pool. This pool is distributed monthly based on each member's Founding Membership Ratio.
                    </p>
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                      <p className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                        Founding Membership Ratio:
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Calculated as the number of a member's verified direct referrals divided by the total number of verified direct referrals across the entire platform.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Annual Profit Pool */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-myfav-primary flex items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold text-lg">2</span>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                      Annual Profit Pool (20%)
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300 mb-3">
                      Founding Members of MyHigh5 and DSM participate in a combined pool comprising twenty percent (20%) of MyHigh5's annual profit after taxes.
                    </p>
                    <div className="space-y-3">
                      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                        <p className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                          Allocation:
                        </p>
                        <ul className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
                          <li className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-myfav-primary"></span>
                            80% of the pool is allocated to MyHigh5 Founding Members.
                          </li>
                          <li className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-myfav-primary"></span>
                            20% of the pool is allocated to DSM Founding Members.
                          </li>
                        </ul>
                      </div>
                      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                          Distribution to members within each group is based on their respective Founding Membership Ratios.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Affiliation and Referral Commissions */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-myfav-primary flex items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold text-lg">3</span>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                      Affiliation and Referral Commissions
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300 mb-4">
                      Members receive significant commissions through the Affiliate Program for the purchase of premium services, including the Founding Membership fee itself:
                    </p>
                    <div className="bg-white dark:bg-gray-800 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead className="bg-gray-100 dark:bg-gray-700">
                            <tr>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white">Referral Type</th>
                              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white">Action</th>
                              <th className="px-4 py-3 text-center text-sm font-semibold text-gray-900 dark:text-white">Direct Referral (Level 1)</th>
                              <th className="px-4 py-3 text-center text-sm font-semibold text-gray-900 dark:text-white">Indirect Referral (Levels 2–10)</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            <tr>
                              <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">Founding Membership</td>
                              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">Pays $100 Joining Fee</td>
                              <td className="px-4 py-3 text-sm text-center font-semibold text-myfav-primary">$20 Commission</td>
                              <td className="px-4 py-3 text-sm text-center font-semibold text-myfav-primary">$2 Commission</td>
                            </tr>
                            <tr>
                              <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">Annual Fee</td>
                              <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">Pays $50 Annual Fee</td>
                              <td className="px-4 py-3 text-sm text-center font-semibold text-myfav-primary">$10 Commission</td>
                              <td className="px-4 py-3 text-sm text-center font-semibold text-myfav-primary">$1 Commission</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Randomly Assigned Referrals */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-myfav-primary flex items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold text-lg">4</span>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                      Randomly Assigned Referrals
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300">
                      MyHigh5 Founding Members receive randomly assigned referrals from users who join the MyHigh5 platform without using a personal invitation link.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Eligibility and Maintenance Section */}
          <section className="pt-8 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myfav-primary/10 dark:bg-myfav-primary/20 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-myfav-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Eligibility and Maintenance
              </h2>
            </div>

            <div className="space-y-6">
              {/* How to Become a Founding Member */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <Users className="w-5 h-5 text-myfav-primary" />
                  How to Become a Founding Member
                </h3>
                <p className="text-gray-700 dark:text-gray-300 mb-4">
                  The Founding Membership is a limited opportunity:
                </p>
                <ul className="space-y-3">
                  <li className="flex items-start gap-3">
                    <CheckCircle2 className="w-5 h-5 text-myfav-primary flex-shrink-0 mt-0.5" />
                    <span className="text-gray-700 dark:text-gray-300">
                      Pay a one-time joining fee of <span className="font-semibold text-gray-900 dark:text-white">$100</span>.
                    </span>
                  </li>
                  <li className="flex items-start gap-3">
                    <CheckCircle2 className="w-5 h-5 text-myfav-primary flex-shrink-0 mt-0.5" />
                    <span className="text-gray-700 dark:text-gray-300">
                      Verify your MyHigh5 account.
                    </span>
                  </li>
                  <li className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-gray-600 dark:text-gray-400 flex-shrink-0 mt-0.5" />
                    <span className="text-gray-700 dark:text-gray-300">
                      <span className="font-semibold text-gray-900 dark:text-white">Crucially</span>, this opportunity will permanently close once the total number of Founding Members reaches <span className="font-semibold text-gray-900 dark:text-white">10,000</span>.
                    </span>
                  </li>
                </ul>
              </div>

              {/* Maintaining Your Status */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <Gift className="w-5 h-5 text-myfav-primary" />
                  Maintaining Your Status
                </h3>
                <div className="space-y-3">
                  <p className="text-gray-700 dark:text-gray-300">
                    To maintain access to all Founding Member benefits, an annual membership fee of <span className="font-semibold text-gray-900 dark:text-white">$50</span> is required.
                  </p>
                  <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      <span className="font-medium text-gray-900 dark:text-white">Important:</span> Failure to pay the annual fee will result in the temporary loss of Founding Member benefits until the status is restored by paying the required amount.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

