import { describe, expect, it } from 'vitest'
import en from './translations/en.json'
import { requirementMessage, stepRequirements, type FormRequirementInput } from './participation-form-requirements'

const t = (key: string): string =>
  (key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en) as string) || ''

const nomination: FormRequirementInput = {
  title: 'Eric Omondi',
  descriptionLength: 40,
  isNomination: true,
  nominatorCountry: 'Kenya',
  asksNomineeAge: true,
  nomineeAgeDeclared: true,
  requiresVideo: true,
  hasVideo: true,
  hasVideoDuplicateError: false,
  imageCount: 0,
  minImages: 0,
}

describe('participation form requirements', () => {
  it('a complete Comedy nomination has nothing missing on any step', () => {
    expect(stepRequirements(0, nomination)).toEqual([])
    expect(stepRequirements(1, nomination)).toEqual([])
    expect(stepRequirements(2, nomination)).toEqual([])
  })

  it('names the title and description problems on the information step', () => {
    expect(stepRequirements(0, { ...nomination, title: '', descriptionLength: 0 })).toEqual(['title_missing', 'description_missing'])
    expect(stepRequirements(0, { ...nomination, title: 'Eno', descriptionLength: 3 })).toEqual(['title_too_short', 'description_too_short'])
    expect(stepRequirements(0, { ...nomination, title: 'x'.repeat(101), descriptionLength: 501 })).toEqual(['title_too_long', 'description_too_long'])
  })

  it('names the nomination media-step requirements', () => {
    const bare = { ...nomination, nominatorCountry: '', nomineeAgeDeclared: false, hasVideo: false }
    expect(stepRequirements(1, bare)).toEqual(['country_missing', 'age_missing', 'video_missing'])
    expect(stepRequirements(1, { ...nomination, hasVideoDuplicateError: true })).toEqual(['video_duplicate'])
  })

  it('does not ask the age question when editing', () => {
    expect(stepRequirements(1, { ...nomination, asksNomineeAge: false, nomineeAgeDeclared: false })).toEqual([])
  })

  it('participations need images, nominations never do', () => {
    const participation = { ...nomination, isNomination: false, minImages: 1, requiresVideo: false, hasVideo: false }
    expect(stepRequirements(1, participation)).toEqual(['images_missing'])
    expect(stepRequirements(1, { ...participation, imageCount: 1 })).toEqual([])
  })

  it('every requirement has an English message', () => {
    for (const req of ['title_missing', 'title_too_short', 'title_too_long', 'description_missing', 'description_too_short',
      'description_too_long', 'country_missing', 'age_missing', 'video_missing', 'video_duplicate', 'images_missing'] as const) {
      expect(requirementMessage(req, t)).toMatch(/\w/)
      expect(requirementMessage(req, () => '')).toMatch(/\w/)
    }
  })
})
