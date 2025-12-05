'use client'

import React from 'react'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'
import { useRouter } from 'next/navigation'

interface ContestsHeaderProps {
  searchTerm?: string
  onSearchChange?: (term: string) => void
}

export function ContestsHeader({ searchTerm, onSearchChange }: ContestsHeaderProps) {
  const { t } = useLanguage()
  const router = useRouter()

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
        {t('dashboard.contests.title')}
      </h1>
      
      {/* Search Button */}
      <Button
        onClick={() => router.push('/dashboard/search')}
        className="w-full md:w-auto flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition"
      >
        <Search className="w-5 h-5" />
        <span>{t('dashboard.search.placeholder')}</span>
      </Button>
    </div>
  )
}
