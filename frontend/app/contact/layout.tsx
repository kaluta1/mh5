import { Metadata } from "next"
import { createMetadata } from "../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

function generateMetadata(): Metadata {
  let lang: import("@/lib/translations").Language = 'fr'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible (lors du build), utiliser le défaut
    lang = 'fr'
  }
  const translations = getMetadataTranslations(lang)

  return createMetadata({
    title: translations.pages.contact.title,
    description: translations.pages.contact.description,
    url: "/contact",
    language: lang,
  })
}

export const metadata: Metadata = generateMetadata()

export default function ContactLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

