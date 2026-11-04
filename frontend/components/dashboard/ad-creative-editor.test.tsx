import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { request: requestMock }, apiService: {} }))

import { CreativeEditor } from './ad-creative-editor'

const APPROVED = {
  id: 5, headline: 'Fresh coffee', body: 'Daily', display_name: 'Acme', cta_code: 'SHOP_NOW',
  destination_url: 'https://www.acme.example/', review_status: 'APPROVED', serving: true, review_issues: [],
  image_url: null, compatibility: { IN_FEED: { compatible: true, message: 'Fits this placement' },
    SIDEBAR: { compatible: false, message: 'Use a 6:5 image (600x500)' } },
}

describe('CreativeEditor', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockResolvedValue({ status: 200, data: { id: 9, review_status: 'DRAFT' } })
  })

  it('counts characters live and blocks over-limit copy', () => {
    render(<CreativeEditor campaignId={1} onSaved={() => {}} />)
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'x'.repeat(41) } })
    expect(screen.getAllByTestId('char-counter')[0]).toHaveTextContent('41/40')
    expect(screen.getByText('Save draft')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Short' } })
    expect(screen.getAllByTestId('char-counter')[0]).toHaveTextContent('5/40')
    expect(screen.getByText('Save draft')).not.toBeDisabled()
    expect(screen.getByText('Submit creative for review')).toBeDisabled()      // incomplete: display name, CTA, https
  })

  it('saves an incomplete draft, shows the domain, tests the destination safely and previews every placement', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const onSaved = vi.fn()
    render(<CreativeEditor campaignId={1} placements={['IN_FEED', 'SIDEBAR']} onSaved={onSaved} />)
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Hello' } })
    fireEvent.change(screen.getByLabelText('Destination URL'), { target: { value: 'http://acme.example' } })
    expect(screen.getByTestId('destination-domain')).toHaveTextContent('Must start with https://')
    expect(screen.getByText('Test destination')).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Destination URL'), { target: { value: 'https://www.acme.example/p' } })
    expect(screen.getByTestId('destination-domain')).toHaveTextContent('Shown as acme.example')
    fireEvent.click(screen.getByText('Test destination'))
    expect(open).toHaveBeenCalledWith('https://www.acme.example/p', '_blank', 'noopener,noreferrer')
    fireEvent.change(screen.getByLabelText('Call-to-action'), { target: { value: 'LEARN_MORE' } })
    const previews = screen.getAllByTestId('ad-preview')
    expect(previews).toHaveLength(2)
    expect(within(previews[0]).getByTestId('ad-cta')).toHaveTextContent('Learn more')
    expect(within(previews[1]).getByTestId('ad-domain')).toHaveTextContent('acme.example')
    expect(requestMock).not.toHaveBeenCalled()                                // previews never call the ad API
    fireEvent.click(screen.getByText('Save draft'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith(expect.objectContaining({
      method: 'post', url: '/api/v1/advertising/advertiser/campaigns/1/creatives',
      data: expect.objectContaining({ headline: 'Hello', cta_code: 'LEARN_MORE', submit_for_review: false }) })))
    expect(onSaved).toHaveBeenCalledWith('Draft saved')
    open.mockRestore()
  })

  it('a change to an approved creative is saved as a new version that needs approval', async () => {
    requestMock.mockResolvedValue({ status: 200, data: { id: 6, review_status: 'DRAFT', supersedes_creative_id: 5 } })
    const onSaved = vi.fn()
    render(<CreativeEditor campaignId={1} creative={APPROVED} onSaved={onSaved} />)
    expect(screen.getByText('serving')).toBeInTheDocument()
    expect(screen.getByTestId('creative-compat-5')).toHaveTextContent('SIDEBAR: Use a 6:5 image')
    expect(screen.getByText('Save changes (needs approval)')).toBeDisabled()    // nothing changed yet
    fireEvent.change(screen.getByLabelText('Headline'), { target: { value: 'Fresher coffee' } })
    fireEvent.click(screen.getByText('Save changes (needs approval)'))
    await waitFor(() => expect(requestMock).toHaveBeenCalledWith(expect.objectContaining({
      method: 'patch', url: '/api/v1/advertising/advertiser/campaigns/1/creatives/5' })))
    expect(onSaved).toHaveBeenCalledWith(expect.stringContaining('the approved version keeps running'))
  })

  it('uploads media with progress to the owner route', async () => {
    requestMock.mockImplementation(async (config) => {
      config.onUploadProgress?.({ loaded: 50, total: 100 })
      return { status: 200, data: {} }
    })
    render(<CreativeEditor campaignId={1} creative={{ ...APPROVED, review_status: 'DRAFT' }} onSaved={() => {}} />)
    const file = new File([new Uint8Array([0, 0, 0, 24])], 'ad.mp4', { type: 'video/mp4' })
    fireEvent.change(screen.getByLabelText('Upload video for creative 5'), { target: { files: [file] } })
    await waitFor(() => {
      const call = requestMock.mock.calls.find((c) => String(c[0].url).endsWith('/creatives/5/video'))
      expect(call).toBeTruthy()
      expect(call![0].data).toBeInstanceOf(FormData)
      expect(typeof call![0].onUploadProgress).toBe('function')
    })
  })
})
