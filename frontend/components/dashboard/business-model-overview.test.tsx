import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import en from '@/lib/translations/en.json'

const lookup = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string

vi.mock('@/contexts/language-context', () => ({ useLanguage: () => ({ t: lookup }) }))
vi.mock('@/lib/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      status: 200,
      data: {
        business_model_version: 'NEW_V2',
        direct_commission_rate: 0.2,
        referral_pool: { retired: true, is_open: false },
        leaders: { pool_rate: 0.05, max_members: 10000 },
        marketplace: { markup_rate: 0.2, enabled: false },
      },
    }),
  },
}))

import { BusinessModelOverview } from './business-model-overview'

describe('BusinessModelOverview', () => {
  it('describes the direct-only 20% model and Leaders, never multi-level earnings', async () => {
    const { container } = render(<BusinessModelOverview />)
    expect(screen.getByText('Direct affiliate commission: 20%')).toBeInTheDocument()
    expect(screen.getByText('MyHigh5 Leaders: 5% monthly')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(en.business_model.marketplace_pending)).toBeInTheDocument())
    const text = container.textContent ?? ''
    expect(text).toMatch(/there are no level 2 to 10 commissions/i)
    expect(text).not.toMatch(/Levels 2-10|10 levels deep|Founding Members pool/i)
  })

  it('presents the Referral Pool only as retired history, with no join offer, price or seats', async () => {
    const { container } = render(<BusinessModelOverview />)
    expect(screen.getByText('MyHigh5 Referral Pool (retired)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: en.business_model.pool_history_link })).toHaveAttribute('href', '/dashboard/referral-pool')
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/\$100 Referral Pool entry|Join the Referral Pool|limited to 10,000|Seats taken/i)
    expect(text).not.toMatch(/assigned fairly and at random/i)
  })
})
