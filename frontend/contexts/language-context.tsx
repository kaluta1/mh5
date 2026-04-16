"use client"

import React, { createContext, useContext, useState, useEffect } from 'react'
import { Language, languages, translations, TranslationKeys } from '@/lib/translations'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

const SUPPORTED_LANGUAGES = Object.keys(languages) as Language[]

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // Always default to English - never use browser language or any other default
  const [language, setLanguage] = useState<Language>('en')

  // Load saved language from localStorage on mount ONLY if user explicitly set it
  // Default is always English
  useEffect(() => {
    const savedLanguage = localStorage.getItem('myhigh5-language') as Language
    // Only use saved language if it's explicitly set and valid
    // Default to English if no preference or invalid value
    if (savedLanguage && SUPPORTED_LANGUAGES.includes(savedLanguage)) {
      setLanguage(savedLanguage)
    } else {
      // Ensure English is set and saved if no preference exists
      setLanguage('en')
      localStorage.setItem('myhigh5-language', 'en')
    }
  }, [])

  // Save language to localStorage and apply lang/dir attributes on <html> when it changes.
  // The `dir` attribute is needed for Arabic so the layout flips RTL.
  useEffect(() => {
    localStorage.setItem('myhigh5-language', language)
    if (typeof document !== 'undefined') {
      const meta = languages[language]
      const html = document.documentElement
      if (html) {
        html.setAttribute('lang', language)
        html.setAttribute('dir', meta?.rtl ? 'rtl' : 'ltr')
      }
    }
  }, [language])

  // Translation function with nested key support (e.g., "hero.title")
  const t = React.useCallback((key: string): string => {
    try {
      const keys = key.split('.')
      let value: any = translations[language]

      if (!value) {
        value = translations.en
      }

      for (const k of keys) {
        if (value && typeof value === 'object' && k in value) {
          value = value[k]
        } else {
          // Fallback to English if key not found
          let fallback: any = translations.en
          for (const fk of keys) {
            if (fallback && typeof fallback === 'object' && fk in fallback) {
              fallback = fallback[fk]
            } else {
              return key // Return key if not found in any language
            }
          }
          return typeof fallback === 'string' ? fallback : key
        }
      }

      // Ensure we always return a string, never an object
      if (typeof value === 'string') {
        return value
      } else {
        return key
      }
    } catch (error) {
      return key
    }
  }, [language])

  const value = React.useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t])

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider')
  }
  return context
}
