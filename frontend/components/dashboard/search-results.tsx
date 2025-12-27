'use client'

import { Badge } from '@/components/ui/badge'
import { useLanguage } from '@/contexts/language-context'

interface SearchResult {
  id: string
  title: string
  category: 'contest' | 'contestant' | 'club' | 'product'
  description?: string

  // Champs enrichis (alignés avec le service de recherche)
  full_name?: string
  city?: string
  country?: string
  continent?: string
  level?: string
  location_name?: string
}

interface SearchResultsProps {
  results: SearchResult[]
  isLoading: boolean
  searchTerm: string
  onResultClick?: (result: SearchResult) => void
}

export function SearchResults({ results, isLoading, searchTerm, onResultClick }: SearchResultsProps) {
  const { t } = useLanguage()

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'contest':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'contestant':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'club':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      case 'product':
        return 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300'
      default:
        return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
    }
  }

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'contest':
        return '🏆 ' + (t('dashboard.search.contest') || 'Contest')
      case 'contestant':
        return '👤 ' + (t('dashboard.search.contestant') || 'Contestant')
      case 'club':
        return '👥 ' + (t('dashboard.search.club') || 'Club')
      case 'product':
        return '📦 ' + (t('dashboard.search.product') || 'Product')
      default:
        return category
    }
  }

  // Group results by category
  const groupedResults = results.reduce((acc, result) => {
    if (!acc[result.category]) {
      acc[result.category] = []
    }
    acc[result.category].push(result)
    return acc
  }, {} as Record<string, SearchResult[]>)

  if (isLoading) {
    return (
      <div className="text-center py-12">
        <div className="inline-block">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-myhigh5-primary"></div>
        </div>
        <p className="text-gray-500 dark:text-gray-400 mt-4">{t('common.loading') || 'Loading...'}</p>
      </div>
    )
  }

  if (searchTerm && results.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        {t('dashboard.search.no_results')}
      </div>
    )
  }

  if (!searchTerm) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        {t('dashboard.search.start_typing')}
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {Object.entries(groupedResults).map(([category, categoryResults]) => (
        <div key={category} className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
            {getCategoryLabel(category)}
            <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
              ({categoryResults.length})
            </span>
          </h2>
          <div className="grid gap-3">
            {categoryResults.map((result) => (
              <button
                key={`${result.category}-${result.id}`}
                onClick={() => onResultClick?.(result)}
                className="p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg hover:border-myhigh5-primary dark:hover:border-myhigh5-blue-400 transition text-left group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    {/* Titre principal */}
                    <p className="font-semibold text-gray-900 dark:text-white group-hover:text-myhigh5-primary dark:group-hover:text-myhigh5-blue-400 transition truncate">
                      {result.title}
                    </p>

                    {/* Sous-ligne spécifique à la catégorie */}
                    {result.category === 'contestant' && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
                        {/* Nom complet si présent */}
                        {result.full_name && <span>{result.full_name}</span>}
                        {result.full_name && (result.city || result.country || result.continent) && (
                          <span> · </span>
                        )}
                        {/* Localisation ville, pays, continent */}
                        {(result.city || result.country || result.continent) && (
                          <span>
                            {[result.city, result.country, result.continent]
                              .filter(Boolean)
                              .join(', ')}
                          </span>
                        )}
                      </p>
                    )}

                    {result.category === 'contest' && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
                        {/* Niveau du concours et localisation simple */}
                        {result.level && (
                          <span className="uppercase tracking-wide mr-1">
                            {result.level}
                          </span>
                        )}
                        {result.location_name && (
                          <span>· {result.location_name}</span>
                        )}
                      </p>
                    )}

                    {/* Description générique en bas si disponible */}
                    {result.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                        {result.description}
                      </p>
                    )}
                  </div>
                  <Badge className={`${getCategoryColor(result.category)} border-0 text-xs flex-shrink-0`}>
                    {getCategoryLabel(result.category)}
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
