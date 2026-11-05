import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { request: requestMock }, apiService: {} }))

import AdminAdvertising from './admin-advertising'

const RESPONSES: Record<string, unknown> = {
  '/overview': {
    settings: { pricing_state: 'CONFIGURED', cpm_rate_usd: '0.5000', min_campaign_budget_usd: '10.00',
      campaigns_enabled: false, funding_enabled: false, adsense_fallback_enabled: true, contest_sharing_enabled: false,
      adsense_sharing_enabled: false },
    approved_policy: { cpm_rate_usd: '0.50', min_campaign_budget_usd: '10.00' },
    packages: [{ code: 'MYHIGH5_CPM_CAMPAIGN', name: 'MyHigh5 CPM campaign', type: 'CPM', price: '0.5000',
      minimum_budget: '10.00', state: 'PRICED_NOT_ACTIVATED', purchasable: false }],
    origins: { active_entries: 883, unscanned: 883, resolved: 0, under_review: 1, resolved_by_kind: {} },
    impression_events: {}, allocations: [], adsense: { credentials_missing: ['ADSENSE_CLIENT_ID'], imports: [], months: [] },
    annual_ads: { enabled: false, payments_by_buyer_match: {}, sponsor_commission: 'PENDING_POLICY' },
  },
  '/campaigns': { campaigns: [{ id: 5, name: 'Spring', status: 'PENDING_REVIEW', advertiser_user_id: 9, budget_total: '10.00',
    spent: '0.00', remaining_budget: '10.00', cpm_rate_usd: '0.5000', funding: 'FUNDED', placements: ['IN_FEED'],
    creatives: [{ id: 3, headline: 'Hello', destination_url: 'https://example.com', review_status: 'PENDING' }] }] },
  '/origins': { origins: [{ contestant_id: 41, title: 'Entry', owner_user_id: 2, entry_type: 'participation',
    contest_name: null, contest_mode: null, evidence: { conflict: 'no contest link' } }] },
  '/reconciliation': { ok: true, checks: [{ check: 'credit_liability', expected: '0.00', actual: '0.00', ok: true, detail: 'x' }] },
  '/suspicious': { invalid_by_reason: {}, reversed_events: 0, recent: [] },
}

describe('AdminAdvertising', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockImplementation(({ method, url }: { method: string; url: string }) => {
      const key = url.replace('/api/v1/admin/advertising', '')
      if (method === 'get') return Promise.resolve({ status: 200, data: RESPONSES[key] })
      return Promise.resolve({ status: 200, data: {} })
    })
  })

  it('shows the policy, the switches off, products, reconciliation and the origin backlog', async () => {
    render(<AdminAdvertising />)
    expect(await screen.findByTestId('adv-pricing')).toHaveTextContent('CPM 0.50 USD per 1,000 valid impressions')
    expect(screen.getByTestId('adv-pricing')).toHaveTextContent('Serve MyHigh5 campaigns: OFF')
    expect(screen.getByTestId('adv-packages')).toHaveTextContent('PRICED_NOT_ACTIVATED')
    expect(screen.getByTestId('adv-reconciliation')).toHaveTextContent('balanced')
    expect(screen.getByTestId('adv-origins')).toHaveTextContent('not yet classified 883')
  })

  it('needs a reason to reject and sends change requests with the note', async () => {
    render(<AdminAdvertising />)
    const reject = await screen.findByText('Reject campaign')
    expect(reject).toBeDisabled()
    expect(screen.getByText('Request changes')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Note for campaign 5'), { target: { value: 'Use a clearer headline' } })
    fireEvent.click(screen.getByText('Request changes'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith({ method: 'post',
      url: '/api/v1/admin/advertising/campaigns/5/request-changes', data: { note: 'Use a clearer headline', issues: [] } }))
    expect(screen.getByText('Reject')).toBeDisabled()                 // creative rejection needs a reason too
  })

  it('flags review issues by category (copy, media, destination, placement)', async () => {
    render(<AdminAdvertising />)
    await screen.findByText('Reject campaign')
    fireEvent.click(screen.getByLabelText('Destination issue for campaign 5'))
    expect(screen.getByText('Request changes')).not.toBeDisabled()   // a category alone is enough
    fireEvent.click(screen.getByText('Request changes'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith({ method: 'post',
      url: '/api/v1/admin/advertising/campaigns/5/request-changes',
      data: { note: '', issues: [{ category: 'DESTINATION', note: '' }] } }))
  })

  it('resolves an origin only with evidence and the password', async () => {
    render(<AdminAdvertising />)
    const personal = await screen.findByText('Personal submission (20%)')
    expect(personal).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Evidence for entry 41'), { target: { value: 'Uploaded by the member' } })
    fireEvent.click(screen.getByText('Nomination (10%)'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith({ method: 'post',
      url: '/api/v1/admin/advertising/origins/41/resolve',
      data: { origin_kind: 'NOMINATION', note: 'Uploaded by the member', current_password: '' } }))
  })
})
