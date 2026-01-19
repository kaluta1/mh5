'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { messagingService, Conversation, DecryptedMessage } from '@/services/messaging-service'
import { apiService } from '@/lib/api'
import { UserAvatar } from '@/components/user/user-avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, Send, Lock, Users } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { enUS, fr } from 'date-fns/locale'
import { cn } from '@/lib/utils'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'

const localeMap: Record<string, any> = {
  en: enUS,
  fr: fr,
  es: enUS, // fallback to enUS
  de: enUS // fallback to enUS
}

const parseApiDate = (value?: string) => {
  if (!value) return new Date()
  const hasTimezone = /[zZ]|([+-]\d{2}:\d{2})$/.test(value)
  return new Date(hasTimezone ? value : `${value}Z`)
}

const buildDisplayName = (user: any, fallbackId?: number) => {
  if (user?.full_name) return user.full_name
  if (user?.username) return user.username
  return fallbackId ? `User ${fallbackId}` : 'User'
}

export default function MessagesPage() {
  const { isAuthenticated, user } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t, language } = useLanguage()
  const { addToast } = useToast()
  const dateLocale = localeMap[language] || enUS
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedConversation, setSelectedConversation] = useState<number | null>(null)
  const [messages, setMessages] = useState<DecryptedMessage[]>([])
  const [messageText, setMessageText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [recipientId, setRecipientId] = useState<number | null>(null)
  const [usersById, setUsersById] = useState<Record<number, any>>({})
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login')
      return
    }
    loadConversations()
    // Generate encryption keys if not already done
    checkAndGenerateKeys()
  }, [isAuthenticated, router])

  useEffect(() => {
    const recipientParam = searchParams.get('user')
    if (recipientParam) {
      const parsedId = Number(recipientParam)
      if (!Number.isNaN(parsedId)) {
        setRecipientId(parsedId)
      }
    }
  }, [searchParams])

  useEffect(() => {
    if (selectedConversation) {
      loadMessages(selectedConversation)
    }
  }, [selectedConversation])

  useEffect(() => {
    if (!recipientId || !user?.id || conversations.length === 0) return
    const existingConversation = conversations.find(
      (conversation) =>
        (conversation.user1_id === user.id && conversation.user2_id === recipientId) ||
        (conversation.user2_id === user.id && conversation.user1_id === recipientId)
    )
    if (existingConversation) {
      setSelectedConversation(existingConversation.id)
    }
  }, [recipientId, conversations, user?.id])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const checkAndGenerateKeys = async () => {
    if (!user?.id) return

    try {
      // Try to get public key - if it fails, generate keys
      await messagingService.getPublicKey(user.id)
    } catch (error: any) {
      // Keys don't exist (404) or other error, generate them
      if (error?.response?.status === 404 || !error?.response) {
        try {
          await messagingService.generateKeys()
          console.log('Encryption keys generated successfully')
        } catch (err: any) {
          const status = err?.response?.status
          const message = err?.response?.data?.detail || err?.message
          // Keys already exist or were created elsewhere; treat as success.
          if (status === 400 && typeof message === 'string' && message.toLowerCase().includes('already')) {
            return
          }
          console.error('Error generating encryption keys:', err)
          // Don't show alert, just log - keys will be generated when needed
        }
      }
    }
  }

  const loadConversations = async () => {
    setIsLoading(true)
    try {
      const data = await messagingService.getConversations()
      setConversations(Array.isArray(data) ? data : [])
      const ids = Array.isArray(data)
        ? data
          .map((conversation) => getConversationPartner(conversation).id)
          .filter((id): id is number => Boolean(id))
          .filter((id) => !usersById[id])
        : []
      if (ids.length > 0) {
        await loadUsers(ids)
      }
    } catch (error) {
      console.error('Error loading conversations:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const loadUsers = async (userIds: number[]) => {
    try {
      const responses = await Promise.all(
        userIds.map((id) => apiService.get(`/api/v1/users/${id}`).catch(() => null))
      )
      setUsersById((prev) => {
        const next = { ...prev }
        responses.forEach((userData: any) => {
          if (userData?.id) {
            next[userData.id] = userData
          }
        })
        return next
      })
    } catch (error) {
      console.error('Error loading user info:', error)
    }
  }

  const loadMessages = async (conversationId: number) => {
    try {
      const data = await messagingService.getMessages(conversationId)
      // Messages come in reverse order (newest first), so reverse to show oldest first
      const sortedMessages = [...data].reverse()
      setMessages(sortedMessages)
      // Mark messages as read
      sortedMessages.forEach(msg => {
        if (msg.sender_id !== user?.id && msg.status !== 'read') {
          messagingService.markAsRead(msg.id).catch(err => console.error('Error marking as read:', err))
        }
      })
      // Scroll to bottom after a short delay to ensure DOM is updated
      setTimeout(() => scrollToBottom(), 100)
    } catch (error: any) {
      console.error('Error loading messages:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to load messages.'
      if (error?.response?.status !== 404) {
        addToast(errorMessage, 'error')
      }
    }
  }

  const handleSendMessage = async () => {
    if (!messageText.trim() || !recipientId || isSending) return

    setIsSending(true)
    try {
      const newMessage = await messagingService.sendMessage({
        recipient_id: recipientId,
        content: messageText.trim(),
        message_type: 'text',
      })
      const optimisticMessage = {
        ...newMessage,
        content: newMessage.content || messageText.trim(),
        created_at: newMessage.created_at || new Date().toISOString(),
      }
      setMessages(prev => [...prev, optimisticMessage])
      if (!selectedConversation && newMessage.conversation_id) {
        setSelectedConversation(newMessage.conversation_id)
      }
      setMessageText('')
      await loadConversations() // Refresh conversations to update last message
      scrollToBottom() // Scroll to bottom after sending
    } catch (error: any) {
      console.error('Error sending message:', error)
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to send message. Please try again.'
      addToast(errorMessage, 'error')
    } finally {
      setIsSending(false)
    }
  }

  const handleDeleteMessage = async (messageId: number) => {
    try {
      await messagingService.deleteMessage(messageId)
      setMessages(prev => prev.filter(msg => msg.id !== messageId))
    } catch (error) {
      console.error('Error deleting message:', error)
      addToast('Failed to delete message.', 'error')
    }
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const getConversationPartner = (conversation: Conversation) => {
    if (conversation.user1_id === user?.id) {
      return { id: conversation.user2_id }
    }
    return { id: conversation.user1_id }
  }

  const hasActiveThread = Boolean(selectedConversation || recipientId)
  const selectedConversationData = selectedConversation
    ? conversations.find(c => c.id === selectedConversation)
    : null
  const activePartner = selectedConversationData
    ? getConversationPartner(selectedConversationData)
    : recipientId
      ? { id: recipientId }
      : null
  const activePartnerUser = activePartner?.id ? usersById[activePartner.id] : null

  useEffect(() => {
    if (recipientId && !usersById[recipientId]) {
      loadUsers([recipientId])
    }
  }, [recipientId, usersById])

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-4rem)] bg-white dark:bg-gray-900 overflow-hidden">
      {/* Conversations List - Hidden on mobile when conversation selected, shown on desktop always */}
      <div className={`w-full md:w-1/3 lg:w-1/4 border-r border-gray-200 dark:border-gray-700 flex flex-col ${selectedConversation ? 'hidden md:flex' : 'flex'}`}>
        <div className="p-3 md:p-4 border-b border-gray-200 dark:border-gray-700">
          <h1 className="text-lg md:text-xl font-bold text-gray-900 dark:text-white">{t('dashboard.messages.title')}</h1>
          <p className="text-xs md:text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('dashboard.messages.subtitle')}
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center flex-1">
            <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 p-6 text-center">
            <Users className="h-12 w-12 text-gray-400 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">
              {t('dashboard.messages.no_conversations')}
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
              {t('dashboard.messages.start_conversation')}
            </p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto">
            {conversations.map((conversation) => {
              const partner = getConversationPartner(conversation)
              const unreadCount = conversation.user1_id === user?.id
                ? conversation.unread_count_user1
                : conversation.unread_count_user2

              return (
                <button
                  key={conversation.id}
                  onClick={() => {
                    setSelectedConversation(conversation.id)
                    setRecipientId(partner.id || null)
                  }}
                  className={cn(
                    "w-full p-3 md:p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left border-b border-gray-100 dark:border-gray-800",
                    selectedConversation === conversation.id && "bg-gray-50 dark:bg-gray-800"
                  )}
                >
                  <div className="flex items-center gap-2 md:gap-3">
                    <UserAvatar user={partner} className="w-10 h-10 md:w-12 md:h-12 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <p className="font-semibold text-gray-900 dark:text-white truncate">
                          {buildDisplayName(usersById[partner.id], partner.id)}
                        </p>
                        {conversation.last_message_at && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {formatDistanceToNow(parseApiDate(conversation.last_message_at), {
                              addSuffix: true,
                              locale: dateLocale
                            })}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Lock className="h-3 w-3 text-gray-400" />
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                          {t('dashboard.messages.encrypted_message')}
                        </p>
                        {unreadCount > 0 && (
                          <span className="ml-auto bg-myhigh5-primary text-white text-xs rounded-full px-2 py-0.5">
                            {unreadCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Messages Area - Hidden on mobile when no conversation selected, shown on desktop always */}
      <div className={`flex-1 flex flex-col ${!hasActiveThread ? 'hidden md:flex' : 'flex'}`}>
        {hasActiveThread ? (
          <>
            {/* Messages Header */}
            <div className="p-3 md:p-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2 md:gap-3">
                {activePartner && (
                  <UserAvatar user={activePartnerUser || activePartner} className="w-8 h-8 md:w-10 md:h-10" />
                )}
                <div className="flex-1 min-w-0">
                  <h2 className="font-semibold text-sm md:text-base text-gray-900 dark:text-white truncate">
                    {activePartner?.id ? buildDisplayName(activePartnerUser, activePartner.id) : t('dashboard.messages.new_message')}
                  </h2>
                  <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                    <Lock className="h-3 w-3 flex-shrink-0" />
                    <span className="truncate">{t('dashboard.messages.end_to_end_encrypted')}</span>
                  </div>
                </div>
                {/* Back button for mobile */}
                <button
                  onClick={() => setSelectedConversation(null)}
                  className="md:hidden p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Messages List */}
            <div className="flex-1 overflow-y-auto p-3 md:p-4 space-y-3 md:space-y-4">
              {selectedConversation ? (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      "flex",
                      message.sender_id === user?.id ? "justify-end" : "justify-start"
                    )}
                  >
                    <div
                      className={cn(
                        "max-w-[85%] md:max-w-[70%] rounded-xl md:rounded-2xl px-3 md:px-4 py-2",
                        message.sender_id === user?.id
                          ? "bg-myhigh5-primary text-white"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white"
                      )}
                    >
                      <p className="text-sm whitespace-pre-wrap break-words">
                        {message.content}
                      </p>
                      <div className={cn(
                        "mt-1 flex items-center justify-between gap-2 text-xs",
                        message.sender_id === user?.id
                          ? "text-white/70"
                          : "text-gray-500 dark:text-gray-400"
                      )}>
                        <span>
                          {formatDistanceToNow(parseApiDate(message.created_at), {
                            addSuffix: true,
                            locale: dateLocale
                          })}
                        </span>
                        {message.sender_id === user?.id && (
                          <button
                            onClick={() => handleDeleteMessage(message.id)}
                            className={cn(
                              "text-xs underline decoration-dotted",
                              message.sender_id === user?.id
                                ? "text-white/70 hover:text-white"
                                : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                            )}
                          >
                            {t('common.delete') || 'Delete'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="flex items-center justify-center h-full text-center text-sm text-gray-500 dark:text-gray-400">
                  {t('dashboard.messages.new_message') || 'Start a new message'}
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Message Input */}
            <div className="p-3 md:p-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2">
                <Input
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSendMessage()
                    }
                  }}
                  placeholder={t('dashboard.messages.type_message')}
                  className="flex-1 text-sm md:text-base"
                />
                <Button
                  onClick={handleSendMessage}
                  disabled={!messageText.trim() || isSending}
                  size="sm"
                  className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white shrink-0"
                >
                  {isSending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center flex-1">
            <div className="text-center">
              <Users className="h-16 w-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                {t('dashboard.messages.select_conversation')}
              </h3>
              <p className="text-gray-500 dark:text-gray-400">
                {t('dashboard.messages.select_conversation_desc')}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
