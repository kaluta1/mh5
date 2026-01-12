import { Metadata } from "next"
import { createMetadata } from "@/app/metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://myhigh5.com";
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
    
    // Image de partage : toujours l'image du concours (pas la photo auteur)
    let image = contestImage
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
