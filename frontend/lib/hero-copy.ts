/**
 * Static hero copy — bundled synchronously (no LanguageProvider / async chunks).
 * Mobile preview via maintenance bypass must never show icon-only buttons.
 */
import en from './translations/en.json'

export const HERO_COPY = {
  titleLine1: String(en.hero?.title_line1 ?? 'Join the largest'),
  titleLine2: String(en.hero?.title_line2 ?? 'contest platform'),
  titleLine3: String(en.hero?.title_line3 ?? 'in the world'),
  subtitle: String(en.hero?.subtitle ?? 'Global Contest Platform'),
  cta: String(en.hero?.cta ?? 'Get Started Now'),
  contests: String(en.navigation?.contests ?? 'Contests'),
  support: String(en.hero?.trust?.support ?? '24/7 Support'),
  free: String(en.hero?.trust?.free ?? 'Free to Join'),
} as const
