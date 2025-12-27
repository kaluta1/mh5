"use client"

import * as React from "react"
import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Bell, Check, CheckCheck, Loader2, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { notificationService, Notification } from "@/services/notification-service"
import { useLanguage } from "@/contexts/language-context"

interface NotificationDropdownProps {
  className?: string
}

export function NotificationDropdown({ className }: NotificationDropdownProps) {
  const { t } = useLanguage()
  const router = useRouter()
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState<number>(0)
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isMarkingAsRead, setIsMarkingAsRead] = useState<number | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  // Charger les notifications et le compteur
  const loadNotifications = async () => {
    try {
      setIsLoading(true)
      const [notifs, count] = await Promise.all([
        notificationService.getNotifications(0, 20, false),
        notificationService.getUnreadCount()
      ])
      setNotifications(notifs)
      setUnreadCount(count)
    } catch (error) {
      console.error('Erreur lors du chargement des notifications:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Charger les notifications au montage et quand le dropdown s'ouvre
  useEffect(() => {
    loadNotifications()
    
    // Rafraîchir le compteur toutes les 30 secondes
    intervalRef.current = setInterval(() => {
      notificationService.getUnreadCount().then(setUnreadCount).catch(console.error)
    }, 30000)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  // Recharger quand le dropdown s'ouvre
  useEffect(() => {
    if (isOpen) {
      loadNotifications()
    }
  }, [isOpen])

  const handleMarkAsRead = async (notificationId: number) => {
    try {
      setIsMarkingAsRead(notificationId)
      await notificationService.markAsRead(notificationId)
      
      // Mettre à jour l'état local
      setNotifications(prev =>
        prev.map(n => n.id === notificationId ? { ...n, is_read: true } : n)
      )
      setUnreadCount(prev => Math.max(0, prev - 1))
    } catch (error) {
      console.error('Erreur lors du marquage de la notification comme lue:', error)
    } finally {
      setIsMarkingAsRead(null)
    }
  }

  const handleMarkAllAsRead = async () => {
    try {
      setIsLoading(true)
      await notificationService.markAllAsRead()
      
      // Mettre à jour l'état local
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch (error) {
      console.error('Erreur lors du marquage de toutes les notifications comme lues:', error)
    } finally {
      setIsLoading(false)
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
      const now = new Date()
      const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
      
      if (diffInSeconds < 60) {
        return t('notifications.time.just_now') || 'Just now'
      } else if (diffInSeconds < 3600) {
        const minutes = Math.floor(diffInSeconds / 60)
        if (minutes === 1) {
          return t('notifications.time.minute_ago') || '1 minute ago'
        }
        return (t('notifications.time.minutes_ago') || '{count} minutes ago').replace('{count}', minutes.toString())
      } else if (diffInSeconds < 86400) {
        const hours = Math.floor(diffInSeconds / 3600)
        if (hours === 1) {
          return t('notifications.time.hour_ago') || '1 hour ago'
        }
        return (t('notifications.time.hours_ago') || '{count} hours ago').replace('{count}', hours.toString())
      } else if (diffInSeconds < 604800) {
        const days = Math.floor(diffInSeconds / 86400)
        if (days === 1) {
          return t('notifications.time.day_ago') || '1 day ago'
        }
        return (t('notifications.time.days_ago') || '{count} days ago').replace('{count}', days.toString())
      } else if (diffInSeconds < 2592000) {
        const weeks = Math.floor(diffInSeconds / 604800)
        if (weeks === 1) {
          return t('notifications.time.week_ago') || '1 week ago'
        }
        return (t('notifications.time.weeks_ago') || '{count} weeks ago').replace('{count}', weeks.toString())
      } else if (diffInSeconds < 31536000) {
        const months = Math.floor(diffInSeconds / 2592000)
        if (months === 1) {
          return t('notifications.time.month_ago') || '1 month ago'
        }
        return (t('notifications.time.months_ago') || '{count} months ago').replace('{count}', months.toString())
      } else {
        const years = Math.floor(diffInSeconds / 31536000)
        if (years === 1) {
          return t('notifications.time.year_ago') || '1 year ago'
        }
        return (t('notifications.time.years_ago') || '{count} years ago').replace('{count}', years.toString())
      }
    } catch {
      return dateString
    }
  }

  const handleViewAll = () => {
    setIsOpen(false)
    router.push('/dashboard/notifications')
  }

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button 
          variant="ghost" 
          size="sm" 
          className={`relative p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${className}`}
        >
          <div className="relative">
            <Bell className="h-5 w-5 text-gray-600 dark:text-gray-300" />
            {unreadCount > 0 && (
              <span className="absolute -top-2 -right-2 bg-gradient-to-r from-red-500 to-pink-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1 shadow-lg animate-pulse">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 max-h-[500px] overflow-y-auto">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>{t('notifications.title') || 'Notifications'}</span>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleMarkAllAsRead}
              disabled={isLoading}
              className="h-6 px-2 text-xs"
            >
              {isLoading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <>
                  <CheckCheck className="h-3 w-3 mr-1" />
                  {t('notifications.mark_all_read') || 'Tout marquer comme lu'}
                </>
              )}
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        
        {isLoading && notifications.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            {t('notifications.no_notifications') || 'Aucune notification'}
          </div>
        ) : (
          notifications.slice(0, 5).map((notification) => (
            <DropdownMenuItem
              key={notification.id}
              className={`flex flex-col items-start p-3 cursor-pointer ${
                !notification.is_read ? 'bg-blue-50 dark:bg-blue-900/20' : ''
              }`}
              onClick={() => !notification.is_read && handleMarkAsRead(notification.id)}
            >
              <div className="flex items-start w-full gap-2">
                <span className="text-lg mt-0.5">{getNotificationIcon(notification.type)}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-sm font-medium ${!notification.is_read ? 'font-semibold' : ''}`}>
                      {notification.title}
                    </p>
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
                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                    {notification.message}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {formatDate(notification.created_at)}
                  </p>
                </div>
              </div>
            </DropdownMenuItem>
          ))
        )}
        
        {/* View All Button */}
        <DropdownMenuSeparator />
        <div className="p-2">
          <Button
            variant="ghost"
            onClick={handleViewAll}
            className="w-full justify-center gap-2 text-myhigh5-primary hover:text-myhigh5-primary hover:bg-myhigh5-primary/10"
          >
            <span className="text-sm font-medium">
              {t('notifications.view_all') || 'Voir toutes les notifications'}
            </span>
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

