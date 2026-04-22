"use client"

import * as React from "react"
import { Smartphone, Download, QrCode, Apple, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useLanguage } from "@/contexts/language-context"

export function DownloadApp() {
  const { t } = useLanguage()

  return (
    <section id="download-app" className="py-20 md:py-24 lg:py-32 relative overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-myhigh5-primary via-myhigh5-secondary to-myhigh5-primary/80" />
      
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-0 left-0 w-96 h-96 bg-white/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-white/10 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white/5 rounded-full blur-3xl" />
        
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff12_1px,transparent_1px),linear-gradient(to_bottom,#ffffff12_1px,transparent_1px)] bg-[size:24px_24px]" />
      </div>

      <div className="container px-4 md:px-6 relative z-10">
        <div className="max-w-6xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            {/* Left Column - Content */}
            <div className="text-center lg:text-left text-white">
              <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full px-4 py-2 text-sm font-semibold mb-6">
                <Smartphone className="w-4 h-4" />
                <span>{t('landing.download_app.badge')}</span>
              </div>
              
              <h2 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 leading-tight">
                {t('landing.download_app.title')}
              </h2>
              
              <p className="text-lg md:text-xl opacity-90 mb-8 leading-relaxed max-w-xl mx-auto lg:mx-0">
                {t('landing.download_app.subtitle')}
              </p>

              {/* Download Buttons */}
              <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start mb-8">
                <Button
                  size="lg"
                  className="group bg-white text-myhigh5-primary hover:bg-gray-100 font-bold px-8 py-6 rounded-xl shadow-xl hover:shadow-2xl transition-all duration-300 hover:-translate-y-1 hover:scale-105"
                  onClick={() => {
                    // Télécharger l'APK depuis le dossier public
                    const link = document.createElement('a')
                    link.href = '/app-release.apk'
                    link.download = 'myhigh5-app.apk'
                    document.body.appendChild(link)
                    link.click()
                    document.body.removeChild(link)
                  }}
                >
                  <Apple className="w-6 h-6 mr-3" />
                  <div className="text-left">
                    <div className="text-xs opacity-70">{t('landing.download_app.download_on')}</div>
                    <div className="text-lg font-bold">{t('landing.download_app.app_store')}</div>
                  </div>
                </Button>
                
                <Button
                  size="lg"
                  variant="outline"
                  className="group bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white hover:bg-white/20 font-bold px-8 py-6 rounded-xl transition-all duration-300 hover:-translate-y-1 hover:scale-105"
                  onClick={() => {
                    // Télécharger l'APK depuis le dossier public
                    const link = document.createElement('a')
                    link.href = '/app-release.apk'
                    link.download = 'myhigh5-app.apk'
                    document.body.appendChild(link)
                    link.click()
                    document.body.removeChild(link)
                  }}
                >
                  <Play className="w-6 h-6 mr-3" />
                  <div className="text-left">
                    <div className="text-xs opacity-70">{t('landing.download_app.available_on')}</div>
                    <div className="text-lg font-bold">{t('landing.download_app.google_play')}</div>
                  </div>
                </Button>
              </div>

              {/* Features */}
              <div className="grid grid-cols-2 gap-4 max-w-md mx-auto lg:mx-0">
                <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20">
                  <div className="text-2xl font-bold mb-1">24/7</div>
                  <div className="text-sm opacity-90">{t('landing.download_app.access_24_7')}</div>
                </div>
                <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20">
                  <div className="text-2xl font-bold mb-1">100%</div>
                  <div className="text-sm opacity-90">{t('landing.download_app.free')}</div>
                </div>
              </div>
            </div>

            {/* Right Column - Phone Mockup / QR Code */}
            <div className="flex items-center justify-center">
              <div className="relative">
                {/* Phone mockup */}
                <div className="relative w-64 h-[500px] mx-auto">
                  <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-white/10 backdrop-blur-xl rounded-[3rem] border-8 border-white/30 shadow-2xl">
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 w-32 h-6 bg-black/30 rounded-full" />
                    <div className="absolute inset-x-4 top-16 bottom-4 bg-white/10 rounded-3xl flex items-center justify-center">
                      <div className="text-center space-y-4 p-8">
                        <div className="w-32 h-32 mx-auto bg-white/20 rounded-2xl flex items-center justify-center">
                          <QrCode className="w-20 h-20 text-white" />
                        </div>
                        <div className="text-white text-sm font-semibold">
                          {t('landing.download_app.scan_qr')}
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Glow effect */}
                  <div className="absolute inset-0 bg-gradient-to-br from-white/20 to-transparent rounded-[3rem] blur-2xl -z-10" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

