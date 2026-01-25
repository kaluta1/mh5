"use client"

import Image from "next/image"
import { maintenanceTranslations } from "@/lib/translations"
import { useLanguage } from "@/contexts/language-context"

export default function MaintenancePage() {
    const { language } = useLanguage()
    const t = maintenanceTranslations[language]?.maintenance || maintenanceTranslations['en'].maintenance

    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-background text-foreground p-4">
            <div className="max-w-2xl w-full text-center space-y-8">
                <div className="relative w-full aspect-video rounded-xl overflow-hidden shadow-2xl">
                    <Image
                        src="/thumbnails.png"
                        alt="MyHigh5"
                        fill
                        className="object-cover"
                        priority
                    />
                </div>

                <div className="space-y-4">
                    <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-primary to-purple-500 bg-clip-text text-transparent">
                        {t.title}
                    </h1>

                    <p className="text-xl text-muted-foreground leading-relaxed">
                        {t.message}
                    </p>

                    <div className="pt-8">
                        <div className="inline-flex items-center justify-center px-6 py-2 rounded-full bg-primary/10 text-primary font-medium">
                            {t.backSoon}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
