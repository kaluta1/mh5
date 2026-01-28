import { Metadata } from "next"
import { createMetadata } from "../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const defaultImage = `${appUrl}/thumbnails.png`

export async function generateMetadata(): Promise<Metadata> {
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

  // Utiliser directement l'image par défaut (pas d'appel API bloquant)
  const ogImage = defaultImage

  // Utiliser le titre et la description en anglais pour les partages
  const englishTitle = englishTranslations.pages.contests.title || 'Contests - High5'
  const englishDescription = englishTranslations.pages.contests.description || 'Join exciting competitions from local to global level. Participate, nominate, or vote in exciting competitions that progress from the local level to the global level.'

  return createMetadata({
    title: englishTitle, // Titre en anglais pour les partages
    description: englishDescription, // Description en anglais pour les partages
    url: "/contests",
    image: ogImage,
    language: lang,
  })
}

export default function ContestsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
