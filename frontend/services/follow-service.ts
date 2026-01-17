import { apiService } from '@/lib/api'

// Follow/Following Service

export interface User {
  id: number
  username: string
  full_name?: string
  avatar_url?: string
  bio?: string
  is_following?: boolean
  is_followed_by?: boolean
  followers_count?: number
  following_count?: number
  posts_count?: number
}

export interface FollowRequest {
  user_id: number
}

export const followService = {
  // Get user's followers
  async getFollowers(userId: number, skip: number = 0, limit: number = 50): Promise<User[]> {
    const safeLimit = Math.min(limit, 100)
    return apiService.get(`/api/v1/users/${userId}/followers?skip=${skip}&limit=${safeLimit}`)
  },

  // Get users that user is following
  async getFollowing(userId: number, skip: number = 0, limit: number = 50): Promise<User[]> {
    const safeLimit = Math.min(limit, 100)
    return apiService.get(`/api/v1/users/${userId}/following?skip=${skip}&limit=${safeLimit}`)
  },

  // Follow a user
  async followUser(userId: number): Promise<void> {
    return apiService.post('/api/v1/follow', { user_id: userId })
  },

  // Unfollow a user
  async unfollowUser(userId: number): Promise<void> {
    return apiService.delete(`/api/v1/follow/${userId}`)
  },

  // Get suggested users to follow
  async getSuggestedUsers(skip: number = 0, limit: number = 20): Promise<User[]> {
    return apiService.get(`/api/v1/users/suggested?skip=${skip}&limit=${limit}`)
  },
}
