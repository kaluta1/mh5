import api, { apiService } from '@/lib/api'

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

export interface GroupMember {
  id: number
  group_id: number
  user_id: number
  role: string
  joined_at: string
  is_muted: boolean
  is_banned: boolean
  user?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
}

export interface GroupMessage {
  id: number
  group_id: number
  sender_id: number
  content?: string
  message_type: 'text' | 'image' | 'video' | 'file' | 'audio' | 'system'
  media_id?: number
  reply_to_id?: number
  status: string
  is_edited: boolean
  is_deleted: boolean
  created_at: string
  updated_at: string
  sender?: {
    id: number
    username: string
    full_name?: string
    avatar_url?: string
  }
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

function normalizePost(post: any): Post {
  return {
    id: post.id,
    author_id: post.author_id,
    author: post.author,
    content: post.content || '',
    visibility: post.visibility || 'public',
    media: Array.isArray(post.media)
      ? post.media.map((item: any, index: number) => ({
          id: item.id,
          post_id: item.post_id ?? post.id,
          media_id: item.media_id ?? 0,
          media_type: item.media_type || 'image',
          url: item.url || item.media_url || '',
          thumbnail_url: item.thumbnail_url,
          order: item.order ?? index,
        }))
      : [],
    poll: post.poll,
    likes_count: post.likes_count ?? post.like_count ?? 0,
    comments_count: post.comments_count ?? post.comment_count ?? 0,
    shares_count: post.shares_count ?? post.share_count ?? 0,
    reactions_count: post.reactions_count ?? 0,
    is_liked: post.is_liked ?? post.user_reaction === 'like',
    is_shared: post.is_shared ?? false,
    user_reaction: typeof post.user_reaction === 'string' ? post.user_reaction : undefined,
    created_at: post.created_at,
    updated_at: post.updated_at,
  }
}

export const socialService = {
  // Posts - Legacy endpoints (keeping for backward compatibility)
  // For new feed system, use feedService from './feed-service'
  async getFeed(skip: number = 0, limit: number = 20): Promise<Post[]> {
    const response = await apiService.get<{ posts?: any[] }>(`/api/v1/social/posts?skip=${skip}&limit=${limit}`)
    return Array.isArray(response?.posts) ? response.posts.map(normalizePost) : []
  },

  async getPost(postId: number): Promise<Post> {
    const response = await apiService.get<any>(`/api/v1/social/posts/${postId}`)
    return normalizePost(response)
  },

  async createPost(data: CreatePostRequest): Promise<Post> {
    const response = await apiService.post<any>('/api/v1/social/posts', data)
    return normalizePost(response)
  },

  async updatePost(postId: number, data: Partial<CreatePostRequest>): Promise<Post> {
    const response = await apiService.put<any>(`/api/v1/social/posts/${postId}`, data)
    return normalizePost(response)
  },

  async deletePost(postId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/posts/${postId}`)
  },

  async likePost(postId: number): Promise<void> {
    return apiService.post(`/api/v1/social/posts/${postId}/reactions?reaction_type=like`)
  },

  async unlikePost(postId: number): Promise<void> {
    return apiService.delete(`/api/v1/social/posts/${postId}/reactions`)
  },

  async reactToPost(postId: number, reactionType: string): Promise<void> {
    return apiService.post(`/api/v1/social/posts/${postId}/reactions?reaction_type=${encodeURIComponent(reactionType)}`)
  },

  async sharePost(postId: number): Promise<void> {
    const response = await api.post(`/api/v1/social/posts/${postId}/shares`, {})
    if (response.status < 200 || response.status >= 300) {
      const data = response.data as { detail?: string | unknown }
      const detail = data?.detail
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? (detail[0] as { msg?: string })?.msg || 'Share failed'
            : 'Could not record repost'
      throw new Error(msg)
    }
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

  // Groups - Updated to use new feed endpoints
  async getGroups(skip: number = 0, limit: number = 20): Promise<SocialGroup[]> {
    const groups = await apiService.get(`/api/v1/feed/groups?skip=${skip}&limit=${limit}`) as any[]
    // Map backend response to frontend format
    return groups.map((g: any) => ({
      ...g,
      is_private: g.group_type === 'private',
      members_count: g.member_count || 0,
    })) as SocialGroup[]
  },

  async getGroup(groupId: number): Promise<SocialGroup> {
    const group = await apiService.get(`/api/v1/feed/groups/${groupId}`) as any
    // Map backend response to frontend format
    return {
      ...group,
      is_private: group.group_type === 'private',
      members_count: group.member_count || 0,
    } as SocialGroup
  },

  async createGroup(data: CreateGroupRequest): Promise<SocialGroup> {
    // Map old format to new format
    const newData = {
      name: data.name,
      description: data.description,
      group_type: data.is_private ? 'private' : 'public' as 'public' | 'private' | 'secret',
    }
    const response = await apiService.post('/api/v1/feed/groups', newData) as any
    // Map backend response to frontend format
    return {
      ...response,
      is_private: response.group_type === 'private',
      members_count: response.member_count || 0,
    } as SocialGroup
  },

  async joinGroup(groupId: number, inviteCode?: string): Promise<void> {
    const url = inviteCode
      ? `/api/v1/feed/groups/${groupId}/join?invite_code=${encodeURIComponent(inviteCode)}`
      : `/api/v1/feed/groups/${groupId}/join`
    return apiService.post(url)
  },

  async leaveGroup(groupId: number): Promise<void> {
    return apiService.delete(`/api/v1/feed/groups/${groupId}/leave`)
  },

  async getGroupMembers(groupId: number): Promise<GroupMember[]> {
    return apiService.get(`/api/v1/feed/groups/${groupId}/members`)
  },

  async getGroupMessages(
    groupId: number,
    skip: number = 0,
    limit: number = 50,
    search?: string,
  ): Promise<GroupMessage[]> {
    const q = new URLSearchParams({ skip: String(skip), limit: String(limit) })
    if (search?.trim()) q.set('search', search.trim())
    const response = await apiService.get(
      `/api/v1/social/groups/${groupId}/messages?${q.toString()}`,
    ) as any
    return response?.messages || []
  },

  /** Update group (name, description, avatar, …) — feed API; admins/owners only. */
  async updateFeedGroup(
    groupId: number,
    data: { name?: string; description?: string; avatar_url?: string | null },
  ): Promise<SocialGroup> {
    const response = await apiService.put(`/api/v1/feed/groups/${groupId}`, data) as any
    return {
      ...response,
      is_private: response.group_type === 'private',
      members_count: response.member_count || 0,
    } as SocialGroup
  },

  /** Add member by @username — admins/owners only. */
  async addGroupMemberByUsername(groupId: number, username: string): Promise<void> {
    await apiService.post(`/api/v1/feed/groups/${groupId}/members/by-username`, { username })
  },

  /** Remove a member — admins (members only) or owner. */
  async removeGroupMember(groupId: number, userId: number): Promise<void> {
    await apiService.delete(`/api/v1/feed/groups/${groupId}/members/${userId}`)
  },

  /** Promote to admin or demote to member — owner required to demote an admin. */
  async updateGroupMemberRole(
    groupId: number,
    userId: number,
    role: 'member' | 'admin',
  ): Promise<GroupMember> {
    return apiService.patch(`/api/v1/feed/groups/${groupId}/members/${userId}`, { role }) as Promise<GroupMember>
  },

  async sendGroupMessage(groupId: number, data: { content: string; message_type?: string; media_id?: number; reply_to_id?: number }): Promise<GroupMessage> {
    return apiService.post(`/api/v1/social/groups/${groupId}/messages`, data)
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

