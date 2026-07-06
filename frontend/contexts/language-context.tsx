"use client"

import React, {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
} from "react"
import { type Language } from "@/lib/locale-registry"
import { LANGUAGE_PREFERENCE_KEY, setLanguagePreferenceClient } from "@/lib/language-cookie"
import { ENGLISH_TRANSLATIONS, lookupTranslation } from "@/lib/translations-loader"

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  aiTranslationPending: boolean
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

type TranslationsMap = Record<string, any>

/** Bump when forcing English-only so saved fr/sw/etc. preferences reset once. */
const ENGLISH_ONLY_MIGRATION = 'myhigh5-english-only-v2'

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language] = useState<Language>("en")
  const [translationsBundle] = useState<TranslationsMap>(ENGLISH_TRANSLATIONS)

  /** Site is English-only: reset any saved locale and keep html lang=en. */
  useLayoutEffect(() => {
    if (!localStorage.getItem(ENGLISH_ONLY_MIGRATION)) {
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, 'en')
      localStorage.setItem(ENGLISH_ONLY_MIGRATION, '1')
    } else {
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, 'en')
    }
    setLanguagePreferenceClient('en')
    const html = document.documentElement
    if (html) {
      html.setAttribute('lang', 'en')
      html.setAttribute('dir', 'ltr')
    }
  }, [])

  const setLanguage = useCallback((_lang: Language) => {
    // English-only — language selector is hidden; ignore switches.
  }, [])

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
    () => ({ language, setLanguage, t, aiTranslationPending: false }),
    [language, setLanguage, t],
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
