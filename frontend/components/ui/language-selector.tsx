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
import { Input } from "@/components/ui/input"

export function LanguageSelector() {
  const { language, setLanguage, aiTranslationPending } = useLanguage()
  const [query, setQuery] = React.useState("")

  const languageEntries = React.useMemo(
    () => Object.entries(languages),
    [],
  )

  const filteredLanguages = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return languageEntries
    return languageEntries.filter(([code, meta]) => {
      const name = meta.name.toLowerCase()
      return code.toLowerCase().includes(q) || name.includes(q)
    })
  }, [languageEntries, query])

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
        <div className="p-2 sticky top-0 z-10 bg-popover border-b">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search language..."
            className="h-8"
          />
        </div>
        {filteredLanguages.length === 0 && (
          <div className="px-2 py-2 text-xs text-muted-foreground">
            No language found
          </div>
        )}
        {filteredLanguages.map(([code, { name, flag }]) => (
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
