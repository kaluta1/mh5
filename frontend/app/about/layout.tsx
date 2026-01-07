import { Metadata } from "next"
import { createMetadata } from "../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

function generateMetadata(): Metadata {
  let lang: import("@/lib/translations").Language = 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible (lors du build), utiliser le défaut
      lang = 'en'
  }
  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux
  const englishTranslations = getMetadataTranslations('en')

  return createMetadata({
    title: englishTranslations.pages.about.title, // Titre en anglais pour les partages
    description: englishTranslations.pages.about.description, // Description en anglais pour les partages
    url: "/about",
    language: lang,
  })
}

export const metadata: Metadata = generateMetadata()

export default function AboutLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

