'use client'

import * as React from 'react'
import { useState } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { ContestResponse } from '@/services/contest-service'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Heart } from 'lucide-react'

interface ContestInfoDialogProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  contest: ContestResponse
  participantsCount: number
}

function DescriptionWithDialog({ description, maxLength = 200 }: { description: string; maxLength?: number }) {
  const [showDialog, setShowDialog] = useState(false)
  const { t, language } = useLanguage()
  const shouldTruncate = description && description.length > maxLength
  const truncatedDescription = shouldTruncate ? description.substring(0, maxLength) + '...' : description

  if (!shouldTruncate) {
    return (
      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
        {description}
      </p>
    )
  }

  return (
    <>
      <p 
        className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed cursor-pointer hover:text-myhigh5-primary dark:hover:text-myhigh5-secondary transition-colors"
        onClick={() => setShowDialog(true)}
      >
        {truncatedDescription}
      </p>
      
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {language === 'fr' ? 'Description complète' : language === 'es' ? 'Descripción completa' : language === 'de' ? 'Vollständige Beschreibung' : 'Full Description'}
            </DialogTitle>
          </DialogHeader>
          <div className="mt-4">
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
              {description}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export function ContestInfoDialog({
  isOpen,
  onOpenChange,
  contest,
  participantsCount
}: ContestInfoDialogProps) {
  const { t } = useLanguage()

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'country':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      case 'continental':
        return 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
      case 'regional':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
      default:
        return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'country':
        return t('dashboard.contests.country')
      case 'continental':
        return t('dashboard.contests.continental')
      case 'regional':
        return t('dashboard.contests.regional')
      default:
        return status
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">
            {t('dashboard.contests.view_details')}
          </DialogTitle>
          <DialogDescription>
            {contest.name}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Contest Description */}
          <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2">
              <span className="text-lg">📖</span> Description
            </h3>
            <DescriptionWithDialog 
              description={contest.description || t('dashboard.contests.no_description')}
              maxLength={200}
            />
          </div>

          {/* Badges */}
          <div className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-900 rounded-xl p-5 border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3 flex items-center gap-2">
              <span className="text-lg">🏷️</span> Informations
            </h3>
            <div className="flex flex-wrap gap-2">
              <Badge className={`${getStatusColor(contest.level)} border-0 text-xs font-semibold px-3 py-1`}>
                {getStatusLabel(contest.level)}
              </Badge>
              <Badge
                className={`${
                  contest.is_submission_open
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                    : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                } border-0 text-xs font-semibold px-3 py-1`}
              >
                {contest.is_submission_open ? t('dashboard.contests.open') : t('dashboard.contests.closed')}
              </Badge>
            </div>
          </div>

          {/* Stats */}
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 rounded-xl p-5 border border-blue-200 dark:border-blue-800">
            <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
              <span className="text-lg">📊</span> Statistiques
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('dashboard.contests.contestants')}</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{participantsCount}</p>
              </div>
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('dashboard.contests.likes')}</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-1">
                  <Heart className="w-5 h-5 text-red-500" />
                  0
                </p>
              </div>
            </div>
          </div>

          {/* Submission Period */}
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 rounded-xl p-5 border border-green-200 dark:border-green-800">
            <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
              <span className="text-lg">📝</span> {t('dashboard.contests.submission')}
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.start')}</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  {new Date(contest.submission_start_date).toLocaleDateString('fr-FR', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                  })}
                </p>
              </div>
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.end')}</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  {new Date(contest.submission_end_date).toLocaleDateString('fr-FR', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                  })}
                </p>
              </div>
            </div>
          </div>

          {/* Voting Period */}
          <div className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-950/30 dark:to-pink-950/30 rounded-xl p-5 border border-purple-200 dark:border-purple-800">
            <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
              <span className="text-lg">🗳️</span> {t('dashboard.contests.voting')}
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.start')}</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  {new Date(contest.voting_start_date).toLocaleDateString('fr-FR', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                  })}
                </p>
              </div>
              <div className="bg-white/60 dark:bg-gray-800/60 rounded-lg p-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('dashboard.contests.end')}</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  {new Date(contest.voting_end_date).toLocaleDateString('fr-FR', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric'
                  })}
                </p>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

