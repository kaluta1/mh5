import { apiService } from '@/lib/api'

export interface Post {
  id: number
  author_id: number
  author?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  content: string
  visibility: 'public' | 'followers' | 'private'
  media?: PostMedia[]
  poll?: Poll
  likes_count: number
  comments_count: number
  shares_count: number
  reactions_count: number
  is_liked: boolean
  is_shared: boolean
  user_reaction?: string
  created_at: string
  updated_at: string
}

export interface PostMedia {
  id: number
  post_id: number
  media_id: number
  media_type: 'image' | 'video'
  url: string
  thumbnail_url?: string
  order: number
}

export interface Poll {
  id: number
  post_id: number
  question: string
  options: PollOption[]
  expires_at?: string
  total_votes: number
  user_vote?: number
}

export interface PollOption {
  id: number
  poll_id: number
  text: string
  votes_count: number
  percentage: number
}

export interface PostComment {
  id: number
  post_id: number
  author_id: number
  author?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  content: string
  parent_id?: number
  replies?: PostComment[]
  likes_count: number
  is_liked: boolean
  created_at: string
  updated_at: string
}

export interface PostReaction {
  id: number
  post_id: number
  user_id: number
  reaction_type: 'like' | 'love' | 'laugh' | 'wow' | 'sad' | 'angry'
  created_at: string
}

export interface SocialGroup {
  id: number
  name: string
  description?: string
  creator_id: number
  creator?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  avatar_url?: string
  is_private: boolean
  members_count: number
  is_member: boolean
  created_at: string
}

export interface PrivateConversation {
  id: number
  user1_id: number
  user2_id: number
  user1?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  user2?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  group_id?: number
  group?: SocialGroup
  last_message?: PrivateMessage
  unread_count: number
  updated_at: string
}

export interface PrivateMessage {
  id: number
  conversation_id: number
  sender_id: number
  sender?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
  content: string
  message_type: 'text' | 'image' | 'video' | 'file'
  media_id?: number
  media_url?: string
  reply_to_id?: number
  reply_to?: PrivateMessage
  is_read: boolean
  created_at: string
}

export interface CreatePostRequest {
  content: string
  visibility: 'public' | 'followers' | 'private'
  media_ids?: number[]
  poll?: {
    question: string
    options: string[]
    expires_at?: string
  }
}

export interface CreateCommentRequest {
  content: string
  parent_id?: number
}

export interface CreateGroupRequest {
  name: string
  description?: string
  is_private: boolean
  avatar_url?: string
}

export const socialService = {
  // Posts
  async getFeed(skip: number = 0, limit: number = 20): Promise<Post[]> {
    return apiService.get(`/api/v1/social/posts/feed?skip=${skip}&limit=${limit}`)
  },

  async getPost(postId: number): Promise<Post> {
    return apiService.get(`/api/v1/social/posts/${postId}`)
  },

  async createPost(data: CreatePostRequest): Promise<Post> {
    return apiService.post('/api/v1/social/posts', data)
  },

  async updatePost(postId: number, data: Partial<CreatePostRequest>): Promise<Post> {
    return apiService.put(`/api/v1/social/posts/${postId}`, data)
  },

  async deletePost(postId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/posts/${postId}`)
  },

  async likePost(postId: number): Promise<void> {
    return apiService.post(`/api/v1/social/posts/${postId}/like`)
  },

  async unlikePost(postId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/posts/${postId}/like`)
  },

  async reactToPost(postId: number, reactionType: string): Promise<void> {
    return apiService.post(`/api/v1/social/posts/${postId}/react`, { reaction_type: reactionType })
  },

  async sharePost(postId: number): Promise<void> {
    return apiService.post(`/api/v1/social/posts/${postId}/share`)
  },

  // Comments
  async getPostComments(postId: number, skip: number = 0, limit: number = 50): Promise<PostComment[]> {
    return apiService.get(`/api/v1/social/posts/${postId}/comments?skip=${skip}&limit=${limit}`)
  },

  async createComment(postId: number, data: CreateCommentRequest): Promise<PostComment> {
    return apiService.post(`/api/v1/social/posts/${postId}/comments`, data)
  },

  async updateComment(commentId: number, content: string): Promise<PostComment> {
    return apiService.put(`/api/v1/social/comments/${commentId}`, { content })
  },

  async deleteComment(commentId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/comments/${commentId}`)
  },

  async likeComment(commentId: number): Promise<void> {
    return apiService.post(`/api/v1/social/comments/${commentId}/like`)
  },

  // Polls
  async votePoll(pollId: number, optionId: number): Promise<void> {
    return apiService.post(`/api/v1/social/polls/${pollId}/vote`, { option_id: optionId })
  },

  // Groups
  async getGroups(skip: number = 0, limit: number = 20): Promise<SocialGroup[]> {
    return apiService.get(`/api/v1/social/groups?skip=${skip}&limit=${limit}`)
  },

  async getGroup(groupId: number): Promise<SocialGroup> {
    return apiService.get(`/api/v1/social/groups/${groupId}`)
  },

  async createGroup(data: CreateGroupRequest): Promise<SocialGroup> {
    return apiService.post('/api/v1/social/groups', data)
  },

  async joinGroup(groupId: number): Promise<void> {
    return apiService.post(`/api/v1/social/groups/${groupId}/join`)
  },

  async leaveGroup(groupId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/groups/${groupId}/leave`)
  },

  // Private Messages
  async getConversations(): Promise<PrivateConversation[]> {
    return apiService.get('/api/v1/private-messages/conversations')
  },

  async getConversation(conversationId: number): Promise<PrivateConversation> {
    return apiService.get(`/api/v1/private-messages/conversations/${conversationId}`)
  },

  async getMessages(conversationId: number, skip: number = 0, limit: number = 50): Promise<PrivateMessage[]> {
    return apiService.get(`/api/v1/private-messages/conversations/${conversationId}/messages?skip=${skip}&limit=${limit}`)
  },

  async sendMessage(conversationId: number, data: { content: string; message_type?: string; media_id?: number; reply_to_id?: number }): Promise<PrivateMessage> {
    return apiService.post(`/api/v1/private-messages/conversations/${conversationId}/messages`, data)
  },

  async markAsRead(conversationId: number, messageId: number): Promise<void> {
    return apiService.post(`/api/v1/private-messages/conversations/${conversationId}/messages/${messageId}/read`)
  },

  async createConversation(userId: number): Promise<PrivateConversation> {
    return apiService.post('/api/v1/private-messages/conversations', { user_id: userId })
  }
}

