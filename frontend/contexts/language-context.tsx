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
import { Language, LANGUAGE_CODES, languages, translations } from "@/lib/translations"
import { LANGUAGE_PREFERENCE_KEY, setLanguagePreferenceClient } from "@/lib/language-cookie"

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  aiTranslationPending: boolean
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

const SUPPORTED_LANGUAGES = LANGUAGE_CODES as readonly Language[]

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en")
  const aiTranslationPending = false

  const setLanguage = useCallback(
    (lang: Language) => {
      setLanguageState(lang)
    },
    [],
  )

  /** Load saved language before paint so the persist effect does not clobber localStorage with a stray `en`. */
  useLayoutEffect(() => {
    const savedLanguage = localStorage.getItem(LANGUAGE_PREFERENCE_KEY) as Language
    if (savedLanguage && SUPPORTED_LANGUAGES.includes(savedLanguage)) {
      setLanguageState(savedLanguage)
    } else {
      setLanguageState("en")
      localStorage.setItem(LANGUAGE_PREFERENCE_KEY, "en")
    }
  }, [])

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
        const keys = key.split(".")
        let value: any = translations[language as keyof typeof translations]

        if (!value || language === "en") {
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
    [language],
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
