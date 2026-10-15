/**
 * Why the participation / nomination form cannot move on.
 *
 * The Next and Submit buttons are disabled while a step is incomplete; this lists
 * what is still missing so the form can say so instead of a silent grey button.
 */
export const MIN_CONTENT_TITLE_LENGTH = 4
export const MAX_CONTENT_TITLE_LENGTH = 100
export const MIN_CONTENT_DESCRIPTION_LENGTH = 4
export const MAX_CONTENT_DESCRIPTION_LENGTH = 500

export type FormRequirement =
  | 'title_missing'
  | 'title_too_short'
  | 'title_too_long'
  | 'description_missing'
  | 'description_too_short'
  | 'description_too_long'
  | 'country_missing'
  | 'age_missing'
  | 'video_missing'
  | 'video_duplicate'
  | 'images_missing'

export interface FormRequirementInput {
  title: string
  descriptionLength: number
  isNomination: boolean
  nominatorCountry: string
  asksNomineeAge: boolean
  nomineeAgeDeclared: boolean
  requiresVideo: boolean
  hasVideo: boolean
  hasVideoDuplicateError: boolean
  imageCount: number
  minImages: number
}

export function infoStepRequirements(input: Pick<FormRequirementInput, 'title' | 'descriptionLength'>): FormRequirement[] {
  const missing: FormRequirement[] = []
  const title = input.title.trim().length
  if (title === 0) missing.push('title_missing')
  else if (title < MIN_CONTENT_TITLE_LENGTH) missing.push('title_too_short')
  else if (title > MAX_CONTENT_TITLE_LENGTH) missing.push('title_too_long')
  const desc = input.descriptionLength
  if (desc === 0) missing.push('description_missing')
  else if (desc < MIN_CONTENT_DESCRIPTION_LENGTH) missing.push('description_too_short')
  else if (desc > MAX_CONTENT_DESCRIPTION_LENGTH) missing.push('description_too_long')
  return missing
}

export function mediaStepRequirements(input: FormRequirementInput): FormRequirement[] {
  const missing: FormRequirement[] = []
  if (input.isNomination && !input.nominatorCountry) missing.push('country_missing')
  if (input.isNomination && input.asksNomineeAge && !input.nomineeAgeDeclared) missing.push('age_missing')
  if (!input.isNomination && input.imageCount < input.minImages) missing.push('images_missing')
  if (input.hasVideoDuplicateError) missing.push('video_duplicate')
  else if (input.requiresVideo && !input.hasVideo) missing.push('video_missing')
  return missing
}

/** Requirements blocking the given step (0 info, 1 media, 2 review = everything). */
export function stepRequirements(step: number, input: FormRequirementInput): FormRequirement[] {
  if (step === 0) return infoStepRequirements(input)
  if (step === 1) return mediaStepRequirements(input)
  return [...infoStepRequirements(input), ...mediaStepRequirements(input)]
}

export function requirementMessage(req: FormRequirement, t: (key: string) => string): string {
  const fallback: Record<FormRequirement, string> = {
    title_missing: 'Enter a title.',
    title_too_short: `The title needs at least ${MIN_CONTENT_TITLE_LENGTH} characters.`,
    title_too_long: `The title can have at most ${MAX_CONTENT_TITLE_LENGTH} characters.`,
    description_missing: 'Enter a description.',
    description_too_short: `The description needs at least ${MIN_CONTENT_DESCRIPTION_LENGTH} characters.`,
    description_too_long: `The description can have at most ${MAX_CONTENT_DESCRIPTION_LENGTH} characters (formatting not counted).`,
    country_missing: "Select the nominee's country.",
    age_missing: 'Tell us whether the nominee is an adult.',
    video_missing: 'Add a link to the video (for example YouTube or TikTok).',
    video_duplicate: 'This video link is already used in this category and round. Use a different link.',
    images_missing: 'Add at least one image.',
  }
  return t(`participation.requirements.${req}`) || fallback[req]
}
