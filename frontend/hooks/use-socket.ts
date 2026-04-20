'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import type { Socket } from 'socket.io-client'

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
  const socketRef = useRef<Socket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const optionsRef = useRef(options)
  const [ioClient, setIoClient] = useState<typeof import('socket.io-client') | null>(null)

  // Keep options ref up to date without triggering reconnection
  useEffect(() => {
    optionsRef.current = options
  }, [options])

  // Dynamically import socket.io-client to avoid SSR issues
  useEffect(() => {
    let mounted = true
    import('socket.io-client').then((mod) => {
      if (mounted) setIoClient(mod)
    })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!ioClient) return

    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (!token) {
      console.log('No access token available for socket connection')
      return
    }

    // Get the API URL from environment or default
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    
    // Create socket connection
    const socket = ioClient.io(apiUrl, {
      transports: ['websocket', 'polling'],
      auth: {
        token: token,
      },
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    })

    socketRef.current = socket

    socket.on('connect', () => {
      console.log('Socket connected:', socket.id)
      setIsConnected(true)
      optionsRef.current.onConnect?.()
    })

    socket.on('disconnect', (reason) => {
      console.log('Socket disconnected:', reason)
      setIsConnected(false)
      optionsRef.current.onDisconnect?.()
    })

    socket.on('connect_error', (error) => {
      console.error('Socket connection error:', error)
      optionsRef.current.onError?.(error)
    })

    socket.on('new_message', (message: SocketMessage) => {
      console.log('New message received:', message)
      optionsRef.current.onNewMessage?.(message)
    })

    socket.on('new_private_message', (message: SocketMessage) => {
      console.log('New private message received:', message)
      optionsRef.current.onNewMessage?.(message)
    })

    socket.on('message_read', (data: { message_id: number; user_id: number }) => {
      console.log('Message read:', data)
      optionsRef.current.onMessageRead?.(data)
    })

    // Cleanup on unmount
    return () => {
      socket.disconnect()
      socketRef.current = null
    }
  }, [ioClient])

  const joinGroup = useCallback((groupId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) {
      console.warn('Cannot join group: socket not connected')
      return
    }
    socket.emit('join_group', { group_id: groupId }, (response: any) => {
      if (response?.success) {
        console.log('Joined group room:', groupId)
      } else {
        console.error('Failed to join group:', response?.error)
      }
    })
  }, [])

  const leaveGroup = useCallback((groupId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) return
    socket.emit('leave_group', { group_id: groupId })
  }, [])

  const joinConversation = useCallback((conversationId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) {
      console.warn('Cannot join conversation: socket not connected')
      return
    }
    socket.emit('join_conversation', { conversation_id: conversationId }, (response: any) => {
      if (response?.success) {
        console.log('Joined conversation:', conversationId)
      } else {
        console.error('Failed to join conversation:', response?.error)
      }
    })
  }, [])

  const leaveConversation = useCallback((conversationId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) return
    socket.emit('leave_conversation', { conversation_id: conversationId })
  }, [])

  const notifyNewMessage = useCallback((groupId: number, messageId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) return
    socket.emit('send_message', { group_id: groupId, message_id: messageId })
  }, [])

  const notifyPrivateMessage = useCallback((conversationId: number, messageId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) return
    socket.emit('send_private_message', { conversation_id: conversationId, message_id: messageId })
  }, [])

  const markMessageRead = useCallback((messageId: number) => {
    const socket = socketRef.current
    if (!socket || !socket.connected) return
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
