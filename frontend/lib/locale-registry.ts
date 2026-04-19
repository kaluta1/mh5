/**
 * UI language catalog (100 locales). Display names for the selector; copy still comes from
 * `translations` in `translations.ts`. Locales without a dedicated bundle use English until
 * you add one or wire machine translation (DeepL, Google Cloud Translation, etc.).
 */
export interface LanguageInfo {
  name: string
  flag: string
  rtl?: boolean
}

const catalog = {
  en: { name: "English", flag: "🇬🇧" },
  zh: { name: "中文 (Chinese)", flag: "🇨🇳" },
  hi: { name: "हिन्दी (Hindi)", flag: "🇮🇳" },
  es: { name: "Español", flag: "🇪🇸" },
  fr: { name: "Français", flag: "🇫🇷" },
  ar: { name: "العربية (Arabic)", flag: "🇸🇦", rtl: true },
  bn: { name: "বাংলা (Bengali)", flag: "🇧🇩" },
  pt: { name: "Português", flag: "🇵🇹" },
  ru: { name: "Русский", flag: "🇷🇺" },
  id: { name: "Bahasa Indonesia", flag: "🇮🇩" },
  ur: { name: "اردو (Urdu)", flag: "🇵🇰", rtl: true },
  de: { name: "Deutsch", flag: "🇩🇪" },
  ja: { name: "日本語", flag: "🇯🇵" },
  sw: { name: "Kiswahili", flag: "🇹🇿" },
  mr: { name: "मराठी (Marathi)", flag: "🇮🇳" },
  te: { name: "తెలుగు (Telugu)", flag: "🇮🇳" },
  tr: { name: "Türkçe", flag: "🇹🇷" },
  ta: { name: "தமிழ் (Tamil)", flag: "🇮🇳" },
  vi: { name: "Tiếng Việt", flag: "🇻🇳" },
  ko: { name: "한국어", flag: "🇰🇷" },
  it: { name: "Italiano", flag: "🇮🇹" },
  th: { name: "ไทย (Thai)", flag: "🇹🇭" },
  gu: { name: "ગુજરાતી (Gujarati)", flag: "🇮🇳" },
  fa: { name: "فارسی (Persian)", flag: "🇮🇷", rtl: true },
  pl: { name: "Polski", flag: "🇵🇱" },
  uk: { name: "Українська", flag: "🇺🇦" },
  ml: { name: "മലയാളം (Malayalam)", flag: "🇮🇳" },
  kn: { name: "ಕನ್ನಡ (Kannada)", flag: "🇮🇳" },
  or: { name: "ଓଡ଼ିଆ (Odia)", flag: "🇮🇳" },
  my: { name: "မြန်မာ (Burmese)", flag: "🇲🇲" },
  pa: { name: "ਪੰਜਾਬੀ (Punjabi)", flag: "🇮🇳" },
  ne: { name: "नेपाली (Nepali)", flag: "🇳🇵" },
  si: { name: "සිංහල (Sinhala)", flag: "🇱🇰" },
  km: { name: "ខ្មែរ (Khmer)", flag: "🇰🇭" },
  lo: { name: "ລາວ (Lao)", flag: "🇱🇦" },
  ms: { name: "Bahasa Melayu", flag: "🇲🇾" },
  tl: { name: "Filipino", flag: "🇵🇭" },
  fi: { name: "Suomi", flag: "🇫🇮" },
  no: { name: "Norsk", flag: "🇳🇴" },
  da: { name: "Dansk", flag: "🇩🇰" },
  sv: { name: "Svenska", flag: "🇸🇪" },
  is: { name: "Íslenska", flag: "🇮🇸" },
  ro: { name: "Română", flag: "🇷🇴" },
  nl: { name: "Nederlands", flag: "🇳🇱" },
  el: { name: "Ελληνικά", flag: "🇬🇷" },
  he: { name: "עברית (Hebrew)", flag: "🇮🇱", rtl: true },
  cs: { name: "Čeština", flag: "🇨🇿" },
  hu: { name: "Magyar", flag: "🇭🇺" },
  sk: { name: "Slovenčina", flag: "🇸🇰" },
  bg: { name: "Български", flag: "🇧🇬" },
  sr: { name: "Српски", flag: "🇷🇸" },
  hr: { name: "Hrvatski", flag: "🇭🇷" },
  bs: { name: "Bosanski", flag: "🇧🇦" },
  sl: { name: "Slovenščina", flag: "🇸🇮" },
  lt: { name: "Lietuvių", flag: "🇱🇹" },
  lv: { name: "Latviešu", flag: "🇱🇻" },
  et: { name: "Eesti", flag: "🇪🇪" },
  ka: { name: "ქართული (Georgian)", flag: "🇬🇪" },
  hy: { name: "Հայերեն (Armenian)", flag: "🇦🇲" },
  az: { name: "Azərbaycanca", flag: "🇦🇿" },
  kk: { name: "Қазақша", flag: "🇰🇿" },
  ky: { name: "Кыргызча", flag: "🇰🇬" },
  uz: { name: "Oʻzbekcha", flag: "🇺🇿" },
  mn: { name: "Монгол", flag: "🇲🇳" },
  ps: { name: "پښتو (Pashto)", flag: "🇦🇫", rtl: true },
  ku: { name: "Kurdî", flag: "🇮🇶", rtl: true },
  am: { name: "አማርኛ (Amharic)", flag: "🇪🇹" },
  zu: { name: "isiZulu", flag: "🇿🇦" },
  xh: { name: "isiXhosa", flag: "🇿🇦" },
  af: { name: "Afrikaans", flag: "🇿🇦" },
  so: { name: "Soomaali", flag: "🇸🇴" },
  ha: { name: "Hausa", flag: "🇳🇬" },
  yo: { name: "Yorùbá", flag: "🇳🇬" },
  ig: { name: "Igbo", flag: "🇳🇬" },
  rw: { name: "Kinyarwanda", flag: "🇷🇼" },
  mg: { name: "Malagasy", flag: "🇲🇬" },
  ny: { name: "Chichewa", flag: "🇲🇼" },
  wo: { name: "Wolof", flag: "🇸🇳" },
  sn: { name: "ChiShona", flag: "🇿🇼" },
  st: { name: "Sesotho", flag: "🇱🇸" },
  eu: { name: "Euskara", flag: "🇪🇸" },
  ca: { name: "Català", flag: "🇪🇸" },
  gl: { name: "Galego", flag: "🇪🇸" },
  cy: { name: "Cymraeg", flag: "🏴" },
  ga: { name: "Gaeilge", flag: "🇮🇪" },
  mt: { name: "Malti", flag: "🇲🇹" },
  sq: { name: "Shqip", flag: "🇦🇱" },
  mk: { name: "Македонски", flag: "🇲🇰" },
  be: { name: "Беларуская", flag: "🇧🇾" },
  tg: { name: "Тоҷикӣ", flag: "🇹🇯" },
  tk: { name: "Türkmençe", flag: "🇹🇲" },
  dv: { name: "ދިވެހި (Dhivehi)", flag: "🇲🇻", rtl: true },
  bo: { name: "བོད་སྐད་ (Tibetan)", flag: "🇨🇳" },
  ug: { name: "ئۇيغۇرچە (Uyghur)", flag: "🇨🇳", rtl: true },
  sd: { name: "سنڌي (Sindhi)", flag: "🇵🇰", rtl: true },
  as: { name: "অসমীয়া (Assamese)", flag: "🇮🇳" },
  ceb: { name: "Cebuano", flag: "🇵🇭" },
  jv: { name: "Basa Jawa", flag: "🇮🇩" },
  su: { name: "Basa Sunda", flag: "🇮🇩" },
  lb: { name: "Lëtzebuergesch", flag: "🇱🇺" },
} satisfies Record<string, LanguageInfo>

export const languages: Record<keyof typeof catalog, LanguageInfo> = catalog

export type Language = keyof typeof catalog

export const LANGUAGE_CODES = Object.freeze(
  (Object.keys(catalog) as Language[]).slice().sort(),
)

if (LANGUAGE_CODES.length !== 100) {
  // eslint-disable-next-line no-console -- build-time sanity check
  console.warn(
    `[locale-registry] Expected exactly 100 languages, got ${LANGUAGE_CODES.length}`,
  )
}
