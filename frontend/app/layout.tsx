import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/hooks/use-auth"
import { LanguageProvider } from "@/contexts/language-context"
import { ToastProvider } from "@/components/ui/toast"
import { CookieConsent } from "@/components/ui/cookie-consent"
import { getMetadataTranslations, detectLanguageFromHeaders, getKeywords } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const inter = Inter({ subsets: ["latin"] })

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const defaultImage = `${appUrl}/thumbnails.png` // Image par défaut pour le partage

// Récupérer une image de contest pour le thumbnail
async function getFeaturedContestImage(): Promise<string> {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/contests?limit=1&skip=0`, {
      next: { revalidate: 3600 }, // Cache pour 1 heure
      headers: {
        'Accept': 'application/json',
      }
    })
    
    if (response.ok) {
      const data = await response.json()
      if (data && Array.isArray(data) && data.length > 0) {
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
    } else if (response.status === 404) {
      // Si l'endpoint n'existe pas, retourner l'image par défaut sans erreur
      console.warn('Contests endpoint not found, using default image')
    }
  } catch (error) {
    // Ne pas logger l'erreur en production pour éviter le spam
    if (process.env.NODE_ENV === 'development') {
      console.error('Error fetching contest image for metadata:', error)
    }
  }
  return defaultImage
}

// Générer les métadonnées selon la langue détectée
export async function generateMetadata(): Promise<Metadata> {
  let lang: import("@/lib/translations").Language = 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible, utiliser le défaut
    lang = 'en'
  }

  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux (toujours en anglais)
  const englishTranslations = getMetadataTranslations('en')
  const localeMap: Record<typeof lang, string> = {
    fr: "fr_FR",
    en: "en_US",
    es: "es_ES",
    de: "de_DE",
  }

  // Récupérer une image de contest pour le thumbnail
  const ogImage = await getFeaturedContestImage()
  
  // S'assurer que l'image est une URL absolue
  const absoluteOgImage = ogImage.startsWith('http') ? ogImage : `${appUrl}${ogImage.startsWith('/') ? ogImage : '/' + ogImage}`
  
  // Utiliser les traductions en anglais pour tous les partages sociaux
  const englishTitle = englishTranslations.pages.home.title
  const englishDescription = englishTranslations.pages.home.description || englishTranslations.defaultDescription || 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.'

  return {
    metadataBase: new URL(appUrl),
    title: {
      default: translations.pages.home.title,
      template: `%s | ${translations.siteName}`
    },
    description: translations.pages.home.description,
    keywords: getKeywords(lang),
    authors: [{ name: `${translations.siteName} Team` }],
    creator: translations.siteName,
    publisher: translations.siteName,
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        'max-video-preview': -1,
        'max-image-preview': 'large',
        'max-snippet': -1,
      },
    },
    openGraph: {
      type: "website",
      locale: "en_US", // Toujours en anglais pour les partages
      url: appUrl,
      siteName: englishTranslations.siteName,
      title: englishTitle,
      description: englishDescription,
      images: [
        {
          url: absoluteOgImage,
          width: 1200,
          height: 630,
          alt: englishTitle,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: englishTitle,
      description: englishDescription,
      images: [absoluteOgImage],
      creator: "@high5",
    },
    alternates: {
      canonical: appUrl,
    },
    icons: {
      icon: [
        { url: '/thumbnails.png', sizes: 'any' },
        { url: '/thumbnails.png', type: 'image/png' },
      ],
      apple: [
        { url: '/thumbnails.png', sizes: '180x180', type: 'image/png' },
      ],
      shortcut: '/thumbnails.png',
    },
  }
}


export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Détecter la langue pour l'attribut lang du HTML
  let htmlLang = 'en'
  try {
    const headersList = headers()
    htmlLang = detectLanguageFromHeaders(headersList)
  } catch {
    htmlLang = 'en'
  }

  return (
    <html lang={htmlLang} suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <ToastProvider>
            <LanguageProvider>
              <AuthProvider>
                {children}
                <CookieConsent />
              </AuthProvider>
            </LanguageProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
