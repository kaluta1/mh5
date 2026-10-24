import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as
    | string
    | undefined) ?? key

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup, language: 'en' }) }))
vi.mock('@/components/layout/header', () => ({ Header: () => null }))
vi.mock('@/components/sections/footer', () => ({ Footer: () => null }))

const get = vi.fn()
vi.mock('@/lib/api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

import { FAQ_TOPICS, RULE_KEYS, ReferralPoolFaq, ReferralPoolRules } from './referral-pool-explainer'
import ReferralPoolPublicPage from '@/app/referral-pool/page'
import { FAQ } from '@/components/sections/faq'
import sitemap from '@/app/sitemap'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { referralPoolLaunchText } from '@/lib/referral-pool-status'

const rp = en.referral_pool as Record<string, string>
const allCopy = (): string[] => [
  ...Object.values(rp),
  en.landing.faq.question_referral_pool,
  en.landing.faq.answer_referral_pool,
  ...Object.entries(en.business_model).filter(([k]) => k.startsWith('units_') || k.startsWith('pool_')).map(([, v]) => String(v)),
]

beforeEach(() => {
  get.mockReset()
})

describe('Referral Pool explanation', () => {
  it('lists the ten approved rules in order', () => {
    render(<ReferralPoolRules />)
    const items = screen.getByTestId('pool-rules').querySelectorAll('li')
    expect(items).toHaveLength(10)
    expect(RULE_KEYS).toHaveLength(10)
    const text = [...items].map((li) => li.textContent)
    expect(text[0]).toBe('Each unit costs $100.')
    expect(text[1]).toMatch(/as many units as you like, unless an administrator sets a limit/)
    expect(text[2]).toMatch(/one allocation slot in each round/)
    expect(text[3]).toMatch(/at random, with every remaining eligible slot equally likely/)
    expect(text[4]).toMatch(/not used up/)
    expect(text[5]).toMatch(/while a round is open start taking part from the next round/)
    expect(text[6]).toMatch(/only after their identity verification \(KYC\) is approved/)
    expect(text[7]).toMatch(/personal invitation always comes first/)
    expect(text[8]).toBe('Referrals are not guaranteed.')
    expect(text[9]).toMatch(/depends on how many eligible new members join/)
  })

  it('answers every required FAQ topic', () => {
    render(<ReferralPoolFaq />)
    expect(FAQ_TOPICS).toHaveLength(12)
    for (const topic of FAQ_TOPICS) {
      fireEvent.click(screen.getByRole('button', { name: rp[`faq_${topic}_q`] }))
      expect(screen.getByText(rp[`faq_${topic}_a`])).toBeInTheDocument()
    }
    expect(rp.faq_price_a).toMatch(/\$100/)
    expect(rp.faq_unlimited_a).toMatch(/no fixed maximum/i)
    expect(rp.faq_kyc_a).toMatch(/only after their own KYC is approved/)
    expect(rp.faq_personal_a).toMatch(/always takes precedence/)
    expect(rp.faq_queue_a).toMatch(/waiting queue/)
    expect(rp.faq_guarantee_a).toMatch(/^No\./)
  })

  it('never promises referrals, earnings or returns and never calls a unit an investment', () => {
    for (const text of allCopy()) {
      for (const sentence of text.split(/(?<=[.!?:])\s+/)) {
        if (sentence.trim().endsWith('?')) continue                         // a question promises nothing
        if (/guarantee/i.test(sentence)) expect(sentence, sentence).toMatch(/\b(not|never|no)\b/i)
        if (/invest/i.test(sentence)) expect(sentence, sentence).toMatch(/\bnot\b/i)
      }
      expect(text).not.toMatch(/passive income|profit|\bROI\b|risk[- ]free|double your|earn up to/i)
    }
  })

  it('no longer describes the retired single-seat pool as the current program', () => {
    const copy = allCopy().join(' ')
    expect(copy).not.toMatch(/10,000 members|one-time \$100|Seats taken|limited to 10,000/i)
    expect(en.business_model.pool_page_title).toBe('Referral Pool')
  })
})

describe('Public Referral Pool page', () => {
  it('explains the system and states it has not launched while both switches are off', async () => {
    get.mockResolvedValue({ status: 200, data: { sales_enabled: false, allocation_enabled: false } })
    render(<ReferralPoolPublicPage />)
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/referral-pool/status'))
    expect(screen.getByTestId('pool-public-status')).toHaveTextContent(rp.launch_pending)
    expect(screen.getByTestId('pool-public-status')).toHaveTextContent(rp.not_guaranteed)
    expect(screen.getByTestId('pool-rules').querySelectorAll('li')).toHaveLength(10)
    expect(screen.getByRole('button', { name: rp.faq_guarantee_q })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: en.business_model.units_buy })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: en.business_model.units_confirm })).not.toBeInTheDocument()
  })

  it('still shows the launch-pending message when the status cannot be loaded', async () => {
    get.mockRejectedValue(new Error('offline'))
    render(<ReferralPoolPublicPage />)
    await waitFor(() => expect(get).toHaveBeenCalled())
    expect(screen.getByTestId('pool-public-status')).toHaveTextContent(rp.launch_pending)
  })
})

describe('Referral Pool launch status in the FAQ, sitemap and footer', () => {
  const answerFor = async (status: unknown) => {
    get.mockResolvedValue({ status: 200, data: status })
    render(<FAQ />)
    fireEvent.click(screen.getByRole('button', { name: en.landing.faq.question_referral_pool }))
    return screen.getByText((text) => text.startsWith(en.landing.faq.answer_referral_pool))
  }

  it('says not launched while both switches are off', async () => {
    const answer = await answerFor({ sales_enabled: false, allocation_enabled: false })
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/referral-pool/status'))
    expect(answer).toHaveTextContent(rp.launch_pending)
  })

  it('follows the real switches once they change', async () => {
    const answer = await answerFor({ sales_enabled: true, allocation_enabled: false })
    await waitFor(() => expect(answer).toHaveTextContent(`${rp.status_sales_on} ${rp.status_allocation_off}`))
    expect(answer).not.toHaveTextContent(rp.launch_pending)
  })

  it('never claims more than "not launched" when the status is unknown', () => {
    expect(referralPoolLaunchText(lookup, null)).toBe(rp.launch_pending)
    expect(referralPoolLaunchText(lookup, { sales_enabled: true, allocation_enabled: true })).toBe(
      `${rp.status_sales_on} ${rp.status_allocation_on}`)
  })

  it('lists the public page in the sitemap and the footer', () => {
    expect(sitemap().some((entry) => entry.url.endsWith('/referral-pool'))).toBe(true)
    const footer = readFileSync(join(process.cwd(), 'components', 'sections', 'footer.tsx'), 'utf8')
    expect(footer).toMatch(/footer\.quick_links\.referral_pool'\), href: "\/referral-pool"/)
    expect(en.footer.quick_links.referral_pool).toBe('Referral Pool')
  })
})
