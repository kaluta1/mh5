'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import { followService, User } from '@/services/follow-service'
import { UserAvatar } from '@/components/user/user-avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, Search, UserPlus, UserMinus, Users } from 'lucide-react'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

export default function FollowingPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [activeTab, setActiveTab] = useState<'following' | 'followers' | 'suggested'>('following')
  const [users, setUsers] = useState<User[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    loadUsers()
  }, [isAuthenticated, router, activeTab])

  const loadUsers = async () => {
    setIsLoading(true)
    try {
      let data: User[] = []
      if (activeTab === 'following') {
        data = await followService.getFollowing(user?.id || 0)
      } else if (activeTab === 'followers') {
        data = await followService.getFollowers(user?.id || 0)
      } else {
        data = await followService.getSuggestedUsers()
      }
      setUsers(data)
    } catch (error) {
      console.error('Error loading users:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleFollow = async (userId: number) => {
    try {
      await followService.followUser(userId)
      setUsers(prev => prev.map(u => 
        u.id === userId ? { ...u, is_following: true, followers_count: (u.followers_count || 0) + 1 } : u
      ))
      addToast('Successfully followed user!', 'success')
    } catch (error: any) {
      console.error('Error following user:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to follow user. Please try again.'
      addToast(errorMessage, 'error')
    }
  }

  const handleUnfollow = async (userId: number) => {
    try {
      await followService.unfollowUser(userId)
      setUsers(prev => prev.map(u => 
        u.id === userId ? { ...u, is_following: false, followers_count: Math.max(0, (u.followers_count || 1) - 1) } : u
      ))
      addToast('Successfully unfollowed user.', 'success')
    } catch (error: any) {
      console.error('Error unfollowing user:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to unfollow user. Please try again.'
      addToast(errorMessage, 'error')
    }
  }

  const filteredUsers = users.filter(u =>
    u.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="space-y-4 md:space-y-6 px-2 sm:px-4 md:px-6 pb-20 md:pb-24 max-w-7xl mx-auto">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl p-4 md:p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white mb-2">
          {t('dashboard.following.title')}
        </h1>
        <p className="text-xs md:text-sm text-gray-500 dark:text-gray-400">
          {t('dashboard.following.subtitle')}
        </p>
      </div>

      {/* Tabs */}
      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm">
        <div className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
          <button
            onClick={() => setActiveTab('following')}
            className={cn(
              "flex-1 px-3 md:px-6 py-3 md:py-4 text-xs md:text-sm font-medium transition-colors whitespace-nowrap shrink-0",
              activeTab === 'following'
                ? "text-myhigh5-primary border-b-2 border-myhigh5-primary"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            )}
          >
            {t('dashboard.following.following_tab')} ({users.filter(u => activeTab === 'following' && u.is_following).length || users.length})
          </button>
          <button
            onClick={() => setActiveTab('followers')}
            className={cn(
              "flex-1 px-3 md:px-6 py-3 md:py-4 text-xs md:text-sm font-medium transition-colors whitespace-nowrap shrink-0",
              activeTab === 'followers'
                ? "text-myhigh5-primary border-b-2 border-myhigh5-primary"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            )}
          >
            {t('dashboard.following.followers_tab')} ({users.filter(u => activeTab === 'followers' && u.is_followed_by).length || users.length})
          </button>
          <button
            onClick={() => setActiveTab('suggested')}
            className={cn(
              "flex-1 px-3 md:px-6 py-3 md:py-4 text-xs md:text-sm font-medium transition-colors whitespace-nowrap shrink-0",
              activeTab === 'suggested'
                ? "text-myhigh5-primary border-b-2 border-myhigh5-primary"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            )}
          >
            {t('dashboard.following.suggested_tab')}
          </button>
        </div>

        {/* Search */}
        <div className="p-3 md:p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder={t('dashboard.following.search_placeholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 text-sm md:text-base"
            />
          </div>
        </div>

        {/* Users List */}
        <div className="p-3 md:p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="text-center py-12">
              <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500 dark:text-gray-400">
                {searchQuery ? t('dashboard.following.no_users_found') : t('dashboard.following.no_users')}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredUsers.map((userItem) => (
                <div
                  key={userItem.id}
                  className="flex items-center justify-between p-3 md:p-4 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors gap-2"
                >
                  <Link
                    href={`/dashboard/profile/${userItem.id}`}
                    className="flex items-center gap-2 md:gap-3 flex-1 min-w-0"
                  >
                    <UserAvatar user={userItem} className="w-10 h-10 md:w-12 md:h-12 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-sm md:text-base text-gray-900 dark:text-white truncate">
                        {userItem.full_name || userItem.username}
                      </h3>
                      <p className="text-xs md:text-sm text-gray-500 dark:text-gray-400 truncate">
                        @{userItem.username}
                      </p>
                      {userItem.bio && (
                        <p className="text-xs md:text-sm text-gray-600 dark:text-gray-300 mt-1 line-clamp-2 hidden sm:block">
                          {userItem.bio}
                        </p>
                      )}
                      <div className="flex items-center gap-3 md:gap-4 mt-1 md:mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {userItem.followers_count !== undefined && (
                          <span>{userItem.followers_count} {t('dashboard.following.followers')}</span>
                        )}
                        {userItem.posts_count !== undefined && (
                          <span>{userItem.posts_count} {t('dashboard.following.posts')}</span>
                        )}
                      </div>
                    </div>
                  </Link>
                  {userItem.id !== user?.id && (
                    <Button
                      onClick={() => 
                        userItem.is_following 
                          ? handleUnfollow(userItem.id) 
                          : handleFollow(userItem.id)
                      }
                      variant={userItem.is_following ? 'outline' : 'default'}
                      size="sm"
                      className={cn(
                        "rounded-full shrink-0 text-xs md:text-sm",
                        !userItem.is_following && "bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                      )}
                    >
                      {userItem.is_following ? (
                        <>
                          <UserMinus className="h-3 w-3 md:h-4 md:w-4 md:mr-2" />
                          <span className="hidden sm:inline">{t('dashboard.following.unfollow')}</span>
                        </>
                      ) : (
                        <>
                          <UserPlus className="h-3 w-3 md:h-4 md:w-4 md:mr-2" />
                          <span className="hidden sm:inline">{t('dashboard.following.follow')}</span>
                        </>
                      )}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
