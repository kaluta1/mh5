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

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  aiTranslationPending: boolean
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

const SUPPORTED_LANGUAGES = LANGUAGE_CODES as readonly Language[]
type TranslationsMap = Record<string, any>

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en")
  const [translationsBundle, setTranslationsBundle] = useState<TranslationsMap | null>(null)
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
    let active = true
    import("@/lib/translations")
      .then((mod) => {
        if (active) setTranslationsBundle(mod.translations)
      })
      .catch(() => {
        if (active) setTranslationsBundle(null)
      })

    return () => {
      active = false
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
        if (!translationsBundle) return ""
        const keys = key.split(".")
        let value: any = translationsBundle[language]

        if (!value || language === "en") {
          value = translationsBundle.en
        }

        for (const k of keys) {
          if (value && typeof value === "object" && k in value) {
            value = value[k]
          } else {
            let fallback: any = translationsBundle.en
            for (const fk of keys) {
              if (fallback && typeof fallback === "object" && fk in fallback) {
                fallback = fallback[fk]
              } else {
                return ""
              }
            }
            return typeof fallback === "string" ? fallback : ""
          }
        }

        if (typeof value === "string") {
          return value
        }
        return ""
      } catch {
        return ""
      }
    },
    [language, translationsBundle],
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
