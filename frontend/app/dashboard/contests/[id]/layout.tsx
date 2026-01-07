import { Metadata } from "next"
import { createMetadata } from "../../../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function generateMetadata({
  params,
}: {
  params: { id: string }
}): Promise<Metadata> {
  // Détecter la langue
  const headersList = headers()
  const lang = detectLanguageFromHeaders(headersList)
  const translations = getMetadataTranslations(lang)

  try {
    // Appel direct à l'API backend pour récupérer les données du concours
    const response = await fetch(`${apiUrl}/api/v1/contests/${params.id}`, {
      next: { revalidate: 3600 }, // Cache pendant 1 heure
    })
    
    if (!response.ok) {
      throw new Error("Contest not found")
    }
    
    const contest = await response.json()
    
    if (!contest) {
      return createMetadata({
        title: translations.pages.contests.title,
        description: `Découvrez ce concours sur ${translations.siteName}`,
        url: `/dashboard/contests/${params.id}`,
        language: lang,
      })
    }

    const title = `${contest.name || translations.pages.contests.title.split(' - ')[0]} - ${translations.siteName}`
    const description = contest.description || `Participez au concours ${contest.name || 'ce concours'} sur ${translations.siteName}. Votez pour vos favoris et gagnez des prix !`
    const image = contest.cover_image_url || contest.image_url || `${appUrl}/thumbnails.png`

    return createMetadata({
      title,
      description,
      image,
      url: `/dashboard/contests/${params.id}`,
      type: "article",
      language: lang,
    })
  } catch (error) {
    console.error("Error generating metadata for contest:", error)
    return createMetadata({
      title: translations.pages.contests.title,
      description: `Découvrez ce concours sur ${translations.siteName}`,
      url: `/dashboard/contests/${params.id}`,
      language: lang,
    })
  }
}

export default function ContestLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

