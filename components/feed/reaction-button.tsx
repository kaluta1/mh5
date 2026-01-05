'use client'

import { useState } from 'react'
import { Heart, Smile, Laugh, AlertCircle, Frown, Angry } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const reactions = [
  { type: 'like', icon: Heart, label: 'J\'aime', color: 'text-red-500' },
  { type: 'love', icon: Heart, label: 'J\'adore', color: 'text-pink-500' },
  { type: 'laugh', icon: Laugh, label: 'Haha', color: 'text-yellow-500' },
  { type: 'wow', icon: AlertCircle, label: 'Wow', color: 'text-blue-500' },
  { type: 'sad', icon: Frown, label: 'Triste', color: 'text-gray-500' },
  { type: 'angry', icon: Angry, label: 'En colère', color: 'text-orange-500' },
]

interface ReactionButtonProps {
  postId: number
  isLiked: boolean
  likesCount: number
  userReaction?: string
  onLike: () => void
  onReact?: (postId: number, reactionType: string) => void
}

export function ReactionButton({ 
  postId, 
  isLiked, 
  likesCount, 
  userReaction,
  onLike, 
  onReact 
}: ReactionButtonProps) {
  const [isOpen, setIsOpen] = useState(false)
  const currentReaction = reactions.find(r => r.type === userReaction)

  const handleReaction = (reactionType: string) => {
    if (reactionType === 'like') {
      onLike()
    } else {
      onReact?.(postId, reactionType)
    }
    setIsOpen(false)
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "group flex items-center gap-2 text-gray-500 dark:text-gray-400 transition-colors",
            (isLiked || userReaction) && "text-red-500 dark:text-red-400"
          )}
        >
          <div className={cn(
            "p-2 rounded-full transition-colors",
            (isLiked || userReaction) 
              ? "bg-red-100 dark:bg-red-900/20" 
              : "group-hover:bg-red-100 dark:group-hover:bg-red-900/20"
          )}>
            {currentReaction ? (
              <currentReaction.icon className={cn("h-5 w-5", currentReaction.color)} fill="currentColor" />
            ) : (
              <Heart className={cn("h-5 w-5", isLiked && "fill-current")} />
            )}
          </div>
          {likesCount > 0 && (
            <span className="text-sm">{likesCount}</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2" align="start">
        <div className="flex items-center gap-2">
          {reactions.map((reaction) => {
            const Icon = reaction.icon
            return (
              <button
                key={reaction.type}
                onClick={() => handleReaction(reaction.type)}
                className={cn(
                  "p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors",
                  userReaction === reaction.type && "bg-gray-100 dark:bg-gray-700"
                )}
                title={reaction.label}
              >
                <Icon className={cn("h-6 w-6", reaction.color)} />
              </button>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}

