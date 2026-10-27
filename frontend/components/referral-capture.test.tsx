import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

let pathname = '/profile/jane'
vi.mock('next/navigation', () => ({ usePathname: () => pathname }))

import { REFERRAL_STORAGE_KEY, ReferralCapture, referralCodeFromSearch } from './referral-capture'

function visit(url: string) {
  window.history.replaceState(null, '', url)
  pathname = new URL(url, 'https://myhigh5.com').pathname
}

beforeEach(() => localStorage.clear())

describe('invitation capture on every page', () => {
  it('remembers ?ref= on a page that had no capture of its own (e.g. a profile)', () => {
    visit('/profile/jane?ref=INV00042')
    render(<ReferralCapture />)
    expect(localStorage.getItem(REFERRAL_STORAGE_KEY)).toBe('INV00042')
  })

  it('the latest invitation wins, exactly as on the pages that already captured it', () => {
    localStorage.setItem(REFERRAL_STORAGE_KEY, 'OLDCODE1')
    visit('/dashboard/groups/7?referral=NEWCODE2')
    render(<ReferralCapture />)
    expect(localStorage.getItem(REFERRAL_STORAGE_KEY)).toBe('NEWCODE2')
  })

  it('a page without ?ref= (a neutral short link) keeps the earlier invitation', () => {
    localStorage.setItem(REFERRAL_STORAGE_KEY, 'KEEPME01')
    visit('/faq')
    render(<ReferralCapture />)
    expect(localStorage.getItem(REFERRAL_STORAGE_KEY)).toBe('KEEPME01')
  })

  it('ignores malformed values', () => {
    expect(referralCodeFromSearch('?ref=<script>')).toBeNull()
    expect(referralCodeFromSearch('?ref=' + 'x'.repeat(100))).toBeNull()
    expect(referralCodeFromSearch('?ref=')).toBeNull()
    expect(referralCodeFromSearch('?ref=AB_c-12')).toBe('AB_c-12')
  })
})
