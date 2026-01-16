import { apiService } from '@/lib/api'

// Feed System Service - Uses new /api/v1/feed/* endpoints

export interface FeedPost {
  id: number
  author_id: number
  content?: string
  post_type: 'text' | 'image' | 'video' | 'link' | 'poll'
  visibility: 'public' | 'followers' | 'private' | 'group'
  group_id?: number
  location?: string
  tags?: string
  like_count: number
  comment_count: number
  share_count: number
  view_count: number
  is_pinned: boolean
  is_archived: boolean
  created_at: string
  updated_at: string
  media?: FeedPostMedia[]
}

export interface FeedPostMedia {
  id: number
  media_url: string
  media_type: string
  order: number
}

export interface FeedPostComment {
  id: number
  post_id: number
  author_id: number
  content: string
  parent_id?: number
  like_count: number
  reply_count: number
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface FeedGroup {
  id: number
  name: string
  description?: string
  group_type: 'public' | 'private' | 'secret'
  creator_id: number
  avatar_url?: string
  cover_url?: string
  max_members?: number
  invite_code?: string
  requires_approval: boolean
  member_count: number
  post_count: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateFeedPostRequest {
  content?: string
  post_type?: 'text' | 'image' | 'video' | 'link' | 'poll'
  visibility?: 'public' | 'followers' | 'private' | 'group'
  group_id?: number
  location?: string
  tags?: string
}

export interface CreateFeedGroupRequest {
  name: string
  description?: string
  group_type?: 'public' | 'private' | 'secret'
  max_members?: number
  requires_approval?: boolean
}

export interface CreateFeedCommentRequest {
  content: string
  parent_id?: number
}

export const feedService = {
  // Feed
  async getFeed(skip: number = 0, limit: number = 20): Promise<FeedPost[]> {
    return apiService.get(`/api/v1/feed?skip=${skip}&limit=${limit}`)
  },

  // Posts
  async getPosts(skip: number = 0, limit: number = 20, groupId?: number, authorId?: number): Promise<FeedPost[]> {
    const params: any = { skip, limit }
    if (groupId) params.group_id = groupId
    if (authorId) params.author_id = authorId
    return apiService.get('/api/v1/feed/posts', params)
  },

  async getPost(postId: number): Promise<FeedPost> {
    return apiService.get(`/api/v1/feed/posts/${postId}`)
  },

  async createPost(data: CreateFeedPostRequest): Promise<FeedPost> {
    return apiService.post('/api/v1/feed/posts', data)
  },

  async uploadPostMedia(postId: number, file: File): Promise<{ id: number; media_url: string; media_type: string; order: number }> {
    const formData = new FormData()
    formData.append('file', file)
    return apiService.post(`/api/v1/feed/posts/${postId}/media`, formData, undefined, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  },

  async createComment(postId: number, data: CreateFeedCommentRequest): Promise<FeedPostComment> {
    return apiService.post(`/api/v1/feed/posts/${postId}/comments`, data)
  },

  async toggleReaction(postId: number, reactionType: 'like' | 'love' | 'haha' | 'wow' | 'sad' | 'angry' = 'like'): Promise<void> {
    return apiService.post(`/api/v1/feed/posts/${postId}/reactions?reaction_type=${reactionType}`)
  },

  // Groups
  async getGroups(skip: number = 0, limit: number = 20, groupType?: 'public' | 'private' | 'secret'): Promise<FeedGroup[]> {
    const params: any = { skip, limit }
    if (groupType) params.group_type = groupType
    return apiService.get('/api/v1/feed/groups', params)
  },

  async getGroup(groupId: number): Promise<FeedGroup> {
    return apiService.get(`/api/v1/feed/groups/${groupId}`)
  },

  async createGroup(data: CreateFeedGroupRequest): Promise<FeedGroup> {
    return apiService.post('/api/v1/feed/groups', data)
  },

  async joinGroup(groupId: number, inviteCode?: string): Promise<void> {
    const params: any = {}
    if (inviteCode) params.invite_code = inviteCode
    return apiService.post(`/api/v1/feed/groups/${groupId}/join`, undefined, undefined, { params })
  },

  async leaveGroup(groupId: number): Promise<void> {
    return apiService.delete(`/api/v1/feed/groups/${groupId}/leave`)
  },
}
