import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import en from './en.json'

// The site is English-only (language-context forces 'en'). These guard against French or
// key-name placeholder text reaching members again.
const FRENCH = /[éèêëàâçùûüôîïœ]|\b(vous|votre|veuillez|erreur|aucun|aucune|réussi|échec|vérification|paiement)\b/i

function strings(node: unknown, path = ''): [string, string][] {
  if (typeof node === 'string') return [[path, node]]
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) => strings(v, path ? `${path}.${k}` : k))
  }
  return []
}

/** Source text without comments, so only code and user-facing strings are checked. */
function code(file: string): string {
  return readFileSync(join(process.cwd(), file), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('English-only content', () => {
  it('en.json contains no French', () => {
    const french = strings(en).filter(([, value]) => FRENCH.test(value))
    expect(french).toEqual([])
  })

  it('en.json has no key-name placeholders where proper English was written', () => {
    const value = (path: string) => path.split('.').reduce<any>((node, k) => node?.[k], en)
    expect(value('dashboard.contests.tooltip_votes_author')).not.toBe('Tooltip Votes Author')
    expect(value('common.profile_setup_description')).not.toBe('Profile Setup Description')
    expect(value('dashboard.messages.title')).toBe('Messages')
    expect(value('admin.kyc.reject_default_reason')).not.toBe('Reject Default Reason')
    // Placeholders the code fills in must survive.
    expect(value('admin.seasons.error_level_exists')).toContain('{level}')
    expect(value('admin.seasons.error_invalid_level')).toContain('{levels}')
  })

  it.each([
    'app/dashboard/kyc/page.tsx',
    'services/kyc-service.ts',
    'components/kyc/kaluta-verification-embed.tsx',
    'components/dashboard/settings-wallet-tab.tsx',
    'components/wallet/cashout-panel.tsx',
  ])('%s shows no French text', (file) => {
    const lines = code(file).split('\n').filter((line) => FRENCH.test(line))
    expect(lines).toEqual([])
  })

  it('KYC page fallbacks for the payment, attempts and document labels are English', () => {
    const src = code('app/dashboard/kyc/page.tsx')
    for (const text of ['Price per attempt', 'Payment required', 'Pay now', 'Attempts remaining', 'Reason for rejection',
      'Passport', 'National ID card', "Driver's license", 'Payment required for a new attempt']) {
      expect(src).toContain(text)
    }
  })
})
