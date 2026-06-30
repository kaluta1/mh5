import { describe, it, expect } from 'vitest'
import { getMetadataTranslations, detectLanguageFromHeaders, getKeywords } from './metadata-translations'

describe('metadata-translations', () => {
  it('returns English metadata by default', () => {
    const meta = getMetadataTranslations('en')
    expect(meta.siteName).toBe('MyHigh5')
    expect(meta.pages.contests.title).toContain('Contests')
  })

  it('returns French metadata when requested', () => {
    const meta = getMetadataTranslations('fr')
    expect(meta.pages.contests.title).toContain('Concours')
  })

  it('falls back to English for unsupported languages', () => {
    const meta = getMetadataTranslations('zz' as any)
    expect(meta.siteName).toBe('MyHigh5')
    expect(meta.pages.home.title).toContain('MyHigh5')
  })

  it('detects language from cookie header', () => {
    const headers = new Headers({ cookie: 'myhigh5-language=fr' })
    expect(detectLanguageFromHeaders(headers)).toBe('fr')
  })

  it('defaults to English when only accept-language is set', () => {
    const headers = new Headers({ 'accept-language': 'es-ES,es;q=0.9' })
    expect(detectLanguageFromHeaders(headers)).toBe('en')
  })

  it('returns keywords', () => {
    expect(getKeywords('en')).toContain('contests')
    expect(getKeywords('fr')).toContain('concours')
  })
})
