import { describe, expect, it } from 'vitest'
import {
  ENGLISH_TRANSLATIONS,
  lookupTranslation,
} from './translations-loader'

describe('lookupTranslation', () => {
  it('resolves nested English keys', () => {
    expect(lookupTranslation(ENGLISH_TRANSLATIONS, 'hero.cta')).toBe('Get Started Now')
    expect(lookupTranslation(ENGLISH_TRANSLATIONS, 'navigation.contests')).toBeTruthy()
  })

  it('returns empty string for missing keys', () => {
    expect(lookupTranslation(ENGLISH_TRANSLATIONS, 'hero.missing.key')).toBe('')
  })
})
