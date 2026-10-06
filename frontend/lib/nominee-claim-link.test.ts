import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import en from './translations/en.json'
import { nomineeClaimLink } from './nominee-claim-link'

const ORIGIN = 'https://myhigh5.example'
const TOKEN = 'synthetic-claim-token-0001'

describe('nominee claim link', () => {
  it('is built from the token the backend returned, for a nomination that is public at once', () => {
    const response = { id: 12, public_status: 'PUBLIC', next_step: null, nominee_claim_token: TOKEN }
    expect(nomineeClaimLink(response, ORIGIN)).toBe(`${ORIGIN}/nominations/claim#token=${TOKEN}`)
  })

  it('is the same for a nomination that is pending: publication does not decide it', () => {
    const pending = { id: 12, public_status: 'PENDING_REVIEW', nominee_claim_token: TOKEN }
    expect(nomineeClaimLink(pending, ORIGIN)).toBe(nomineeClaimLink({ nominee_claim_token: TOKEN }, ORIGIN))
  })

  it('is absent when the backend returned no token: nothing is made up', () => {
    for (const response of [{ id: 12, public_status: 'PUBLIC' }, { nominee_claim_token: null }, { nominee_claim_token: '' },
      { nominee_claim_token: '   ' }, { nominee_claim_token: 42 }, {}, null, undefined]) {
      expect(nomineeClaimLink(response as never, ORIGIN)).toBeNull()
    }
    expect(nomineeClaimLink({ nominee_claim_token: TOKEN }, null)).toBeNull()
  })

  it('keeps the token in the URL fragment and adds nothing else', () => {
    const link = nomineeClaimLink({ nominee_claim_token: TOKEN }, `${ORIGIN}/`) as string
    const url = new URL(link)
    expect(url.origin + url.pathname).toBe(`${ORIGIN}/nominations/claim`)
    expect(url.search).toBe('')
    expect(url.hash).toBe(`#token=${TOKEN}`)
  })
})

describe('the submission page', () => {
  const page = readFileSync(join(__dirname, '..', 'app', 'dashboard', 'contests', '[id]', 'apply', 'page.tsx'), 'utf8')
  const submit = page.slice(page.indexOf('// The nominee\'s one-time claim link'), page.indexOf('} catch (err: any) {'))

  it('takes the link from the submission response before deciding which success message to show', () => {
    expect(submit).toContain('nomineeClaimLink(response,')
    expect(submit.indexOf('setNomineeClaimLink(')).toBeLessThan(submit.indexOf("public_status === 'PENDING_REVIEW'"))
  })

  it('no longer discards it on the normal (public) success path', () => {
    expect(submit.match(/setNomineeClaimLink\(/g)).toHaveLength(1)
    expect(page).not.toContain('setNomineeClaimLink(null)')
  })

  it('offers no link when an existing entry is edited', () => {
    expect(submit).toMatch(/isEditingParticipation \? null : nomineeClaimLink\(response/)
  })

  it('shows it only when there is one, with the existing one-time wording', () => {
    expect(page).toContain('{nomineeClaimLinkUrl && (')
    expect(page).toContain("t('participation.claim_link_note')")
    expect(en.participation.claim_link_note).toMatch(/one-time link/)
  })

  it('does not make the link a condition of anything', () => {
    // publication, the success message and navigation never read the link
    expect(page.match(/nomineeClaimLinkUrl/g)).toHaveLength(4)   // state, the block's condition, its input, its copy button
  })
})
