import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/hooks/use-auth"
import { LanguageProvider } from "@/contexts/language-context"
import { ToastProvider } from "@/components/ui/toast"
import { CookieConsent } from "@/components/ui/cookie-consent"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"),
  title: "MyFav - Plateforme de Concours Mondiale",
  description: "Rejoignez la plus grande communauté de concours au monde. Participez, votez et gagnez dans des compétitions de beauté, talents et bien plus encore.",
  keywords: ["concours", "beauté", "talents", "communauté", "votes", "compétition"],
  authors: [{ name: "MyFav Team" }],
  openGraph: {
    title: "MyFav - Plateforme de Concours Mondiale",
    description: "Rejoignez la plus grande communauté de concours au monde",
    type: "website",
    locale: "en_US",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
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
