import { Metadata } from "next"
import { createMetadata } from "../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

async function getFeaturedContestImage(): Promise<string | undefined> {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/contests?limit=1&skip=0`, {
      next: { revalidate: 3600 } // Cache pour 1 heure
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data && data.length > 0) {
        const contest = data[0]
        // Utiliser image_url ou cover_image_url
        const imageUrl = contest.image_url || contest.cover_image_url
        if (imageUrl) {
          // Si c'est une URL relative, construire l'URL complète
          if (imageUrl.startsWith('/')) {
            return `${apiUrl}${imageUrl}`
          } else if (imageUrl.startsWith('http')) {
            return imageUrl
          } else {
            return `${apiUrl}/${imageUrl}`
          }
        }
      }
    }
  } catch (error) {
    console.error('Error fetching contest image for metadata:', error)
  }
  return undefined
}

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
  
  // Récupérer l'image d'un contest pour le thumbnail
  const contestImage = await getFeaturedContestImage()
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
  const defaultImage = `${appUrl}/thumbnails.png`
  const ogImage = contestImage || defaultImage

  return createMetadata({
    title: translations.pages.contests.title,
    description: englishTranslations.pages.contests.description, // Description en anglais pour les partages
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

