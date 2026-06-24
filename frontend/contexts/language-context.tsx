"use client"

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react"
import { type Language, LANGUAGE_CODES, languages } from "@/lib/locale-registry"
import { LANGUAGE_PREFERENCE_KEY, setLanguagePreferenceClient } from "@/lib/language-cookie"
import {
  ENGLISH_TRANSLATIONS,
  loadTranslations,
  lookupTranslation,
} from "@/lib/translations-loader"

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  aiTranslationPending: boolean
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

const SUPPORTED_LANGUAGES = LANGUAGE_CODES as readonly Language[]
type TranslationsMap = Record<string, any>

const LANG_DEFAULT_EN_MIGRATION = 'myhigh5-default-lang-en-v1'

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // English is bundled synchronously so labels never render blank on first paint.
  const [language, setLanguageState] = useState<Language>("en")
  const [translationsBundle, setTranslationsBundle] =
    useState<TranslationsMap>(ENGLISH_TRANSLATIONS)
  const [aiTranslationPending, setAiTranslationPending] = useState(false)

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang)
  }, [])

  /** Load saved language before paint so the persist effect does not clobber localStorage with a stray `en`. */
  useLayoutEffect(() => {
    if (!localStorage.getItem(LANG_DEFAULT_EN_MIGRATION)) {
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, 'en')
      localStorage.setItem(LANG_DEFAULT_EN_MIGRATION, '1')
      setLanguageState('en')
      return
    }
    const savedLanguage = localStorage.getItem(LANGUAGE_PREFERENCE_KEY) as Language
    if (savedLanguage && SUPPORTED_LANGUAGES.includes(savedLanguage)) {
      setLanguageState(savedLanguage)
    } else {
      setLanguageState("en")
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, "en")
    }
  }, [])

  useEffect(() => {
    let active = true
    setAiTranslationPending(language !== "en")

    loadTranslations(language)
      .then((bundle) => {
        if (active) {
          setTranslationsBundle(bundle)
          setAiTranslationPending(false)
        }
      })
      .catch(() => {
        // Never clear labels — keep English (or the last good bundle).
        if (active) {
          setTranslationsBundle(ENGLISH_TRANSLATIONS)
          setAiTranslationPending(false)
        }
      })

    return () => {
      active = false
    }
  }, [language])

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
        const primary = lookupTranslation(translationsBundle, key)
        if (primary) return primary
        return lookupTranslation(ENGLISH_TRANSLATIONS, key)
      } catch {
        return lookupTranslation(ENGLISH_TRANSLATIONS, key)
      }
    },
    [translationsBundle],
  )

  const value = useMemo(
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
