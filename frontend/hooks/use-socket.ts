'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { resolvePublicApiBase } from '@/lib/config'

interface SocketMessage {
  message_id: number
  group_id?: number
  conversation_id?: number
  sender_id: number
  sender_name: string
  content: string
  message_type: string
  created_at: string
}

interface UseSocketOptions {
  onNewMessage?: (message: SocketMessage) => void
  onMessageRead?: (data: { message_id: number; user_id: number }) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Error) => void
}

export function useSocket(options: UseSocketOptions = {}) {
  const socketRef = useRef<any>(null)
  const [isConnected, setIsConnected] = useState(false)
  const optionsRef = useRef(options)

  // Keep options ref up to date without triggering reconnection
  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) {
      return
    }

    // Dynamically import socket.io-client
    let socket: any
    let mounted = true

    import('socket.io-client').then((ioModule) => {
      if (!mounted) return

      const io = ioModule.io
      const apiUrl = resolvePublicApiBase()
      
      socket = io(apiUrl, {
        transports: ['websocket', 'polling'],
        auth: { token },
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
      })

      socketRef.current = socket

      socket.on('connect', () => {
        setIsConnected(true)
        optionsRef.current.onConnect?.()
      })

      socket.on('disconnect', (reason: string) => {
        setIsConnected(false)
        optionsRef.current.onDisconnect?.()
      })

      socket.on('connect_error', (error: Error) => {
        console.error('Socket connection error:', error)
        optionsRef.current.onError?.(error)
      })

      socket.on('new_message', (message: SocketMessage) => {
        optionsRef.current.onNewMessage?.(message)
      })

      socket.on('new_private_message', (message: SocketMessage) => {
        optionsRef.current.onNewMessage?.(message)
      })

      socket.on('message_read', (data: { message_id: number; user_id: number }) => {
        optionsRef.current.onMessageRead?.(data)
      })
    }).catch((err) => {
      console.error('Failed to load socket.io-client:', err)
    })

    return () => {
      mounted = false
      if (socket) {
        socket.disconnect()
        socketRef.current = null
      }
    }
  }, [])

  const joinGroup = useCallback((groupId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) {
      console.warn('Cannot join group: socket not connected')
      return
    }
    socket.emit('join_group', { group_id: groupId }, (response: any) => {
      if (response?.success) {
      } else {
        console.error('Failed to join group:', response?.error)
      }
    })
  }, [])

  const leaveGroup = useCallback((groupId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) return
    socket.emit('leave_group', { group_id: groupId })
  }, [])

  const joinConversation = useCallback((conversationId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) {
      console.warn('Cannot join conversation: socket not connected')
      return
    }
    socket.emit('join_conversation', { conversation_id: conversationId }, (response: any) => {
      if (response?.success) {
      } else {
        console.error('Failed to join conversation:', response?.error)
      }
    })
  }, [])

  const leaveConversation = useCallback((conversationId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) return
    socket.emit('leave_conversation', { conversation_id: conversationId })
  }, [])

  const notifyNewMessage = useCallback((groupId: number, messageId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) return
    socket.emit('send_message', { group_id: groupId, message_id: messageId })
  }, [])

  const notifyPrivateMessage = useCallback((conversationId: number, messageId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) return
    socket.emit('send_private_message', { conversation_id: conversationId, message_id: messageId })
  }, [])

  const markMessageRead = useCallback((messageId: number) => {
    const socket = socketRef.current
    if (!socket?.connected) return
    socket.emit('message_read', { message_id: messageId })
  }, [])

  return {
    socket: socketRef.current,
    isConnected,
    joinGroup,
    leaveGroup,
    joinConversation,
    leaveConversation,
    notifyNewMessage,
    notifyPrivateMessage,
    markMessageRead,
  }
}
