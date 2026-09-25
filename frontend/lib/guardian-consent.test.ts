import { describe, expect, it } from 'vitest'
import { GUARDIAN_SCOPE_LABELS, readFragmentToken } from './guardian-consent'

describe('readFragmentToken', () => {
  it('reads a well-formed token from the fragment', () => {
    expect(readFragmentToken('#token=abcDEF123_-xyz')).toBe('abcDEF123_-xyz')
  })

  it('rejects missing, short or malformed tokens', () => {
    expect(readFragmentToken('')).toBe('')
    expect(readFragmentToken('#token=short')).toBe('')
    expect(readFragmentToken('#token=<script>alert(1)</script>')).toBe('')
    expect(readFragmentToken('#other=abcdefghijklmnop')).toBe('')
  })
})

describe('GUARDIAN_SCOPE_LABELS', () => {
  it('labels all eleven consent scopes', () => {
    expect(Object.keys(GUARDIAN_SCOPE_LABELS)).toHaveLength(11)
  })
})
