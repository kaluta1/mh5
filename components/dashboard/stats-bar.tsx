'use client'

import { ThumbsUp, MessageCircle, Heart, Star } from 'lucide-react'

interface StatsBarProps {
  votes?: number
  reactions?: number
  comments?: number
  favorites?: number
}

export function StatsBar({ votes = 0, reactions = 0, comments = 0, favorites = 0 }: StatsBarProps) {
  return (
    <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
        <div className="flex items-center gap-4">
          {votes > 0 && (
            <div className="flex items-center gap-1">
              <ThumbsUp className="w-4 h-4 text-blue-600" fill="currentColor" />
              <span>{votes}</span>
            </div>
          )}
          {reactions > 0 && (
            <div className="flex items-center gap-1">
              <Star className="w-4 h-4 text-purple-600" fill="currentColor" />
              <span>{reactions}</span>
            </div>
          )}
          {comments > 0 && (
            <div className="flex items-center gap-1">
              <MessageCircle className="w-4 h-4" />
              <span>{comments}</span>
            </div>
          )}
          {favorites > 0 && (
            <div className="flex items-center gap-1">
              <Heart className="w-4 h-4 text-red-500" fill="currentColor" />
              <span>{favorites}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

