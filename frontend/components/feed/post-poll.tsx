'use client'

import { useState } from 'react'
import { Poll } from '@/services/social-service'
import { socialService } from '@/services/social-service'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

interface PostPollProps {
  poll: Poll
  postId: number
}

export function PostPoll({ poll, postId }: PostPollProps) {
  const [selectedOption, setSelectedOption] = useState<number | null>(poll.user_vote || null)
  const [hasVoted, setHasVoted] = useState(!!poll.user_vote)
  const [isLoading, setIsLoading] = useState(false)

  const handleVote = async (optionId: number) => {
    if (hasVoted || isLoading) return
    
    setIsLoading(true)
    try {
      await socialService.votePoll(poll.id, optionId)
      setSelectedOption(optionId)
      setHasVoted(true)
      // Refresh poll data
      window.location.reload()
    } catch (error) {
      console.error('Error voting:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const isExpired = poll.expires_at && new Date(poll.expires_at) < new Date()

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3">
      <h3 className="font-semibold text-gray-900 dark:text-white">{poll.question}</h3>
      <div className="space-y-2">
        {poll.options.map((option) => {
          const isSelected = selectedOption === option.id
          const canVote = !hasVoted && !isExpired
          
          return (
            <div key={option.id} className="space-y-1">
              <button
                onClick={() => canVote && handleVote(option.id)}
                disabled={!canVote || isLoading}
                className={cn(
                  "w-full text-left p-3 rounded-lg border transition-colors",
                  canVote && "hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer",
                  isSelected && "border-myhigh5-primary bg-myhigh5-primary/5",
                  !canVote && "cursor-default",
                  isLoading && "opacity-50"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">
                    {option.text}
                  </span>
                  {hasVoted && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {option.percentage}%
                    </span>
                  )}
                </div>
                {hasVoted && (
                  <Progress value={option.percentage} className="h-2" />
                )}
              </button>
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{poll.total_votes} vote{poll.total_votes !== 1 ? 's' : ''}</span>
        {poll.expires_at && (
          <span>
            {isExpired ? 'Expiré' : `Expire ${new Date(poll.expires_at).toLocaleDateString()}`}
          </span>
        )}
      </div>
    </div>
  )
}

