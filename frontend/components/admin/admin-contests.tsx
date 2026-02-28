'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Trophy, Calendar } from 'lucide-react'
import { ContestList } from './contests/ContestList'
import { RoundsList } from './contests/RoundsList'
import api from '@/lib/api'
import { cacheService } from '@/lib/cache-service'

export default function AdminContests() {
  const { t } = useLanguage()
  const { addToast } = useToast()

  // Shared state for lists
  const [seasons, setSeasons] = useState<any[]>([])
  const [votingTypes, setVotingTypes] = useState<any[]>([])
  const [categories, setCategories] = useState<any[]>([])
  const [loadingShared, setLoadingShared] = useState(true)
  const [activeTab, setActiveTab] = useState('contests')

  useEffect(() => {
    fetchSharedData()
  }, [])

  const fetchSharedData = async () => {
    try {
      setLoadingShared(true)

      // Fetch Seasons
      const seasonsEndpoint = '/api/v1/admin/seasons'
      const cachedSeasons = cacheService.get<any[]>(seasonsEndpoint, {})
      if (cachedSeasons) {
        setSeasons(cachedSeasons)
      } else {
        const response = await api.get(seasonsEndpoint)
        setSeasons(response.data)
        cacheService.set(seasonsEndpoint, response.data, {}, 5 * 60 * 1000)
      }

      // Fetch Voting Types
      try {
        const vtResponse = await api.get('/api/v1/voting-types')
        if (vtResponse.data && Array.isArray(vtResponse.data)) {
          setVotingTypes(vtResponse.data)
        }
      } catch (err) {
        console.warn('Voting types fetch error', err)
      }

      // Fetch Categories
      const catEndpoint = '/api/v1/categories'
      const params = { active_only: true }
      const cachedCategories = cacheService.get<any[]>(catEndpoint, params)
      if (cachedCategories) {
        setCategories(cachedCategories)
      } else {
        try {
          const catResponse = await api.get(`${catEndpoint}/`, { params })
          const data = catResponse.data && Array.isArray(catResponse.data) ? catResponse.data : []
          setCategories(data)
          cacheService.set(catEndpoint, data, params, 5 * 60 * 1000)
        } catch (err) {
          console.warn('Categories fetch error', err)
        }
      }

    } catch (error) {
      // Silently handle timeout errors
      if (error?.code !== 'ECONNABORTED' && error?.message && !error?.message?.includes('timeout')) {
        console.warn('Error loading shared data', error)
        addToast(t('admin.common.load_error') || 'Erreur de chargement des données', 'error')
      }
    } finally {
      setLoadingShared(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex justify-between items-start gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3">
              <Trophy className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
              <h1 className="text-4xl font-bold text-white dark:text-white">
                {t('admin.contests.title') || 'Gestion des Concours'}
              </h1>
            </div>
            <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium">
              {t('admin.contests.description') || 'Gérez vos concours et les rounds associés'}
            </p>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md mb-6">
          <TabsTrigger value="contests" className="gap-2">
            <Trophy className="h-4 w-4" />
            {t('admin.contests.tab_contests') || 'Concours'}
          </TabsTrigger>
          <TabsTrigger value="rounds" className="gap-2">
            <Calendar className="h-4 w-4" />
            {t('admin.contests.tab_rounds') || 'Rounds'}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="contests">
          <ContestList seasons={seasons} votingTypes={votingTypes} categories={categories} />
        </TabsContent>

        <TabsContent value="rounds">
          <RoundsList />
        </TabsContent>
      </Tabs>
    </div>
  )
}
