"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Globe, Loader2 } from "lucide-react"
import { useLanguage } from "@/contexts/language-context"
import { languages, Language } from "@/lib/translations"

export function LanguageSelector() {
  const { language, setLanguage, aiTranslationPending } = useLanguage()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2">
          {aiTranslationPending ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" aria-hidden />
          ) : (
            <Globe className="h-4 w-4" />
          )}
          <span className="hidden sm:inline">{languages[language].flag}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[min(24rem,70vh)] overflow-y-auto">
        {Object.entries(languages).map(([code, { name, flag }]) => (
          <DropdownMenuItem
            key={code}
            onClick={() => setLanguage(code as Language)}
            className={`gap-2 ${language === code ? 'bg-accent' : ''}`}
          >
            <span>{flag}</span>
            <span>{name}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
