"use client"

import { useEffect, useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { SearchSkeleton } from '@/components/ui/skeleton'
import { SearchResults } from '@/components/dashboard/search-results'
import { Button } from '@/components/ui/button'
import api from '@/lib/api'

interface SearchResult {
  id: string
  title: string
  category: 'contest' | 'contestant' | 'club' | 'product'
  description?: string
  image?: string
}

interface SearchHistoryItem {
  id: number
  term: string
  created_at: string
}

export default function SearchPage() {
  const { t } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([])

  // Charger l'historique depuis le backend
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await api.get('/api/v1/search-history', {
          params: { limit: 20 },
        })

        const raw: SearchHistoryItem[] = response.data || []

        // Sécurité côté frontend : dédoublonner par terme normalisé
        const seen = new Set<string>()
        const unique: SearchHistoryItem[] = []

        for (const item of raw) {
          const key = item.term.replace(/\s+/g, ' ').trim().toLowerCase()
          if (!key || seen.has(key)) continue
          seen.add(key)
          unique.push(item)
        }

        setSearchHistory(unique)
      } catch (err) {
        console.error('Error loading search history:', err)
      }
    }

    if (isAuthenticated && user) {
      fetchHistory()
    }
  }, [isAuthenticated, user])

  if (isLoading) {
    return <SearchSkeleton />
  }

  if (!isAuthenticated || !user) {
    return null
  }

  const runSearch = async (term: string) => {
    const normalizedTerm = term.replace(/\s+/g, ' ').trim()

    if (!normalizedTerm) {
      setResults([])
      return
    }

    setIsSearching(true)
    try {
      const { searchService } = await import('@/services/search-service')
      
      // Utiliser searchAll pour une meilleure performance avec les résultats catégorisés
      const response = await searchService.searchAll(normalizedTerm, 15)
      
      // Combiner tous les résultats
      const allResults = [
        ...response.contest,
        ...response.contestant,
        ...response.club
      ]
      
      setResults(allResults)

      // Enregistrer la recherche dans l'historique backend (même si aucun résultat, si tu préfères tu peux garder la condition)
      try {
        const res = await api.post('/api/v1/search-history', { term: normalizedTerm })
        const saved = res.data as SearchHistoryItem
        // Mettre à jour la liste locale (en tête)
        setSearchHistory((prev) => {
          const normalizedLower = normalizedTerm.toLowerCase()
          const existing = prev.filter(
            (h) => h.term.replace(/\s+/g, ' ').trim().toLowerCase() !== normalizedLower
          )
          return [saved, ...existing].slice(0, 20)
        })
      } catch (err) {
        console.error('Error saving search history:', err)
      }
    } catch (error) {
      console.error('Search error:', error)
      setResults([])
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearchClick = () => {
    runSearch(searchTerm)
  }

  const handleHistoryClick = (term: string) => {
    setSearchTerm(term)
    runSearch(term)
  }

  const handleResultClick = (result: SearchResult) => {
    // Navigate to the appropriate page based on category
    switch (result.category) {
      case 'contest':
        router.push(`/dashboard/contests/${result.id}`)
        break
      case 'contestant':
        router.push(`/dashboard/contestants/${result.id}`)
        break
      case 'club':
        router.push(`/dashboard/clubs/${result.id}`)
        break
      default:
        break
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-950 dark:to-gray-900 px-4 py-6 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[2fr,1fr] gap-8">
        {/* Colonne principale */}
        <div className="space-y-8">
          {/* Header */}
          <div className="space-y-2">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
              {t('dashboard.search.title')}
            </h1>
            <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400 max-w-2xl">
              {t('dashboard.search.description')}
            </p>
          </div>

          {/* Search Input + bouton */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                placeholder={t('dashboard.search.placeholder') || 'Search...'}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleSearchClick()
                  }
                }}
                className="flex-1 px-4 py-3 sm:px-6 sm:py-4 bg-white/90 dark:bg-gray-900/60 border border-gray-200/80 dark:border-gray-800 rounded-2xl text-base sm:text-lg outline-none focus-visible:ring-2 focus-visible:ring-myhigh5-primary/80 dark:focus-visible:ring-myhigh5-blue-400 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 shadow-sm"
              />
              <Button
                type="button"
                onClick={handleSearchClick}
                disabled={isSearching}
                className="sm:px-6 sm:py-4 px-4 py-3 rounded-2xl text-sm sm:text-lg font-semibold shadow-sm flex items-center justify-center gap-2"
              >
                {isSearching ? (t('common.loading') || 'Searching...') : (t('common.search') || 'Search')}
              </Button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-500">
              ↵ {t('dashboard.search.start_typing')}
            </p>
          </div>

          {/* Results */}
          <SearchResults
            results={results}
            isLoading={isSearching}
            searchTerm={searchTerm}
            onResultClick={handleResultClick}
          />
        </div>

        {/* Sidebar historique */}
        <aside className="space-y-4 bg-white/90 dark:bg-gray-900/70 border border-gray-200/80 dark:border-gray-800 rounded-2xl p-4 h-fit shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white tracking-wide">
              {t('dashboard.search.recent_searches') || 'Recherches récentes'}
            </h2>
            {searchHistory.length > 0 && (
              <button
                type="button"
                onClick={async () => {
                  setSearchHistory([])
                  try {
                    // Pas d'endpoint de purge pour l'instant, on ne fait que nettoyer côté UI
                  } catch (err) {
                    console.error('Error clearing search history:', err)
                  }
                }}
                className="text-[11px] uppercase tracking-wide text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-300"
              >
                {t('common.clear') || 'Effacer'}
              </button>
            )}
          </div>

          {searchHistory.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-500">
              {t('dashboard.search.no_history') || 'Aucune recherche récente.'}
            </p>
          ) : (
            <ul className="space-y-1 max-h-80 overflow-y-auto text-sm">
              {searchHistory.map((item) => (
                <li key={`${item.id}-${item.term}`}>
                  <button
                    type="button"
                    onClick={() => handleHistoryClick(item.term)}
                    className="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 flex items-center justify-between gap-2"
                  >
                    <span className="truncate">{item.term}</span>
                    <span className="text-[10px] text-gray-400 dark:text-gray-500 whitespace-nowrap">
                      {new Date(item.created_at).toLocaleDateString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  )
}
