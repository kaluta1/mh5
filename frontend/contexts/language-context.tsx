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
  // Always default to English - never use browser language or any other default
  const [language, setLanguage] = useState<Language>('en')

  // Load saved language from localStorage on mount ONLY if user explicitly set it
  // Default is always English
  useEffect(() => {
    const savedLanguage = localStorage.getItem('myhigh5-language') as Language
    // Only use saved language if it's explicitly set and valid
    // Default to English if no preference or invalid value
    if (savedLanguage && ['en', 'fr', 'es', 'de'].includes(savedLanguage)) {
      setLanguage(savedLanguage)
    } else {
      // Ensure English is set and saved if no preference exists
      setLanguage('en')
      localStorage.setItem('myhigh5-language', 'en')
    }
  }, [])

  // Save language to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('myhigh5-language', language)
  }, [language])

  // Translation function with nested key support (e.g., "hero.title")
  const t = (key: string): string => {
    try {
    const keys = key.split('.')
    let value: any = translations[language]
      
      if (!value) {
        console.warn(`Translations not found for language: ${language}, falling back to English`)
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
              // Only warn in development - translation key not found
              if (process.env.NODE_ENV === 'development') {
                console.warn(`Translation key "${key}" not found in any language`)
              }
            return key // Return key if not found in any language
            }
          }
          return typeof fallback === 'string' ? fallback : key
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
    } catch (error) {
      console.error(`Error resolving translation key "${key}":`, error)
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
