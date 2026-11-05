import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { request: requestMock }, apiService: {} }))

import { AdvertiserDashboard, estimateImpressions } from './advertiser-dashboard'

const CREATIVE = {
  id: 3, headline: 'Hello', body: 'Body', display_name: 'Acme', cta_code: 'SHOP_NOW', cta_label: 'Shop now',
  destination_url: 'https://www.example.com/x', destination_domain: 'example.com', image_url: null,
  review_status: 'REJECTED', review_note: '', review_issues: [{ category: 'COPY', note: 'Typo in headline' }],
  image: null, compatibility: null, supersedes_creative_id: null, serving: false,
}
const CAMPAIGN = {
  id: 7, name: 'Spring', status: 'CHANGES_REQUESTED', display_status: 'CHANGES_REQUIRED', funding: 'FUNDED',
  package: 'cpm', budget_total: '10.00', daily_cap: null, cpm_rate_usd: '0.5000', estimated_impressions: 20000,
  estimated_remaining_impressions: 20000, spent: '0.00', remaining_budget: '10.00', delivery_progress_percent: '0.0',
  served_impressions: 0, valid_impressions: 0, invalid_events: 0, clicks: 0, review_note: 'Use a clearer headline',
  review_issues: [{ category: 'MEDIA', note: 'Image is blurry' }], placements: ['IN_FEED'], daily: [], by_placement: [],
  schedule: { timezone: 'Africa/Nairobi', starts_after_approval: true, end_at_local: '2027-01-10T18:00:00+03:00' },
  non_delivery_reasons: [], creatives: [CREATIVE],
}
const OVERVIEW = {
  pricing_state: 'CONFIGURED', cpm_rate_usd: '0.5000', min_campaign_budget_usd: '10.00', campaigns_enabled: false,
  funding_enabled: false, available_credit: '5.00', credit_in_campaigns: '10.00', refund_policy: 'No automatic refunds',
  packages: [
    { code: 'MYHIGH5_CPM_CAMPAIGN', package_code: 'cpm', name: 'MyHigh5 CPM campaign', price: '0.5000', currency: 'USD',
      price_unit: 'USD per 1,000 valid viewable impressions', minimum_budget: '10.00',
      estimated_impressions_at_minimum: 20000, placements: ['SIDEBAR', 'IN_FEED', 'IN_CONTENT'],
      payment: 'Prepaid advertiser credit', state: 'PRICED_NOT_ACTIVATED', purchasable: false },
    { code: 'LEGACY_AD_SYSTEM', name: 'Legacy ad_* campaigns', price: null, state: 'RETIRED', purchasable: false, placements: [] },
  ],
  campaigns: [CAMPAIGN],
}
const PKG = (code: string, name: string, extra = {}) => ({
  code, name, price: '0.50', minimum_rate: '0.50', price_label: `0.50 USD per unit of ${code}`, billing_unit: 'unit',
  billable_event: `event of ${code}`, minimum_budget: '10.00', minimum_note: 'Minimum campaign budget 10.00 USD',
  supported_media: ['IMAGE'], supported_placements: ['IN_FEED', 'SIDEBAR', 'IN_CONTENT'], can_draft: true,
  purchasable: false, disabled_reason: null, ...extra,
})
const CATALOG = {
  packages: [PKG('cpm', 'Standard CPM'), PKG('cpc', 'Cost per click', { price_label: '0.05 USD per one valid click', minimum_rate: '0.05' }),
    PKG('cpv', 'Cost per view', { can_draft: false, disabled_reason: 'Video creatives cannot be stored or played yet' })],
  countries: [{ code: 'KE', name: 'Kenya' }, { code: 'UG', name: 'Uganda' }],
  page_types: [{ code: 'FEED', rendered: true, placements: ['SIDEBAR', 'IN_FEED'] },
    { code: 'CONTEST_ENTRY', rendered: true, placements: ['SIDEBAR', 'IN_CONTENT'] },
    { code: 'DISCOVERY', rendered: false, placements: ['SIDEBAR', 'IN_FEED'] }],
  budget: { available_credit: '5.00', fees: 'None', unused_credit: 'Returns to your credit' },
  launch: 'Delivery starts automatically once MyHigh5 approves the campaign.',
}

function respond(config: { method: string; url: string }) {
  const url = config.url
  if (url.endsWith('/advertiser/overview')) return { status: 200, data: OVERVIEW }
  if (url.endsWith('/advertiser/catalog')) return { status: 200, data: CATALOG }
  if (url.includes('/advertiser/estimate')) {
    const pkg = new URL(`http://x${url}`).searchParams.get('package')
    return { status: 200, data: pkg === 'cpc'
      ? { units: 20, unit: 'valid clicks', budget: '1.00', rate: '0.050000' }
      : { units: 20000, unit: 'valid viewable impressions', budget: '10.00', rate: '0.50' } }
  }
  return { status: 200, data: { id: 99, review_status: 'DRAFT' } }
}

describe('AdvertiserDashboard', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockImplementation(async (config) => respond(config))
  })

  it('estimates the theoretical impressions exactly', () => {
    expect(estimateImpressions('10', '0.50')).toBe(20000)
    expect(estimateImpressions('25.5', '0.50')).toBe(51000)
    expect(estimateImpressions('', '0.50')).toBeNull()
  })

  it('is package-first: package terms, disabled reasons and per-package estimates (never CPM for CPC)', async () => {
    render(<AdvertiserDashboard />)
    expect(await screen.findByTestId('package-card-cpc')).toHaveTextContent('0.05 USD per one valid click')
    expect(screen.getByTestId('package-reason-cpv')).toHaveTextContent('Video creatives cannot be stored')
    expect(screen.getByLabelText('Cost per view')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Total budget (USD)'), { target: { value: '9' } })
    expect(await screen.findByTestId('form-problems')).toHaveTextContent('The minimum campaign budget is 10.00 USD')
    fireEvent.click(screen.getByLabelText('Cost per click'))
    fireEvent.change(screen.getByLabelText('Total budget (USD)'), { target: { value: '1' } })
    await waitFor(() => expect(screen.getByTestId('ad-estimate')).toHaveTextContent('Up to 20 valid clicks'))
    expect(screen.getByTestId('ad-estimate')).not.toHaveTextContent('impressions')
    expect(screen.getByTestId('budget-panel')).toHaveTextContent('Available advertiser credit: 5.00 USD')
  })

  it('targets explicitly: searchable countries with names, no implicit widening, rendered page types only', async () => {
    render(<AdvertiserDashboard />)
    await screen.findByTestId('campaign-form')
    fireEvent.change(screen.getByLabelText('Campaign name'), { target: { value: 'Launch' } })
    fireEvent.click(screen.getByLabelText('Chosen countries'))
    expect(screen.getByTestId('form-problems')).toHaveTextContent('Choose at least one country')
    expect(screen.getByText('Save draft campaign')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Search countries'), { target: { value: 'ken' } })
    fireEvent.click(screen.getByRole('option', { name: 'Kenya (KE)' }))
    expect(screen.getByTestId('country-picker')).toHaveTextContent('Kenya (KE)')
    fireEvent.click(screen.getByLabelText('Chosen page types'))
    const pages = screen.getByTestId('page-types')
    expect(within(pages).getByText(/Discovery \(no ad slot yet\)/)).toBeInTheDocument()
    fireEvent.click(within(pages).getByLabelText(/Contest-entry pages/))
    const placements = screen.getByTestId('placements')
    expect(within(placements).getByLabelText('In-feed')).toBeDisabled()        // not shown on contest-entry pages
    fireEvent.click(within(placements).getByLabelText('Contest-entry panel'))
    fireEvent.change(screen.getByLabelText('End'), { target: { value: '2027-01-10T18:00' } })
    fireEvent.click(screen.getByText('Save draft campaign'))
    await waitFor(() => {
      const post = requestMock.mock.calls.find((c) => c[0].method === 'post' && c[0].url.endsWith('/advertiser/campaigns'))
      expect(post).toBeTruthy()
      expect(post![0].data).toMatchObject({ name: 'Launch', countries_mode: 'LIST', countries: ['KE'],
        page_types_mode: 'LIST', page_types: ['CONTEST_ENTRY'], placements: ['IN_CONTENT'], start_at: null,
        end_at: '2027-01-10T18:00' })
      expect(typeof post![0].data.timezone).toBe('string')
    })
  })

  it('shows a schedule with time zone, duration preview and the automatic launch disclosure', async () => {
    render(<AdvertiserDashboard />)
    await screen.findByTestId('campaign-form')
    fireEvent.click(screen.getByLabelText('Schedule a start'))
    fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2027-01-01T09:00' } })
    fireEvent.change(screen.getByLabelText('End'), { target: { value: '2027-01-03T12:30' } })
    expect(screen.getByTestId('schedule-preview')).toHaveTextContent('Duration: 2 days 3 h 30 min')
    expect(screen.getByTestId('schedule-preview')).toHaveTextContent('starts automatically once MyHigh5 approves')
  })

  it('shows display status, review issues by category and the creative editor', async () => {
    render(<AdvertiserDashboard />)
    expect(await screen.findByTestId('campaign-status-7')).toHaveTextContent('Changes required')
    expect(screen.getByTestId('campaign-note-7')).toHaveTextContent('MEDIA: Image is blurry')
    expect(screen.getByTestId('campaign-schedule-7')).toHaveTextContent('Starts after approval')
    expect(screen.getByTestId('creative-issues-3')).toHaveTextContent('COPY: Typo in headline')
    expect(screen.getByText('Resubmit for review')).toBeDisabled()          // campaigns are not open
    fireEvent.click(screen.getByText('Cancel campaign'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
      { method: 'post', url: '/api/v1/advertising/advertiser/campaigns/7/cancel', data: undefined }))
  })
})
