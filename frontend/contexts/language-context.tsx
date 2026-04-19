"use client"

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { Language, LANGUAGE_CODES, languages, translations } from "@/lib/translations"
import { LANGUAGE_PREFERENCE_KEY, setLanguagePreferenceClient } from "@/lib/language-cookie"
import { flattenStringLeaves } from "@/lib/i18n-flatten"
import { loadAiTranslationFlat, mergeAiTranslationFlat } from "@/lib/i18n-ai-cache"
import { I18N_AI_CHUNK_KEYS } from "@/lib/i18n-ai-constants"
import { fetchTranslatedChunk } from "@/lib/i18n-fetch-translate"
import { localeUsesAiTranslation } from "@/lib/i18n-native-locales"

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  /** True while AI is filling missing strings for locales without a hand-written bundle */
  aiTranslationPending: boolean
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

const SUPPORTED_LANGUAGES = LANGUAGE_CODES as readonly Language[]

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en")
  /** Dot-key map for the active AI locale (English source keys → translated strings). */
  const [aiFlat, setAiFlat] = useState<Record<string, string>>({})
  const [aiTranslationPending, setAiTranslationPending] = useState(false)

  const flatEnglish = useMemo(() => flattenStringLeaves(translations.en), [])
  const hydrateAbortRef = useRef<AbortController | null>(null)
  const flatEnglishRef = useRef(flatEnglish)
  flatEnglishRef.current = flatEnglish

  const hydrateAi = useCallback(async (locale: string) => {
    if (!localeUsesAiTranslation(locale)) return

    hydrateAbortRef.current?.abort()
    const ac = new AbortController()
    hydrateAbortRef.current = ac
    const { signal } = ac

    const flatEn = flatEnglishRef.current
    let working = loadAiTranslationFlat(locale)
    setAiFlat(working)

    const allKeys = Object.keys(flatEn)
    const countMissing = () =>
      allKeys.reduce((n, k) => (working[k] ? n : n + 1), 0)

    if (allKeys.length > 0 && countMissing() === 0) {
      return
    }

    setAiTranslationPending(true)
    try {
      const chunkSize = I18N_AI_CHUNK_KEYS
      for (let i = 0; i < allKeys.length; i += chunkSize) {
        if (signal.aborted) return
        const batchKeys = allKeys.slice(i, i + chunkSize)
        const toSend: Record<string, string> = {}
        for (const k of batchKeys) {
          if (!working[k] && flatEn[k]) {
            toSend[k] = flatEn[k]
          }
        }
        if (Object.keys(toSend).length === 0) continue

        const patch = await fetchTranslatedChunk(locale, toSend, signal)
        if (signal.aborted) return
        if (patch === null) {
          break
        }

        working = mergeAiTranslationFlat(locale, patch)
        setAiFlat({ ...working })
        await new Promise((r) => setTimeout(r, 100))
      }
    } finally {
      setAiTranslationPending(false)
    }
  }, [])

  const setLanguage = useCallback(
    (lang: Language) => {
      setLanguageState(lang)
      const cached = loadAiTranslationFlat(lang)
      setAiFlat(cached)
      if (localeUsesAiTranslation(lang)) {
        void hydrateAi(lang)
      } else {
        hydrateAbortRef.current?.abort()
        setAiTranslationPending(false)
      }
    },
    [hydrateAi],
  )

  /** Load saved language before paint so the persist effect does not clobber localStorage with a stray `en`. */
  useLayoutEffect(() => {
    const savedLanguage = localStorage.getItem(LANGUAGE_PREFERENCE_KEY) as Language
    if (savedLanguage && SUPPORTED_LANGUAGES.includes(savedLanguage)) {
      setLanguageState(savedLanguage)
      setAiFlat(loadAiTranslationFlat(savedLanguage))
      if (localeUsesAiTranslation(savedLanguage)) {
        void hydrateAi(savedLanguage)
      }
    } else {
      setLanguageState("en")
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, "en")
    }
  }, [hydrateAi])

  useEffect(() => {
    localStorage.setItem(LANGUAGE_PREFERENCE_KEY, language)
    setLanguagePreferenceClient(language)
    if (typeof document !== "undefined") {
      const meta = languages[language]
      const html = document.documentElement
      if (html) {
        html.setAttribute("lang", language)
        html.setAttribute("dir", meta?.rtl ? "rtl" : "ltr")
      }
    }
  }, [language])

  const t = useCallback(
    (key: string): string => {
      try {
        if (localeUsesAiTranslation(language)) {
          const ai = aiFlat[key]
          if (typeof ai === "string" && ai.length > 0) {
            return ai
          }
        }

        const keys = key.split(".")
        let value: any = translations[language as keyof typeof translations]

        if (language === "en") {
          value = translations.en
        } else if (localeUsesAiTranslation(language)) {
          value = translations.en
        } else if (!value) {
          value = translations.en
        }

        for (const k of keys) {
          if (value && typeof value === "object" && k in value) {
            value = value[k]
          } else {
            let fallback: any = translations.en
            for (const fk of keys) {
              if (fallback && typeof fallback === "object" && fk in fallback) {
                fallback = fallback[fk]
              } else {
                return key
              }
            }
            return typeof fallback === "string" ? fallback : key
          }
        }

        if (typeof value === "string") {
          return value
        }
        return key
      } catch {
        return key
      }
    },
    [language, aiFlat],
  )

  const value = React.useMemo(
    () => ({ language, setLanguage, t, aiTranslationPending }),
    [language, setLanguage, t, aiTranslationPending],
  )

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (context === undefined) {
    throw new Error("useLanguage must be used within a LanguageProvider")
  }
  return context
}
