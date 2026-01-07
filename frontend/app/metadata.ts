/**
 * Métadonnées SEO partagées pour toutes les pages
 */
import { Metadata } from "next"
import { Language } from "@/lib/translations"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const defaultImage = `${appUrl}/thumbnails.png`

const localeMap: Record<Language, string> = {
  fr: "fr_FR",
  en: "en_US",
  es: "es_ES",
  de: "de_DE",
}

export function createMetadata({
  title,
  description,
  image,
  url,
  type = "website",
  language,
}: {
  title: string
  description: string
  image?: string
  url?: string
  type?: "website" | "article" | "profile"
  language?: Language
}): Metadata {
  // Détecter la langue si non fournie
  let lang: Language = language || 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible (côté client), utiliser la langue fournie ou défaut
    lang = language || 'en'
  }

  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux (toujours en anglais)
  const englishTranslations = getMetadataTranslations('en')
  const fullTitle = title.includes("High5") ? title : `${title} | ${translations.siteName}`
  // Titre en anglais pour les partages
  const englishTitle = title.includes("High5") ? title : `${title} | ${englishTranslations.siteName}`
  const ogImage = image || defaultImage
  const canonicalUrl = url ? `${appUrl}${url}` : appUrl
  
  // Utiliser la description en anglais pour les partages si disponible, sinon utiliser celle fournie
  // Pour les pages spécifiques, on peut passer une description en anglais
  // Sinon, on utilise une description générique en anglais
  const ogDescription = description || englishTranslations.defaultDescription

  return {
    title: fullTitle,
    description,
    openGraph: {
      title: englishTitle,
      description: ogDescription,
      url: canonicalUrl,
      siteName: englishTranslations.siteName,
      images: [
        {
          url: ogImage,
          width: 1200,
          height: 630,
          alt: englishTitle,
        },
      ],
      locale: "en_US", // Toujours en anglais pour les partages
      type,
    },
    twitter: {
      card: "summary_large_image",
      title: englishTitle,
      description: ogDescription,
      images: [ogImage],
    },
    alternates: {
      canonical: canonicalUrl,
    },
  }
}

