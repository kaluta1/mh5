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

export default function GroupsPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
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
    } catch (error) {
      console.error('Error creating group:', error)
    } finally {
      setIsCreating(false)
    }
  }

  const handleJoinGroup = async (groupId: number) => {
    try {
      await socialService.joinGroup(groupId)
      await loadGroups()
    } catch (error) {
      console.error('Error joining group:', error)
    }
  }

  const handleLeaveGroup = async (groupId: number) => {
    try {
      await socialService.leaveGroup(groupId)
      await loadGroups()
    } catch (error) {
      console.error('Error leaving group:', error)
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
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Groupes</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Rejoignez des groupes et partagez avec votre communauté
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative flex-1 md:flex-initial md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Rechercher un groupe..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
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
            {searchQuery ? 'Aucun groupe trouvé' : 'Aucun groupe disponible'}
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            {searchQuery 
              ? 'Essayez avec d\'autres mots-clés'
              : 'Soyez le premier à créer un groupe !'
            }
          </p>
          {!searchQuery && (
            <Button
              onClick={() => setIsCreateDialogOpen(true)}
              className="rounded-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              <Plus className="h-4 w-4 mr-2" />
              Créer un groupe
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredGroups.map((group) => (
            <div
              key={group.id}
              className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm hover:shadow-md transition-shadow overflow-hidden"
            >
              {/* Group Header */}
              <div className="p-6">
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
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2 hover:text-myhigh5-primary transition-colors">
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
                      {group.members_count} membres
                    </span>
                  </div>
                </div>

                {group.creator && (
                  <div className="flex items-center gap-2 mb-4 text-sm text-gray-500 dark:text-gray-400">
                    <span>Créé par</span>
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
                  {group.is_member ? 'Quitter' : 'Rejoindre'}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Floating Action Button */}
      <FloatingActionButton
        onClick={() => setIsCreateDialogOpen(true)}
        label="Créer un groupe"
        variant="primary"
        position="bottom-right"
      />

      {/* Create Group Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Créer un nouveau groupe</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block text-gray-700 dark:text-gray-300">
                Nom du groupe *
              </label>
              <Input
                placeholder="Nom du groupe"
                value={newGroup.name}
                onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
                className="w-full"
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block text-gray-700 dark:text-gray-300">
                Description
              </label>
              <Textarea
                placeholder="Description du groupe (optionnel)"
                value={newGroup.description}
                onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                className="min-h-[100px]"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Type de groupe
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
                  Public
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
                  Privé
                </button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateDialogOpen(false)}
            >
              Annuler
            </Button>
            <Button
              onClick={handleCreateGroup}
              disabled={!newGroup.name.trim() || isCreating}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              {isCreating ? 'Création...' : 'Créer le groupe'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

