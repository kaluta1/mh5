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

// Générer les métadonnées selon la langue détectée
function generateMetadata(): Metadata {
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
          url: defaultImage,
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
      images: [defaultImage],
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
