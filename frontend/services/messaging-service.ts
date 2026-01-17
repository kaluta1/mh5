import { apiService } from '@/lib/api'

// Messaging Service with E2E Encryption Support

export interface Conversation {
  id: number
  conversation_type: 'direct' | 'group'
  user1_id?: number
  user2_id?: number
  group_id?: number
  last_message_id?: number
  last_message_at?: string
  message_count: number
  unread_count_user1: number
  unread_count_user2: number
  created_at: string
  updated_at: string
}

export interface DecryptedMessage {
  id: number
  conversation_id: number
  sender_id: number
  content: string  // Decrypted content
  message_type: 'text' | 'image' | 'video' | 'file' | 'audio' | 'system'
  media_url?: string
  reply_to_id?: number
  status: 'sent' | 'delivered' | 'read' | 'deleted'
  is_edited: boolean
  created_at: string
  edited_at?: string
}

export interface SendMessageRequest {
  recipient_id: number
  content: string
  message_type?: 'text' | 'image' | 'video' | 'file' | 'audio'
  media_url?: string
  reply_to_id?: number
}

export interface EncryptionKeyPair {
  user_id: number
  public_key: string
  private_key?: string  // Only returned during generation
  message?: string
}

export const messagingService = {
  // Encryption Keys
  async generateKeys(): Promise<EncryptionKeyPair> {
    return apiService.post('/api/v1/feed/keys/generate')
  },

  async getPublicKey(userId: number): Promise<EncryptionKeyPair> {
    return apiService.get(`/api/v1/feed/keys/public/${userId}`)
  },

  // Conversations
  async getConversations(skip: number = 0, limit: number = 50): Promise<Conversation[]> {
    return apiService.get(`/api/v1/feed/messages/conversations?skip=${skip}&limit=${limit}`)
  },

  // Messages (decrypted)
  async getMessages(conversationId: number, skip: number = 0, limit: number = 50): Promise<DecryptedMessage[]> {
    return apiService.get(`/api/v1/feed/messages/conversations/${conversationId}/messages?skip=${skip}&limit=${limit}`)
  },

  // Send message (will be encrypted on backend)
  async sendMessage(data: SendMessageRequest): Promise<DecryptedMessage> {
    return apiService.post('/api/v1/feed/messages/send', data)
  },

  // Mark message as read
  async markAsRead(messageId: number): Promise<void> {
    return apiService.post(`/api/v1/feed/messages/${messageId}/read`)
  },

  // Delete message
  async deleteMessage(messageId: number): Promise<void> {
    return apiService.delete(`/api/v1/feed/messages/${messageId}`)
  },
}
