'use client'

import { useState } from 'react'
import { Image as ImageIcon, Video, BarChart3, Smile, MapPin, Calendar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserAvatar } from '@/components/user/user-avatar'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'

interface CreatePostBoxProps {
  user?: {
    id?: number
    username?: string
    full_name?: string
    avatar_url?: string
  }
  onPostCreated?: () => void
  onOpenDialog?: () => void
}

export function CreatePostBox({ user, onPostCreated, onOpenDialog }: CreatePostBoxProps) {
  const [isFocused, setIsFocused] = useState(false)
  const { t } = useLanguage()

  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div className="flex-shrink-0">
        <UserAvatar user={user} className="w-12 h-12" />
      </div>

      {/* Input Area */}
      <div className="flex-1">
        <button
          onClick={onOpenDialog}
          className="w-full text-left"
        >
          <div
            className={cn(
              "w-full min-h-[52px] px-4 py-3 rounded-2xl border transition-all",
              isFocused
                ? "border-myhigh5-primary bg-white dark:bg-gray-900"
                : "border-transparent bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"
            )}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
          >
            <p className="text-gray-500 dark:text-gray-400 text-lg">
              {t('dashboard.feed.create_post_placeholder') || 'What\'s on your mind?'}
            </p>
          </div>
        </button>

        {/* Action Buttons */}
        <div className="flex items-center justify-between mt-3 px-1">
          <div className="flex items-center gap-4">
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/20 transition-colors"
              title={t('dashboard.feed.media') || 'Media'}
            >
              <ImageIcon className="h-5 w-5 text-myhigh5-primary group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" />
            </button>
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-green-100 dark:hover:bg-green-900/20 transition-colors"
              title={t('dashboard.feed.video') || 'Video'}
            >
              <Video className="h-5 w-5 text-myhigh5-primary group-hover:text-green-600 dark:group-hover:text-green-400 transition-colors" />
            </button>
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-purple-100 dark:hover:bg-purple-900/20 transition-colors"
              title={t('dashboard.feed.poll') || 'Poll'}
            >
              <BarChart3 className="h-5 w-5 text-myhigh5-primary group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors" />
            </button>
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-yellow-100 dark:hover:bg-yellow-900/20 transition-colors"
              title={t('dashboard.feed.emoji') || 'Emoji'}
            >
              <Smile className="h-5 w-5 text-myhigh5-primary group-hover:text-yellow-600 dark:group-hover:text-yellow-400 transition-colors" />
            </button>
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-red-100 dark:hover:bg-red-900/20 transition-colors"
              title={t('dashboard.feed.schedule') || 'Schedule'}
            >
              <Calendar className="h-5 w-5 text-myhigh5-primary group-hover:text-red-600 dark:group-hover:text-red-400 transition-colors" />
            </button>
            <button
              onClick={onOpenDialog}
              className="group flex items-center justify-center w-9 h-9 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/20 transition-colors"
              title={t('dashboard.feed.location') || 'Location'}
            >
              <MapPin className="h-5 w-5 text-myhigh5-primary group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" />
            </button>
          </div>

          <Button
            onClick={onOpenDialog}
            className="rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white font-semibold px-4 h-9 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('dashboard.feed.publish') || 'Publish'}
          </Button>
        </div>
      </div>
    </div>
  )
}

