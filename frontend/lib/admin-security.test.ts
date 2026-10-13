import { describe, expect, it } from 'vitest'

import { GRANT_REASON_MIN_LENGTH, adminErrorText, validGrantReason } from './admin-security'

describe('admin security helpers', () => {
  it('shows the server message of a refused privileged action, whatever shape it has', () => {
    const refused = (detail: unknown) => ({ response: { status: 403, data: { detail } } })
    expect(adminErrorText(refused({ code: 'PERMISSION_REQUIRED', message: 'The manage_administrators permission is required.' }), 'x'))
      .toBe('The manage_administrators permission is required.')
    expect(adminErrorText(refused('Utilisateur non trouvé'), 'x')).toBe('Utilisateur non trouvé')
    expect(adminErrorText(refused([{ msg: 'Field required' }]), 'x')).toBe('Field required')
    // Nothing usable from the server: the page's own wording, never "[object Object]".
    for (const detail of [undefined, null, '', '   ', {}, { code: 'X' }, []]) {
      expect(adminErrorText(refused(detail), 'Could not be saved')).toBe('Could not be saved')
    }
    expect(adminErrorText(new Error('network'), 'Could not be saved')).toBe('Could not be saved')
    expect(adminErrorText(undefined, 'Could not be saved')).toBe('Could not be saved')
  })

  it('asks for a payment reference that says something', () => {
    expect(GRANT_REASON_MIN_LENGTH).toBe(10)
    expect(validGrantReason('Bank transfer ref 0042')).toBe(true)
    expect(validGrantReason('  ref 12345  ')).toBe(false)
    for (const bad of ['', 'paid', '          ', '   x      y   ', 'a\n\n\n\n\n\n\n\n\nb']) {
      expect(validGrantReason(bad)).toBe(false)
    }
  })
})
