'use client'

import { useState, useEffect } from 'react'
import { Users, Lock, Globe } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserAvatar } from '@/components/user/user-avatar'
import Link from 'next/link'
import { cn } from '@/lib/utils'

interface SuggestedGroup {
  id: number
  name: string
  description?: string
  avatar_url?: string
  is_private: boolean
  members_count: number
  creator?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
}

interface SuggestedGroupsProps {
  currentUserId?: number
}

export function SuggestedGroups({ currentUserId }: SuggestedGroupsProps) {
  const [groups, setGroups] = useState<SuggestedGroup[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // TODO: Récupérer les groupes suggérés depuis l'API
    // Pour l'instant, on simule des données
    setTimeout(() => {
      setGroups([
        { 
          id: 1, 
          name: 'Groupe Tech', 
          description: 'Discussions sur les nouvelles technologies',
          is_private: false,
          members_count: 1234
        },
        { 
          id: 2, 
          name: 'Groupe Art', 
          description: 'Partagez vos créations artistiques',
          is_private: true,
          members_count: 567
        },
        { 
          id: 3, 
          name: 'Groupe Sport', 
          description: 'Passionnés de sport',
          is_private: false,
          members_count: 890
        },
      ])
      setIsLoading(false)
    }, 500)
  }, [])

  const handleJoin = async (groupId: number) => {
    // TODO: Implémenter la logique de rejoindre un groupe
    console.log('Join group:', groupId)
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4">
        <h3 className="text-xl font-bold mb-4">Groupes suggérés</h3>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 sticky top-4">
      <h3 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">
        Groupes suggérés
      </h3>
      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.id} className="flex items-start gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
              <Users className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <Link 
                  href={`/dashboard/groups/${group.id}`}
                  className="font-semibold text-gray-900 dark:text-white hover:underline truncate"
                >
                  {group.name}
                </Link>
                {group.is_private ? (
                  <Lock className="w-4 h-4 text-gray-500 flex-shrink-0" />
                ) : (
                  <Globe className="w-4 h-4 text-gray-500 flex-shrink-0" />
                )}
              </div>
              {group.description && (
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-2">
                  {group.description}
                </p>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                {group.members_count} membres
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleJoin(group.id)}
                className="rounded-full px-4 h-8 text-sm font-semibold w-full"
              >
                Rejoindre
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        className="w-full mt-4 text-myhigh5-primary hover:text-myhigh5-primary/80"
      >
        Voir plus
      </Button>
    </div>
  )
}

