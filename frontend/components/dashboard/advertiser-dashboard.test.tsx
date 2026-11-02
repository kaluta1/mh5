import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { request: requestMock }, apiService: {} }))

import { AdvertiserDashboard, estimateImpressions } from './advertiser-dashboard'

const CAMPAIGN = {
  id: 7, name: 'Spring', status: 'CHANGES_REQUESTED', funding: 'FUNDED', budget_total: '10.00', daily_cap: null,
  cpm_rate_usd: '0.5000', estimated_impressions: 20000, estimated_remaining_impressions: 20000, spent: '0.00',
  remaining_budget: '10.00', delivery_progress_percent: '0.0', served_impressions: 0, valid_impressions: 0,
  invalid_events: 0, clicks: null, review_note: 'Use a clearer headline', placements: ['IN_FEED'], daily: [],
  by_placement: [], creatives: [{ id: 3, headline: 'Hello', body: 'Body', destination_url: 'https://example.com',
    image_url: null, review_status: 'PENDING', image: null }],
}
const OVERVIEW = {
  pricing_state: 'CONFIGURED', cpm_rate_usd: '0.5000', min_campaign_budget_usd: '10.00', campaigns_enabled: false,
  funding_enabled: false, available_credit: '0.00', credit_in_campaigns: '10.00', refund_policy: 'No automatic refunds',
  packages: [
    { code: 'MYHIGH5_CPM_CAMPAIGN', name: 'MyHigh5 CPM campaign', price: '0.5000', currency: 'USD',
      price_unit: 'USD per 1,000 valid viewable impressions', minimum_budget: '10.00',
      estimated_impressions_at_minimum: 20000, placements: ['SIDEBAR', 'IN_FEED', 'IN_CONTENT'],
      payment: 'Prepaid advertiser credit', state: 'PRICED_NOT_ACTIVATED', purchasable: false },
    { code: 'LEGACY_AD_SYSTEM', name: 'Legacy ad_* campaigns', price: null, state: 'RETIRED', purchasable: false, placements: [] },
  ],
  campaigns: [CAMPAIGN],
}

describe('AdvertiserDashboard', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockResolvedValue({ status: 200, data: OVERVIEW })
  })

  it('estimates the theoretical impressions exactly', () => {
    expect(estimateImpressions('10', '0.50')).toBe(20000)
    expect(estimateImpressions('10.00', '0.5000')).toBe(20000)
    expect(estimateImpressions('25.5', '0.50')).toBe(51000)
    expect(estimateImpressions('', '0.50')).toBeNull()
    expect(estimateImpressions('10', null)).toBeNull()
  })

  it('shows packages, the price, the closed state and the minimum budget warning', async () => {
    render(<AdvertiserDashboard />)
    expect(await screen.findByTestId('ad-package-MYHIGH5_CPM_CAMPAIGN')).toHaveTextContent('up to 20,000 impressions')
    expect(screen.getByTestId('ad-package-LEGACY_AD_SYSTEM')).toHaveTextContent('retired')
    expect(screen.getByTestId('ad-price')).toHaveTextContent('Minimum campaign budget: 10.00 USD')
    expect(screen.getByTestId('ad-not-open')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Total budget (USD)'), { target: { value: '9' } })
    expect(screen.getByTestId('ad-estimate')).toHaveTextContent('The minimum campaign budget is 10.00 USD')
    expect(screen.getByText('Create draft')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Total budget (USD)'), { target: { value: '10' } })
    expect(screen.getByTestId('ad-estimate')).toHaveTextContent('Up to 20,000 billable impressions')
    expect(screen.getByText('Create draft')).not.toBeDisabled()
  })

  it('shows the review note, analytics, a preview and the change-request actions', async () => {
    render(<AdvertiserDashboard />)
    expect(await screen.findByTestId('campaign-status-7')).toHaveTextContent('Changes requested')
    expect(screen.getByTestId('campaign-note-7')).toHaveTextContent('Use a clearer headline')
    expect(screen.getByTestId('campaign-analytics-7')).toHaveTextContent('Not tracked')
    expect(screen.getAllByTestId('ad-preview')[0]).toHaveTextContent('Sponsored')
    expect(screen.getByText('Resubmit for review')).toBeDisabled()      // campaigns are not open
    fireEvent.click(screen.getByText('Cancel campaign'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
      { method: 'post', url: '/api/v1/advertising/advertiser/campaigns/7/cancel', data: undefined }))
  })

  it('uploads a creative image as form data to the owner route', async () => {
    render(<AdvertiserDashboard />)
    const input = await screen.findByLabelText('Upload image for creative 3')
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'ad.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => {
      const call = requestMock.mock.calls.find((c) => String(c[0].url).endsWith('/creatives/3/image'))
      expect(call).toBeTruthy()
      expect(call![0].data).toBeInstanceOf(FormData)
    })
  })
})
