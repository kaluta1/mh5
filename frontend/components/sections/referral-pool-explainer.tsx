'use client'

import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

/** The ten approved rules of the Multi-Unit Referral Pool, in order. */
export const RULE_KEYS = Array.from({ length: 10 }, (_, i) => `referral_pool.rule_${i + 1}`)

/** One question per topic the FAQ must cover. */
export const FAQ_TOPICS = [
  'unit', 'price', 'unlimited', 'rounds', 'random', 'kyc',
  'personal', 'refunds', 'suspended', 'queue', 'limits', 'guarantee',
] as const

export function ReferralPoolRules() {
  const { t } = useLanguage()
  return (
    <section className="rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 space-y-3">
      <h2 className="font-semibold text-gray-900 dark:text-white">{t('referral_pool.explainer_title')}</h2>
      <ol className="list-decimal pl-5 space-y-1 text-sm text-gray-700 dark:text-gray-200" data-testid="pool-rules">
        {RULE_KEYS.map((key) => (
          <li key={key}>{t(key)}</li>
        ))}
      </ol>
      <p className="text-sm font-medium text-amber-700 dark:text-amber-400">{t('referral_pool.disclaimer')}</p>
    </section>
  )
}

export function ReferralPoolFaq() {
  const { t } = useLanguage()
  const [open, setOpen] = useState<string | null>(null)
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('referral_pool.faq_title')}</h2>
      {FAQ_TOPICS.map((topic) => {
        const expanded = open === topic
        return (
          <div key={topic} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : topic)}
              className="w-full flex items-center justify-between gap-3 p-4 text-left font-semibold text-gray-900 dark:text-white"
            >
              <span>{t(`referral_pool.faq_${topic}_q`)}</span>
              <ChevronDown className={`w-5 h-5 shrink-0 text-myhigh5-primary transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>
            {expanded && (
              <p className="px-4 pb-4 text-sm text-gray-600 dark:text-gray-300">{t(`referral_pool.faq_${topic}_a`)}</p>
            )}
          </div>
        )
      })}
    </section>
  )
}
