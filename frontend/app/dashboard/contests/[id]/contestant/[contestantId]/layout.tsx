import { Metadata } from "next"
import { createMetadata } from "../../../../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function generateMetadata({
  params,
}: {
  params: { id: string; contestantId: string }
}): Promise<Metadata> {
  // Détecter la langue
  const headersList = headers()
  const lang = detectLanguageFromHeaders(headersList)
  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux
  const englishTranslations = getMetadataTranslations('en')

  try {
    // Appel direct à l'API backend pour récupérer les données du contestant
    const contestantResponse = await fetch(`${apiUrl}/api/v1/contestants/${params.contestantId}`, {
      next: { revalidate: 3600 }, // Cache pendant 1 heure
    })
    
    if (!contestantResponse.ok) {
      throw new Error("Contestant not found")
    }
    
    const contestant = await contestantResponse.json()
    
    if (!contestant) {
      return createMetadata({
        title: `${englishTranslations.pages.contests.title.split(' - ')[0]} - ${englishTranslations.siteName}`,
        description: `Discover this participant on ${englishTranslations.siteName}`,
        url: `/dashboard/contests/${params.id}/contestant/${params.contestantId}`,
        language: lang,
      })
    }

    // Récupérer les informations du concours
    let contestImage = `${appUrl}/thumbnails.png`
    try {
      const contestResponse = await fetch(`${apiUrl}/api/v1/contests/${params.id}`, {
        next: { revalidate: 3600 },
      })
      if (contestResponse.ok) {
        const contest = await contestResponse.json()
        contestImage = contest.cover_image_url || contest.image_url || contestImage
        // S'assurer que l'image est une URL absolue
        if (!contestImage.startsWith('http')) {
          contestImage = contestImage.startsWith('/') ? `${appUrl}${contestImage}` : `${appUrl}/${contestImage}`
        }
      }
    } catch (error) {
      console.error("Error loading contest:", error)
    }

    // Utiliser le nom du participant mais avec une description en anglais
    const title = contestant.title || `${contestant.author_name || 'Participant'} - ${englishTranslations.siteName}`
    const description = contestant.description 
      ? contestant.description 
      : `Discover ${contestant.author_name || 'this participant'} on ${englishTranslations.siteName}. Vote and support!`
    
    // Extraire l'image depuis image_media_ids
    // Par défaut, utiliser l'image du concours (si le contestant n'a pas de photo)
    let image = contestImage
    
    // Vérifier si le contestant a des images
    if (contestant.image_media_ids) {
      try {
        const imageIds = typeof contestant.image_media_ids === 'string' 
          ? JSON.parse(contestant.image_media_ids) 
          : contestant.image_media_ids
        
        if (Array.isArray(imageIds) && imageIds.length > 0) {
          // Le contestant a des images, utiliser la première URL directement
          const firstImageUrl = imageIds[0]
          if (firstImageUrl && typeof firstImageUrl === 'string') {
            image = firstImageUrl
          }
        }
        // Si pas d'images ou tableau vide, image reste = contestImage (image du concours)
      } catch (error) {
        console.error("Error parsing image_media_ids:", error)
        // En cas d'erreur de parsing, utiliser l'image du concours
        image = contestImage
      }
    }
    // Si pas d'image_media_ids, image reste = contestImage (image du concours)
    
    // S'assurer que l'image est une URL absolue
    if (!image.startsWith('http')) {
      image = image.startsWith('/') ? `${appUrl}${image}` : `${appUrl}/${image}`
    }

    return createMetadata({
      title, // Titre avec nom du participant
      description, // Description en anglais
      image,
      url: `/dashboard/contests/${params.id}/contestant/${params.contestantId}`,
      type: "profile",
      language: lang,
    })
  } catch (error) {
    console.error("Error generating metadata for contestant:", error)
    return createMetadata({
      title: `${englishTranslations.pages.contests.title.split(' - ')[0]} - ${englishTranslations.siteName}`,
      description: `Discover this participant on ${englishTranslations.siteName}`,
      url: `/dashboard/contests/${params.id}/contestant/${params.contestantId}`,
      language: lang,
    })
  }
}

export default function ContestantDetailLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
