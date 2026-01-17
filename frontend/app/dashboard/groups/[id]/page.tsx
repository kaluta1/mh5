'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Lock, Globe, Users, Loader2, ArrowLeft, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { UserAvatar } from '@/components/user/user-avatar'
import { socialService, SocialGroup, GroupMember, GroupMessage } from '@/services/social-service'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

export default function GroupDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, user } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const groupId = Number(params?.id)

  const [group, setGroup] = useState<SocialGroup | null>(null)
  const [members, setMembers] = useState<GroupMember[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isJoining, setIsJoining] = useState(false)
  const [messages, setMessages] = useState<GroupMessage[]>([])
  const [messageText, setMessageText] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    if (!Number.isNaN(groupId)) {
      loadGroup()
    }
  }, [isAuthenticated, groupId])

  const loadGroup = async () => {
    setIsLoading(true)
    try {
      const data = await socialService.getGroup(groupId)
      setGroup(data)
      const memberList = await socialService.getGroupMembers(groupId)
      setMembers(memberList)
      if (data.is_member) {
        await loadMessages()
      } else {
        setMessages([])
      }
    } catch (error) {
      console.error('Error loading group:', error)
      addToast('Failed to load group.', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const loadMessages = async () => {
    setIsLoadingMessages(true)
    try {
      const data = await socialService.getGroupMessages(groupId, 0, 50)
      setMessages(Array.isArray(data) ? data.slice().reverse() : [])
    } catch (error) {
      console.error('Error loading group messages:', error)
      addToast('Failed to load messages.', 'error')
    } finally {
      setIsLoadingMessages(false)
    }
  }

  const handleJoinLeave = async () => {
    if (!group) return
    setIsJoining(true)
    try {
      if (group.is_member) {
        await socialService.leaveGroup(group.id)
        addToast('Left group.', 'success')
      } else {
        await socialService.joinGroup(group.id)
        addToast('Joined group.', 'success')
      }
      await loadGroup()
    } catch (error: any) {
      console.error('Error updating group membership:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Action failed.'
      addToast(errorMessage, 'error')
    } finally {
      setIsJoining(false)
    }
  }

  const handleSendMessage = async () => {
    if (!group || !messageText.trim()) return
    setIsSending(true)
    try {
      const sent = await socialService.sendGroupMessage(group.id, {
        content: messageText.trim(),
        message_type: 'text',
      })
      setMessages((prev) => [...prev, sent])
      setMessageText('')
    } catch (error: any) {
      console.error('Error sending group message:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to send message.'
      addToast(errorMessage, 'error')
    } finally {
      setIsSending(false)
    }
  }

  const parseApiDate = (value: string) => {
    if (!value) return new Date()
    if (/[zZ]|[+-]\d{2}:\d{2}$/.test(value)) {
      return new Date(value)
    }
    return new Date(`${value}Z`)
  }

  const orderedMessages = useMemo(() => {
    return [...messages].sort((a, b) => {
      return parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime()
    })
  }, [messages])

  if (!isAuthenticated) {
    return null
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  if (!group) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        {t('dashboard.groups.no_groups_found') || 'Group not found'}
      </div>
    )
  }

  return (
    <div className="space-y-4 md:space-y-6 px-2 sm:px-4 md:px-6 pb-20 md:pb-24 max-w-5xl mx-auto">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          {t('common.back') || 'Back'}
        </Button>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl p-4 md:p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center flex-shrink-0">
              {group.avatar_url ? (
                <img src={group.avatar_url} alt={group.name} className="w-full h-full rounded-full object-cover" />
              ) : (
                <Users className="w-8 h-8 text-white" />
              )}
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold text-gray-900 dark:text-white">
                {group.name}
              </h1>
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mt-1">
                {group.is_private ? <Lock className="h-4 w-4" /> : <Globe className="h-4 w-4" />}
                <span>{group.is_private ? t('dashboard.groups.private') : t('dashboard.groups.public')}</span>
                <span>•</span>
                <span>{group.members_count} {t('dashboard.groups.members')}</span>
              </div>
              {group.description && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-3">
                  {group.description}
                </p>
              )}
            </div>
          </div>
          <Button
            onClick={handleJoinLeave}
            disabled={isJoining}
            variant={group.is_member ? 'outline' : 'default'}
            className={group.is_member ? 'border-gray-300 dark:border-gray-600' : 'bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white'}
          >
            {group.is_member ? t('dashboard.groups.leave') : t('dashboard.groups.join')}
          </Button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl p-4 md:p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t('dashboard.groups.members') || 'Members'}
        </h2>
        <div className="space-y-3">
          {members.map((member) => (
            <div key={member.id} className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <UserAvatar user={member.user || { id: member.user_id }} className="w-10 h-10" />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {member.user?.full_name || member.user?.username || `User ${member.user_id}`}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {member.role}
                  </p>
                </div>
              </div>
            </div>
          ))}
          {members.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('dashboard.groups.no_members') || 'No members yet.'}
            </p>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl md:rounded-2xl p-4 md:p-6 border border-gray-100 dark:border-gray-700 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t('dashboard.messages.title') || 'Messages'}
        </h2>

        {!group.is_member ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {t('dashboard.groups.join_to_chat') || 'Join the group to start chatting.'}
          </div>
        ) : (
          <>
            <div className="h-80 overflow-y-auto border border-gray-100 dark:border-gray-700 rounded-lg p-3 space-y-3 bg-gray-50 dark:bg-gray-900/20">
              {isLoadingMessages ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
                </div>
              ) : orderedMessages.length === 0 ? (
                <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">
                  {t('dashboard.groups.no_messages') || 'No messages yet.'}
                </div>
              ) : (
                orderedMessages.map((message) => {
                  const isMine = message.sender_id === user?.id
                  return (
                    <div key={message.id} className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${isMine ? 'bg-myhigh5-primary text-white' : 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700'}`}>
                        {!isMine && (
                          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                            {message.sender?.full_name || message.sender?.username || `User ${message.sender_id}`}
                          </div>
                        )}
                        <div>{message.content || ''}</div>
                        <div className={`text-[11px] mt-1 ${isMine ? 'text-white/80' : 'text-gray-400'}`}>
                          {parseApiDate(message.created_at).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>

            <div className="mt-3 flex items-end gap-2">
              <Textarea
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                placeholder={t('dashboard.messages.type_message') || 'Type a message...'}
                className="min-h-[48px] resize-none"
              />
              <Button
                onClick={handleSendMessage}
                disabled={isSending || !messageText.trim()}
                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
