import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import en from './translations/en.json'

/** The site is English-only: the 404 page reads these strings from en.json. */
describe('404 page copy', () => {
  const copy = en.not_found as Record<string, string>

  it('has every string the page asks for', () => {
    const page = readFileSync(join(__dirname, '..', 'app', 'not-found.tsx'), 'utf8')
    const keys = [...page.matchAll(/t\('not_found\.([a-z_]+)'\)/g)].map((m) => m[1])
    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) expect(copy[key], key).toBeTruthy()
  })

  it('is English, not French and not a placeholder', () => {
    expect(copy.title).toBe('Page not found')
    expect(copy.go_back).toBe('Go back')
    for (const [key, value] of Object.entries(copy)) {
      expect(value, key).not.toMatch(/introuvable|Retour|Accueil|Désolé|Liens rapides/i)
      expect(value, key).not.toMatch(/^(Description|Help Text)$/)
    }
    expect(copy.description.split(' ').length).toBeGreaterThan(5)
    expect(copy.help_text.split(' ').length).toBeGreaterThan(5)
  })
})
