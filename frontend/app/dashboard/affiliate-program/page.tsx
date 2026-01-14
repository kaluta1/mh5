'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { Network, DollarSign, Users, Link2, TrendingUp, Award, CheckCircle2, Share2, Target, ShoppingBag, Megaphone, BookOpen } from 'lucide-react'
import Link from 'next/link'

export default function AffiliateProgramPage() {
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
            <div className="w-10 h-10 rounded-xl bg-myhigh5-primary flex items-center justify-center shadow-lg shadow-myhigh5-primary/25">
              <Network className="w-5 h-5 text-white" />
            </div>
            MyHigh5 Affiliate Program
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            Build your network and earn commissions through our 10-level affiliate program
          </p>
        </div>
        <Link href="/dashboard/affiliates">
          <button className="px-4 py-2 bg-myhigh5-primary text-white rounded-xl hover:bg-myhigh5-primary/90 shadow-lg shadow-myhigh5-primary/25 transition-colors">
            View My Affiliates
          </button>
        </Link>
      </div>

      {/* Main Content */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="p-6 sm:p-8 space-y-8">
          
          {/* Overview Section */}
          <section>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                <Target className="w-6 h-6 text-myhigh5-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                How It Works
              </h2>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              The MyHigh5 Affiliate Program allows you to earn commissions by referring new members to the platform. 
              Every person you refer becomes part of your network, and you earn commissions on their activities up to 10 levels deep.
            </p>

            <div className="grid md:grid-cols-3 gap-4">
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="w-10 h-10 rounded-lg bg-myhigh5-primary flex items-center justify-center mb-4">
                  <Link2 className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Get Your Link
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Every member gets a unique referral link that tracks all sign-ups and activities
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="w-10 h-10 rounded-lg bg-myhigh5-primary flex items-center justify-center mb-4">
                  <Share2 className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Share & Refer
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Share your link with friends, family, and your network to start building your affiliate network
                </p>
              </div>

              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="w-10 h-10 rounded-lg bg-myhigh5-primary flex items-center justify-center mb-4">
                  <DollarSign className="w-5 h-5 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Earn Commissions
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Earn commissions on purchases, memberships, and activities from your entire network
                </p>
              </div>
            </div>
          </section>

          {/* Commission Structure Section */}
          <section className="pt-8 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                <Award className="w-6 h-6 text-myhigh5-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Commission Structure
              </h2>
            </div>
           
          </section>

          {/* What You Can Earn On Section */}
          <section className="pt-8 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-myhigh5-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                What You Can Earn Commissions On
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              {/* KYC Payments */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <Users className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    KYC Payments
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn commissions when members in your network complete their KYC verification
                </p>
                <p className="text-lg font-bold text-myhigh5-primary">
                  10% on Level 1, 1% on Levels 2-10
                </p>
              </div>

              {/* Founding Membership */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <BookOpen className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Founding Membership
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn commissions when members in your network pay for Founding Member's joining fees
                </p>
                <p className="text-lg font-bold text-myhigh5-primary">
                  10% on Level 1, 1% on Levels 2-10
                </p>
              </div>

              {/* Annual Membership Fee */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <Award className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Annual Membership Fee
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn commissions when Founding Members in your referral network pay their annual membership fee.
                </p>
                <p className="text-lg font-bold text-myhigh5-primary">
                  10% on Level 1, 1% on Levels 2-10
                </p>
              </div>

              {/* Club Memberships */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <Users className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Club Memberships
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn referral commissions from the 20% margin added to club membership fees.
                </p>
                <p className="text-lg font-bold text-myhigh5-primary">
                  10% on Level 1, 1% on Levels 2-10
                </p>
              </div>

              {/* Shop Purchases */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <ShoppingBag className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Shop Purchases
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn referral commissions from the 20% margin added to the digital content price.
                </p>
                <p className="text-lg font-bold text-myhigh5-primary">
                  10% on Level 1, 1% on Levels 2-10
                </p>
              </div>

              {/* Ad Revenue Sharing */}
              <div className="bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                    <Megaphone className="w-5 h-5 text-myhigh5-primary" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Ad Revenue Sharing
                  </h3>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  Earn commissions from ad revenues generated on contest pages of members in your network
                </p>
                <div className="text-lg font-bold text-myhigh5-primary space-y-1">
                  <p>Participants: 40% for self, 5% for Level 1, 1% for each of Levels 2 to 10.</p>
                  <p>Nominators: 10% for self, 2.5% for Level 1, 1% for each of Levels 2 to 10.</p>
                </div>
              </div>
             
            </div>
          </section>

          {/* Key Features Section */}
          <section className="pt-8 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-myhigh5-primary/10 dark:bg-myhigh5-primary/20 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Key Features
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    Personalized Affiliate Links
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Every member gets a unique referral link that's automatically embedded on every page they visit
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    30-Day Cookie Tracking
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Referral links are tracked using 30-day cookies, ensuring you get credit for all sign-ups
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    Real-Time Tracking
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Monitor your network growth, commissions, and earnings in real-time through your dashboard
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    Automatic Commission Distribution
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Commissions are automatically calculated and added to your wallet balance
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    Random Referral Assignment
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Members who join without a referral link are randomly assigned to Founding Members
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                <CheckCircle2 className="w-6 h-6 text-myhigh5-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-1">
                    Network Visibility
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    View your entire network structure, including direct and indirect referrals across all 10 levels
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Getting Started Section */}
          <section className="pt-8 border-t border-gray-200 dark:border-gray-700">
            <div className="bg-gradient-to-r from-myhigh5-primary/10 to-myhigh5-secondary/10 dark:from-myhigh5-primary/20 dark:to-myhigh5-secondary/20 rounded-xl p-6 border border-myhigh5-primary/20">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
                Ready to Start Earning?
              </h2>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Start building your affiliate network today and earn commissions on every referral. 
                Visit your Affiliates dashboard to get your referral links and start sharing.
              </p>
              <Link href="/dashboard/affiliates">
                <button className="px-6 py-3 bg-myhigh5-primary text-white rounded-xl hover:bg-myhigh5-primary/90 shadow-lg shadow-myhigh5-primary/25 transition-colors font-semibold">
                  Go to My Affiliates Dashboard
                </button>
              </Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

