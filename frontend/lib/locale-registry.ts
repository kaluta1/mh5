/**
 * UI language catalog backed by local JSON bundles only.
 * No AI runtime translation fallback.
 */
export interface LanguageInfo {
  name: string
  flag: string
  rtl?: boolean
}

const catalog = {
  en: { name: "English", flag: "🇬🇧" },
  fr: { name: "Français", flag: "🇫🇷" },
  es: { name: "Español", flag: "🇪🇸" },
  de: { name: "Deutsch", flag: "🇩🇪" },
  pt: { name: "Português", flag: "🇵🇹" },
  sw: { name: "Kiswahili", flag: "🇹🇿" },
  ar: { name: "العربية", flag: "🇸🇦", rtl: true },
  zh: { name: "中文", flag: "🇨🇳" },
  hi: { name: "हिन्दी", flag: "🇮🇳" },
  ru: { name: "Русский", flag: "🇷🇺" },
  it: { name: "Italiano", flag: "🇮🇹" },
  nl: { name: "Nederlands", flag: "🇳🇱" },
  tr: { name: "Türkçe", flag: "🇹🇷" },
  ja: { name: "日本語", flag: "🇯🇵" },
  ko: { name: "한국어", flag: "🇰🇷" },
  id: { name: "Bahasa Indonesia", flag: "🇮🇩" },
  ur: { name: "اردو", flag: "🇵🇰", rtl: true },
  bn: { name: "বাংলা", flag: "🇧🇩" },
  te: { name: "తెలుగు", flag: "🇮🇳" },
  ta: { name: "தமிழ்", flag: "🇮🇳" },
  vi: { name: "Tiếng Việt", flag: "🇻🇳" },
  th: { name: "ไทย", flag: "🇹🇭" },
  fa: { name: "فارسی", flag: "🇮🇷", rtl: true },
  pl: { name: "Polski", flag: "🇵🇱" },
  uk: { name: "Українська", flag: "🇺🇦" },
  ms: { name: "Bahasa Melayu", flag: "🇲🇾" },
  tl: { name: "Filipino", flag: "🇵🇭" },
  ro: { name: "Română", flag: "🇷🇴" },
  el: { name: "Ελληνικά", flag: "🇬🇷" },
  he: { name: "עברית", flag: "🇮🇱", rtl: true },
  cs: { name: "Čeština", flag: "🇨🇿" },
  hu: { name: "Magyar", flag: "🇭🇺" },
  sv: { name: "Svenska", flag: "🇸🇪" },
  da: { name: "Dansk", flag: "🇩🇰" },
  no: { name: "Norsk", flag: "🇳🇴" },
  fi: { name: "Suomi", flag: "🇫🇮" },
  mr: { name: "मराठी", flag: "🇮🇳" },
  pa: { name: "ਪੰਜਾਬੀ", flag: "🇮🇳" },
  ml: { name: "മലയാളം", flag: "🇮🇳" },
  kn: { name: "ಕನ್ನಡ", flag: "🇮🇳" },
  gu: { name: "ગુજરાતી", flag: "🇮🇳" },
  am: { name: "አማርኛ", flag: "🇪🇹" },
  yo: { name: "Yorùbá", flag: "🇳🇬" },
  ha: { name: "Hausa", flag: "🇳🇬" },
  rw: { name: "Kinyarwanda", flag: "🇷🇼" },
} satisfies Record<string, LanguageInfo>

export const languages: Record<keyof typeof catalog, LanguageInfo> = catalog

export type Language = keyof typeof catalog

export const LANGUAGE_CODES = Object.freeze(
  (Object.keys(catalog) as Language[]).slice().sort(),
)

if (LANGUAGE_CODES.length !== 45) {
  // eslint-disable-next-line no-console -- build-time sanity check
  console.warn(
    `[locale-registry] Expected exactly 45 languages, got ${LANGUAGE_CODES.length}`,
  )
}
