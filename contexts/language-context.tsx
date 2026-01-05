"use client"

import React, { createContext, useContext, useState, useEffect } from 'react'
import { Language, translations, TranslationKeys } from '@/lib/translations'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Language>('en')

  // Load saved language from localStorage on mount
  useEffect(() => {
    const savedLanguage = localStorage.getItem('myhigh5-language') as Language
    if (savedLanguage && ['en', 'fr', 'es', 'de'].includes(savedLanguage)) {
      setLanguage(savedLanguage)
    }
  }, [])

  // Save language to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('myhigh5-language', language)
  }, [language])

  // Translation function with nested key support (e.g., "hero.title")
  const t = (key: string): string => {
    const keys = key.split('.')
    let value: any = translations[language]
    
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
        return fallback
      }
    }
    
    // Ensure we always return a string, never an object
    if (typeof value === 'string') {
      return value
    } else if (typeof value === 'object' && value !== null) {
      console.warn(`Translation key "${key}" returned an object instead of string:`, value)
      return key // Return the key as fallback
    } else {
      return key
    }
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
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
