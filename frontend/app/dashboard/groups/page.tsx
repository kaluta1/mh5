'use client'

import { useState, useEffect } from 'react'
import { Plus, Users, Lock, Globe, Search, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { UserAvatar } from '@/components/user/user-avatar'
import { FloatingActionButton } from '@/components/ui/floating-action-button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { socialService, SocialGroup, CreateGroupRequest } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

export default function GroupsPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const [groups, setGroups] = useState<SocialGroup[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [newGroup, setNewGroup] = useState<CreateGroupRequest>({
    name: '',
    description: '',
    is_private: false
  })
  const [isCreating, setIsCreating] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    loadGroups()
  }, [isAuthenticated, router])

  const loadGroups = async () => {
    setIsLoading(true)
    try {
      const data = await socialService.getGroups(0, 50)
      setGroups(data)
    } catch (error) {
      console.error('Error loading groups:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateGroup = async () => {
    if (!newGroup.name.trim()) return

    setIsCreating(true)
    try {
      const createdGroup = await socialService.createGroup(newGroup)
      setGroups(prev => [createdGroup, ...prev])
      setIsCreateDialogOpen(false)
      setNewGroup({ name: '', description: '', is_private: false })
      addToast('Group created successfully!', 'success')
    } catch (error: any) {
      console.error('Error creating group:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to create group. Please try again.'
      addToast(errorMessage, 'error')
    } finally {
      setIsCreating(false)
    }
  }

  const handleJoinGroup = async (groupId: number) => {
    try {
      await socialService.joinGroup(groupId)
      await loadGroups()
      addToast('Successfully joined the group!', 'success')
    } catch (error: any) {
      console.error('Error joining group:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to join group. Please try again.'
      addToast(errorMessage, 'error')
    }
  }

  const handleLeaveGroup = async (groupId: number) => {
    if (!confirm('Are you sure you want to leave this group?')) return
    
    try {
      await socialService.leaveGroup(groupId)
      await loadGroups()
      addToast('Successfully left the group.', 'success')
    } catch (error: any) {
      console.error('Error leaving group:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to leave group. Please try again.'
      addToast(errorMessage, 'error')
    }
  }

  const filteredGroups = groups.filter(group =>
    group.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    group.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="space-y-4 md:space-y-6 px-2 sm:px-4 md:px-6 pb-20 md:pb-24 max-w-7xl mx-auto">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl p-4 md:p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">{t('dashboard.groups.title')}</h1>
            <p className="text-xs md:text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('dashboard.groups.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative flex-1 md:flex-initial md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder={t('dashboard.groups.search_placeholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 text-sm md:text-base"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Groups Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
        </div>
      ) : filteredGroups.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-2xl p-12 border border-gray-100 dark:border-gray-700 shadow-sm text-center">
          <Users className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            {searchQuery ? t('dashboard.groups.no_groups_found') : t('dashboard.groups.no_groups_available')}
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            {searchQuery 
              ? t('dashboard.groups.try_keywords')
              : t('dashboard.groups.be_first')
            }
          </p>
          {!searchQuery && (
            <Button
              onClick={() => setIsCreateDialogOpen(true)}
              className="rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              <Plus className="h-4 w-4 mr-2" />
              {t('dashboard.groups.create_group')}
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {filteredGroups.map((group) => (
            <div
              key={group.id}
              className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-md transition-shadow overflow-hidden"
            >
              {/* Group Header */}
              <div className="p-4 md:p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="w-16 h-16 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
                    {group.avatar_url ? (
                      <img src={group.avatar_url} alt={group.name} className="w-full h-full rounded-full object-cover" />
                    ) : (
                      <Users className="w-8 h-8 text-white" />
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {group.is_private ? (
                      <Lock className="h-4 w-4 text-gray-500" />
                    ) : (
                      <Globe className="h-4 w-4 text-gray-500" />
                    )}
                  </div>
                </div>

                <Link href={`/dashboard/groups/${group.id}`}>
                  <h3 className="text-lg md:text-xl font-bold text-gray-900 dark:text-white mb-2 hover:text-myhigh5-primary transition-colors line-clamp-1">
                    {group.name}
                  </h3>
                </Link>

                {group.description && (
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">
                    {group.description}
                  </p>
                )}

                <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400 mb-4">
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1">
                      <Users className="h-4 w-4" />
                      {group.members_count} {t('dashboard.groups.members')}
                    </span>
                  </div>
                </div>

                {group.creator && (
                  <div className="flex items-center gap-2 mb-4 text-sm text-gray-500 dark:text-gray-400">
                    <span>{t('dashboard.groups.created_by')}</span>
                    <UserAvatar user={group.creator} className="w-5 h-5" />
                    <span>{group.creator.full_name || group.creator.username}</span>
                  </div>
                )}

                <Button
                  onClick={() => group.is_member ? handleLeaveGroup(group.id) : handleJoinGroup(group.id)}
                  variant={group.is_member ? 'outline' : 'default'}
                  className={cn(
                    "w-full rounded-full",
                    group.is_member 
                      ? "border-gray-300 dark:border-gray-600" 
                      : "bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                  )}
                >
                  {group.is_member ? t('dashboard.groups.leave') : t('dashboard.groups.join')}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Floating Action Button */}
      <FloatingActionButton
        onClick={() => setIsCreateDialogOpen(true)}
        label={t('dashboard.groups.create_group')}
        variant="primary"
        position="bottom-right"
      />

      {/* Create Group Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="max-w-lg mx-4 max-h-[90vh] overflow-y-auto" aria-describedby="create-group-description">
          <DialogHeader>
            <DialogTitle>{t('dashboard.groups.create_new_group')}</DialogTitle>
          </DialogHeader>
          <p id="create-group-description" className="sr-only">
            {t('dashboard.groups.create_new_group')}
          </p>

          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block text-gray-700 dark:text-gray-300">
                {t('dashboard.groups.group_name')} *
              </label>
              <Input
                placeholder={t('dashboard.groups.group_name_placeholder')}
                value={newGroup.name}
                onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
                className="w-full"
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block text-gray-700 dark:text-gray-300">
                {t('dashboard.groups.description')}
              </label>
              <Textarea
                placeholder={t('dashboard.groups.description_placeholder')}
                value={newGroup.description}
                onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                className="min-h-[100px]"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('dashboard.groups.group_type')}
              </label>
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setNewGroup({ ...newGroup, is_private: false })}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors",
                    !newGroup.is_private
                      ? "border-myhigh5-primary bg-myhigh5-primary/10 text-myhigh5-primary"
                      : "border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                  )}
                >
                  <Globe className="h-4 w-4" />
                  {t('dashboard.groups.public')}
                </button>
                <button
                  onClick={() => setNewGroup({ ...newGroup, is_private: true })}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors",
                    newGroup.is_private
                      ? "border-myhigh5-primary bg-myhigh5-primary/10 text-myhigh5-primary"
                      : "border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                  )}
                >
                  <Lock className="h-4 w-4" />
                  {t('dashboard.groups.private')}
                </button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
            >
              {t('dashboard.groups.cancel')}
            </Button>
            <Button
              onClick={handleCreateGroup}
              disabled={!newGroup.name.trim() || isCreating}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              {isCreating ? t('dashboard.groups.creating') : t('dashboard.groups.create_group_button')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

