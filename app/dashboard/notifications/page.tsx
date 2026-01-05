'use client'

import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { NotificationsSkeleton } from '@/components/ui/skeleton'
import { notificationService, Notification } from '@/services/notification-service'
import { Bell, Check, CheckCheck, Loader2, Filter } from 'lucide-react'

type FilterType = 'all' | 'unread'

export default function NotificationsPage() {
  const { t, language } = useLanguage()
  const { user, isAuthenticated, isLoading } = useAuth()
  const { addToast } = useToast()
  const router = useRouter()
  
  // Mapping des langues vers les locales
  const localeMap: Record<string, string> = {
    fr: 'fr-FR',
    en: 'en-US',
    es: 'es-ES',
    de: 'de-DE'
  }
  
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [pageLoading, setPageLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [filter, setFilter] = useState<FilterType>('all')
  const [unreadCount, setUnreadCount] = useState(0)
  const [currentPage, setCurrentPage] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [isMarkingAsRead, setIsMarkingAsRead] = useState<number | null>(null)
  const [isMarkingAllAsRead, setIsMarkingAllAsRead] = useState(false)
  
  const ITEMS_PER_PAGE = 20
  const observerTarget = useRef<HTMLDivElement>(null)
  const isMountedRef = useRef(true)

  // Redirection si non authentifié
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  // Gérer le montage/démontage du composant
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Charger les notifications et le compteur
  const loadNotifications = async (page: number = 0, reset: boolean = false) => {
    if (!isAuthenticated || !user) return

    try {
      if (page === 0) {
        setPageLoading(true)
      } else {
        setIsLoadingMore(true)
      }

      const unreadOnly = filter === 'unread'
      const skip = page * ITEMS_PER_PAGE
      const newNotifications = await notificationService.getNotifications(
        skip,
        ITEMS_PER_PAGE,
        unreadOnly
      )

      if (!isMountedRef.current) return

      if (reset || page === 0) {
        setNotifications(newNotifications)
      } else {
        setNotifications(prev => [...prev, ...newNotifications])
      }

      setHasMore(newNotifications.length === ITEMS_PER_PAGE)
      setCurrentPage(page)

      // Charger le compteur de non lues
      if (page === 0) {
        const count = await notificationService.getUnreadCount()
        if (isMountedRef.current) {
          setUnreadCount(count)
        }
      }
    } catch (error: any) {
      console.error('Erreur lors du chargement des notifications:', error)
      if (isMountedRef.current) {
        addToast(error?.response?.data?.detail || 'Something went wrong', 'error')
      }
    } finally {
      if (isMountedRef.current) {
        setPageLoading(false)
        setIsLoadingMore(false)
      }
    }
  }

  // Charger les notifications au montage et quand le filtre change
  useEffect(() => {
    if (isAuthenticated && user) {
      loadNotifications(0, true)
    }
  }, [isAuthenticated, user, filter])

  // Observer pour le scroll infini
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore && !pageLoading) {
          loadNotifications(currentPage + 1, false)
        }
      },
      { threshold: 0.1 }
    )

    const currentTarget = observerTarget.current
    if (currentTarget) {
      observer.observe(currentTarget)
    }

    return () => {
      if (currentTarget) {
        observer.unobserve(currentTarget)
      }
    }
  }, [hasMore, isLoadingMore, pageLoading, currentPage, filter])

  const handleMarkAsRead = async (notificationId: number) => {
    try {
      setIsMarkingAsRead(notificationId)
      await notificationService.markAsRead(notificationId)
      
      // Mettre à jour l'état local
      setNotifications(prev =>
        prev.map(n => n.id === notificationId ? { ...n, is_read: true } : n)
      )
      setUnreadCount(prev => Math.max(0, prev - 1))
      
      addToast('Notification marked as read', 'success')
    } catch (error: any) {
      console.error('Erreur lors du marquage de la notification comme lue:', error)
      addToast(error?.response?.data?.detail || 'Something went wrong', 'error')
    } finally {
      setIsMarkingAsRead(null)
    }
  }

  const handleMarkAllAsRead = async () => {
    try {
      setIsMarkingAllAsRead(true)
      await notificationService.markAllAsRead()
      
      // Mettre à jour l'état local
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      setUnreadCount(0)
      
      addToast('All notifications marked as read', 'success')
    } catch (error: any) {
      console.error('Erreur lors du marquage de toutes les notifications comme lues:', error)
      addToast(error?.response?.data?.detail || 'Something went wrong', 'error')
    } finally {
      setIsMarkingAllAsRead(false)
    }
  }

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'contest':
        return '🏆'
      case 'compte':
        return '👤'
      case 'system':
        return '🔔'
      default:
        return '📢'
    }
  }

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString)
      return date.toLocaleDateString(localeMap[language] || 'fr-FR', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return dateString
    }
  }

  const handleNotificationClick = (notification: Notification) => {
    // Marquer comme lu si ce n'est pas déjà fait
    if (!notification.is_read) {
      handleMarkAsRead(notification.id)
    }

    // Naviguer vers l'élément lié
    if (notification.related_contestant_id && notification.related_contest_id) {
      router.push(`/dashboard/contests/${notification.related_contest_id}/contestant/${notification.related_contestant_id}`)
    } else if (notification.related_contest_id) {
      router.push(`/dashboard/contests/${notification.related_contest_id}`)
    } else if (notification.related_contestant_id) {
      router.push(`/dashboard/contestants/${notification.related_contestant_id}`)
    }
  }

  if (isLoading || pageLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <NotificationsSkeleton />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Bell className="h-6 w-6" />
          <h1 className="text-2xl font-bold">{t('notifications.title') || 'Notifications'}</h1>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="ml-2">
              {unreadCount}
            </Badge>
          )}
        </div>
        
        {unreadCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleMarkAllAsRead}
            disabled={isMarkingAllAsRead}
          >
            {isMarkingAllAsRead ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <CheckCheck className="h-4 w-4 mr-2" />
            )}
            {t('notifications.mark_all_read') || 'Mark all as read'}
          </Button>
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-6">
        <Filter className="h-4 w-4 text-gray-500" />
        <Button
          variant={filter === 'all' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('all')}
        >
          All
        </Button>
        <Button
          variant={filter === 'unread' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('unread')}
        >
          Unread
          {unreadCount > 0 && (
            <Badge variant="secondary" className="ml-2">
              {unreadCount}
            </Badge>
          )}
        </Button>
      </div>

      {/* Notifications List */}
      {notifications.length === 0 ? (
        <Card className="p-8 text-center">
          <Bell className="h-12 w-12 mx-auto mb-4 text-gray-400" />
          <p className="text-gray-500 dark:text-gray-400">
            {t('notifications.no_notifications') || 'No notifications'}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {notifications.map((notification) => (
            <Card
              key={notification.id}
              className={`p-4 cursor-pointer transition-all hover:shadow-md ${
                !notification.is_read ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800' : ''
              }`}
              onClick={() => handleNotificationClick(notification)}
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl mt-0.5">{getNotificationIcon(notification.type)}</span>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <h3 className={`text-sm font-medium ${!notification.is_read ? 'font-semibold' : ''}`}>
                      {notification.title}
                    </h3>
                    {!notification.is_read && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleMarkAsRead(notification.id)
                        }}
                        disabled={isMarkingAsRead === notification.id}
                        className="h-6 w-6 p-0"
                      >
                        {isMarkingAsRead === notification.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Check className="h-3 w-3" />
                        )}
                      </Button>
                    )}
                  </div>
                  
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {notification.message}
                  </p>
                  
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {formatDate(notification.created_at)}
                    </p>
                    <Badge variant="outline" className="text-xs">
                      {t(`notifications.types.${notification.type}`) || notification.type}
                    </Badge>
                  </div>
                </div>
              </div>
            </Card>
          ))}
          
          {/* Infinite scroll target */}
          {hasMore && (
            <div ref={observerTarget} className="h-10 flex items-center justify-center">
              {isLoadingMore && <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

