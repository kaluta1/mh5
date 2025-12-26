'use client'

import { useState, useEffect } from 'react'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserAvatar } from '@/components/user/user-avatar'
import { cn } from '@/lib/utils'

interface SuggestedUser {
  id: number
  username: string
  full_name?: string
  avatar_url?: string
  bio?: string
  followers_count?: number
}

interface SuggestedUsersProps {
  currentUserId?: number
}

export function SuggestedUsers({ currentUserId }: SuggestedUsersProps) {
  const [users, setUsers] = useState<SuggestedUser[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // TODO: Récupérer les utilisateurs suggérés depuis l'API
    // Pour l'instant, on simule des données
    setTimeout(() => {
      setUsers([
        { id: 1, username: 'user1', full_name: 'User One', followers_count: 1234 },
        { id: 2, username: 'user2', full_name: 'User Two', followers_count: 567 },
        { id: 3, username: 'user3', full_name: 'User Three', followers_count: 890 },
      ])
      setIsLoading(false)
    }, 500)
  }, [])

  const handleFollow = async (userId: number) => {
    // TODO: Implémenter la logique de suivi
    console.log('Follow user:', userId)
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4">
        <h3 className="text-xl font-bold mb-4">Suggestions pour vous</h3>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 sticky top-4">
      <h3 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">
        Suggestions pour vous
      </h3>
      <div className="space-y-4">
        {users.map((user) => (
          <div key={user.id} className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <UserAvatar user={user} className="w-10 h-10 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 dark:text-white truncate">
                  {user.full_name || user.username}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                  @{user.username}
                </p>
                {user.followers_count && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {user.followers_count} abonnés
                  </p>
                )}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleFollow(user.id)}
              className="rounded-full px-4 h-8 text-sm font-semibold"
            >
              Suivre
            </Button>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        className="w-full mt-4 text-myfav-primary hover:text-myfav-primary/80"
      >
        Voir plus
      </Button>
    </div>
  )
}

