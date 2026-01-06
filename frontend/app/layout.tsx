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
const defaultImage = `${appUrl}/og-image.jpg` // Image par défaut pour le partage

// Récupérer une image de contest pour le thumbnail
async function getFeaturedContestImage(): Promise<string> {
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
  return defaultImage
}

// Générer les métadonnées selon la langue détectée
async function generateMetadata(): Promise<Metadata> {
  let lang: import("@/lib/translations").Language = 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible, utiliser le défaut
    lang = 'en'
  }

  const translations = getMetadataTranslations(lang)
  const localeMap: Record<typeof lang, string> = {
    fr: "fr_FR",
    en: "en_US",
    es: "es_ES",
    de: "de_DE",
  }

  // Récupérer une image de contest pour le thumbnail
  const ogImage = await getFeaturedContestImage()

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
      locale: localeMap[lang],
      url: appUrl,
      siteName: translations.siteName,
      title: translations.pages.home.title,
      description: translations.pages.home.description,
      images: [
        {
          url: ogImage,
          width: 1200,
          height: 630,
          alt: translations.pages.home.title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: translations.pages.home.title,
      description: translations.pages.home.description,
      images: [ogImage],
      creator: "@high5",
    },
    alternates: {
      canonical: appUrl,
    },
  }
}

export const metadata = generateMetadata()

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
