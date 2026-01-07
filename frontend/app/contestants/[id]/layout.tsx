import { Metadata } from "next"
import { createMetadata } from "../../metadata"
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
    // Appel direct à l'API backend pour récupérer les données du contestant
    const response = await fetch(`${apiUrl}/api/v1/contestants/${params.id}`, {
      next: { revalidate: 3600 }, // Cache pendant 1 heure
    })
    
    if (!response.ok) {
      throw new Error("Contestant not found")
    }
    
    const contestant = await response.json()
    
    if (!contestant) {
      return createMetadata({
        title: `${translations.pages.contests.title.split(' - ')[0]} - ${translations.siteName}`,
        description: `Découvrez ce participant sur ${translations.siteName}`,
        url: `/contestants/${params.id}`,
        language: lang,
      })
    }

    const title = contestant.title || `${contestant.author_name || 'Participant'} - ${translations.siteName}`
    const description = contestant.description || `Découvrez ${contestant.author_name || 'ce participant'} sur ${translations.siteName}. Votez et soutenez !`
    
    // Extraire l'image depuis image_media_ids ou utiliser l'avatar
    let image = contestant.author_avatar_url || `${appUrl}/thumbnails.png`
    if (contestant.image_media_ids) {
      try {
        const imageIds = typeof contestant.image_media_ids === 'string' 
          ? JSON.parse(contestant.image_media_ids) 
          : contestant.image_media_ids
        if (Array.isArray(imageIds) && imageIds.length > 0) {
          image = typeof imageIds[0] === 'string' ? imageIds[0] : contestant.author_avatar_url || `${appUrl}/thumbnails.png`
        }
      } catch {
        // Si l'image n'est pas un JSON valide, utiliser l'avatar
      }
    }

    return createMetadata({
      title,
      description,
      image,
      url: `/contestants/${params.id}`,
      type: "profile",
      language: lang,
    })
  } catch (error) {
    console.error("Error generating metadata for contestant:", error)
    return createMetadata({
      title: `${translations.pages.contests.title.split(' - ')[0]} - ${translations.siteName}`,
      description: `Découvrez ce participant sur ${translations.siteName}`,
      url: `/contestants/${params.id}`,
      language: lang,
    })
  }
}

export default function ContestantLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
