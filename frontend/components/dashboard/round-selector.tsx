'use client'

import React from 'react'
import { RoundWithStats } from '@/services/contest-service'
import { useLanguage } from '@/contexts/language-context'

interface RoundSelectorProps {
    rounds: RoundWithStats[]
    selectedRoundId?: number
    onSelectRound: (roundId: number) => void
    className?: string
}

/**
 * Composant de sélection de rounds avec scroll horizontal
 * Affiche les rounds avec leur statut et nombre de participants
 */
export function RoundSelector({
    rounds,
    selectedRoundId,
    onSelectRound,
    className = ''
}: RoundSelectorProps) {
    const { t } = useLanguage()
    if (!rounds || rounds.length === 0) {
        return null
    }

    const getStatusIcon = (round: RoundWithStats): string => {
        if (round.is_completed) return '✓'
        if (round.is_submission_open) return '🔵'
        if (round.is_voting_open) return '🗳️'
        if (round.status === 'upcoming') return '○'
        return ''
    }

    const getStatusColor = (round: RoundWithStats): string => {
        if (round.is_completed) {
            return 'bg-green-500/20 text-green-400 border-green-500/50'
        }
        if (round.is_submission_open) {
            return 'bg-blue-500/20 text-blue-400 border-blue-500/50'
        }
        if (round.is_voting_open) {
            return 'bg-purple-500/20 text-purple-400 border-purple-500/50'
        }
        return 'bg-gray-700/50 text-gray-400 border-gray-600'
    }

    const getSeasonLevelLabel = (level: string | null): string => {
        if (!level) return ''
        const labels: Record<string, string> = {
            submission: 'Submissions',
            voting: 'Voting',
            city: 'City',
            country: 'Country',
            regional: 'Regional',
            continental: 'Continental',
            global: 'Global'
        }
        return labels[level] || level
    }

    // Calculer les stats
    const completedRounds = rounds.filter(r => r.is_completed).length
    const activeRound = rounds.find(r => r.is_submission_open || r.is_voting_open)
    const totalRounds = rounds.length

    return (
        <div className={`space-y-2 ${className}`}>
            {/* Stats summary */}
            <div className="flex items-center gap-4 text-xs text-gray-400 px-1">
                <span>
                    <span className="text-green-400 font-medium">{completedRounds}</span>/{totalRounds} rounds completed
                </span>
                {activeRound && (
                    <span>
                        Current: <span className="text-blue-400 font-medium">{activeRound.name}</span>
                    </span>
                )}
            </div>

            {/* Horizontal scrollable rounds */}
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
                {rounds.map((round) => {
                    const isSelected = selectedRoundId === round.id
                    const statusColor = getStatusColor(round)
                    const statusIcon = getStatusIcon(round)

                    return (
                        <button
                            key={round.id}
                            onClick={() => onSelectRound(round.id)}
                            className={`
                flex-shrink-0 px-3 py-2 rounded-lg border transition-all
                ${isSelected
                                    ? 'ring-2 ring-blue-500 ' + statusColor
                                    : statusColor + ' hover:opacity-80'
                                }
              `}
                        >
                            <div className="flex items-center gap-2">
                                <span className="text-sm">{statusIcon}</span>
                                <div className="text-left">
                                    {round.is_voting_open && (
                                        <div className="text-[10px] font-bold uppercase tracking-wide text-blue-500 mb-0.5">
                                            {t('dashboard.contests.vote_label') || 'Vote'}
                                        </div>
                                    )}
                                    <div className="text-sm font-medium whitespace-nowrap">
                                        {round.name}
                                    </div>
                                    <div className="flex items-center gap-2 text-xs opacity-80">
                                        <span>{round.participants_count} participants</span>
                                        {round.current_season_level && (
                                            <>
                                                <span>•</span>
                                                <span>{getSeasonLevelLabel(round.current_season_level)}</span>
                                            </>
                                        )}
                                    </div>
                                </div>
                                {round.current_user_participated && (
                                    <span className="ml-2 px-1.5 py-0.5 bg-green-500/20 text-green-400 text-xs rounded">
                                        You're in
                                    </span>
                                )}
                            </div>
                        </button>
                    )
                })}
            </div>
        </div>
    )
}

export default RoundSelector
