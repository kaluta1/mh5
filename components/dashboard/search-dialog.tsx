'use client'

import { useState, useEffect } from 'react'
import { Search, X } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface SearchResult {
  id: string
  title: string
  category: 'contest' | 'contestant' | 'club' | 'product'
  description?: string
  image?: string
}

interface SearchDialogProps {
  isOpen: boolean
  onClose: () => void
}

export function SearchDialog({ isOpen, onClose }: SearchDialogProps) {
  const { t } = useLanguage()
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!searchTerm.trim()) {
      setResults([])
      return
    }

    setIsLoading(true)
    const performSearch = async () => {
      try {
        const { searchService } = await import('@/services/search-service')
        
        // Utiliser searchAll pour une meilleure performance
        const response = await searchService.searchAll(searchTerm, 10)
        
        // Combiner tous les résultats
        const allResults = [
          ...response.contest,
          ...response.contestant,
          ...response.club
        ]
        
        setResults(allResults)
      } catch (error) {
        console.error('Search error:', error)
        setResults([])
      } finally {
        setIsLoading(false)
      }
    }

    // Debounce search to avoid too many requests
    const timer = setTimeout(performSearch, 300)
    return () => clearTimeout(timer)
  }, [searchTerm])

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

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/50 dark:bg-black/70 flex items-start justify-center pt-20">
      <div className="w-full max-w-2xl mx-4 bg-white dark:bg-gray-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Search Input */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <Search className="w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder={t('dashboard.search.placeholder') || 'Search contests, contestants, clubs, products...'}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              autoFocus
              className="flex-1 bg-transparent text-lg outline-none text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
            />
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition"
            >
              <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="max-h-96 overflow-y-auto">
          {isLoading ? (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">
              {t('common.loading') || 'Loading...'}
            </div>
          ) : results.length === 0 && searchTerm ? (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">
              {t('dashboard.search.no_results') || 'No results found'}
            </div>
          ) : results.length === 0 ? (
            <div className="p-8 text-center text-gray-500 dark:text-gray-400">
              {t('dashboard.search.start_typing') || 'Start typing to search...'}
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {results.map((result) => (
                <button
                  key={`${result.category}-${result.id}`}
                  className="w-full p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition text-left"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="font-semibold text-gray-900 dark:text-white mb-1">
                        {result.title}
                      </p>
                      {result.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400">
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
          )}
        </div>
      </div>
    </div>
  )
}
