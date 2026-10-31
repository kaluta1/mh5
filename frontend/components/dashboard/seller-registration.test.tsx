import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const get = vi.fn()
const put = vi.fn()
const post = vi.fn()
vi.mock('@/lib/api', () => ({
  default: {
    get: (...a: unknown[]) => get(...a), put: (...a: unknown[]) => put(...a), post: (...a: unknown[]) => post(...a),
  },
}))

import { APPROVAL_MEANING, SellerRegistration } from './seller-registration'

const BASE_STATUS = {
  enforcement_enabled: true, can_sell: false,
  profile: { status: 'NONE', seller_category: null, public_label: null, reverify_due_at: null },
  application: null,
  declaration: { version: 'SELLER-DECLARATION-1', text: 'I declare that the information is true.' },
  product_categories: ['HANDMADE', 'FOOD'], regulated_categories: ['FOOD'],
  private_review_thresholds: { sales_usd: '1000.00', order_count: 20, note: 'Internal MyHigh5 review triggers.' },
}

const DRAFT_APP = {
  id: 4, status: 'DRAFT', seller_category: 'SOLE_TRADER', business_structure: 'EXEMPT', legal_name: 'Amina Juma',
  trading_name: null, residence_country: 'SG', establishment_country: 'SG', establishment_subdivision: null,
  customer_markets: [], business_address: null, contact_phone: null, product_categories: [], products_description: null,
  commercial_indicators: {}, registration_authority: null, registration_number: null, exemption_basis: null,
  tax_registered: null, tax_identifier_masked: null, licences: [], representative: null, ownership: [],
  declaration_accepted_at: null, submitted_at: null, decided_at: null, correction_request: null,
  missing_fields: ['trading_name'], documents: [], history: [],
}

beforeEach(() => { get.mockReset(); put.mockReset(); post.mockReset() })

describe('SellerRegistration', () => {
  it('offers business and private registration and explains what approval means', async () => {
    get.mockResolvedValue({ data: BASE_STATUS })
    render(<SellerRegistration />)
    expect(await screen.findByText('Register as a Business Seller')).toBeTruthy()
    expect(screen.getByText('Register as a Private Seller')).toBeTruthy()
    expect(screen.getByText(APPROVAL_MEANING)).toBeTruthy()
    expect(screen.getByText(/Publishing opens once your seller registration is approved/)).toBeTruthy()
    expect(screen.queryByText(/Government Approved/i)).toBeNull()
  })

  it('asks an exempt sole trader for the exemption basis instead of a registration number', async () => {
    get.mockResolvedValue({ data: { ...BASE_STATUS, application: DRAFT_APP } })
    render(<SellerRegistration />)
    expect(await screen.findByLabelText('Legal basis of your registration exemption')).toBeTruthy()
    expect(screen.queryByLabelText('Registration number')).toBeNull()
  })

  it('submits only after the declaration is accepted, with its version', async () => {
    get.mockResolvedValue({ data: { ...BASE_STATUS, application: { ...DRAFT_APP, seller_category: 'PRIVATE', business_structure: null } } })
    put.mockResolvedValue({ data: BASE_STATUS })
    post.mockResolvedValue({ data: BASE_STATUS })
    render(<SellerRegistration />)
    const submit = await screen.findByText('Submit application')
    expect((submit.closest('button') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText(BASE_STATUS.declaration.text))
    fireEvent.click(submit)
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/marketplace/seller/application/submit', {
      declaration_version: 'SELLER-DECLARATION-1', accept_declaration: true }))
  })
})
