'use client'

import { useState } from 'react'
import { Search } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'
import { SearchDialog } from './search-dialog'

export function SearchBar() {
  const { t } = useLanguage()
  const router = useRouter()
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  const handleSearchClick = () => {
    setIsDialogOpen(true)
  }

  return (
    <>
      <button
        onClick={handleSearchClick}
        className="hidden md:flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition text-gray-600 dark:text-gray-400 text-sm"
      >
        <Search className="w-4 h-4" />
        <span>{t('dashboard.search.placeholder') || 'Search...'}</span>
      </button>

      <SearchDialog isOpen={isDialogOpen} onClose={() => setIsDialogOpen(false)} />
    </>
  )
}
