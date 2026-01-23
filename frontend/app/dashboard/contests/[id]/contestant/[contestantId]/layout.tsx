import { Metadata } from "next"
import { createMetadata } from "@/app/metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://myhigh5.com";
const defaultImage = `${appUrl}/thumbnails.png`

export async function generateMetadata({
  params,
}: {
  params: { id: string; contestantId: string }
}): Promise<Metadata> {
  // Détecter la langue
  let lang: import("@/lib/translations").Language = 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    lang = 'en'
  }

  // Traductions en anglais pour les partages sociaux
  const englishTranslations = getMetadataTranslations('en')

  // Utiliser des métadonnées génériques (pas d'appel API bloquant)
  const title = `Participant - ${englishTranslations.siteName}`
  const description = `Discover this participant on ${englishTranslations.siteName}. Vote and support!`

  return createMetadata({
    title,
    description,
    image: defaultImage,
    url: `/dashboard/contests/${params.id}/contestant/${params.contestantId}`,
    type: "profile",
    language: lang,
  })
}

export default function ContestantDetailLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
