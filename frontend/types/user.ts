export interface UserRole {
  id: number
  name: string
  description?: string
}

export interface User {
  id: number
  email: string
  username?: string
  full_name?: string
  first_name?: string
  last_name?: string
  avatar_url?: string
  bio?: string
  
  // Demographics
  gender?: 'male' | 'female' | 'other' | 'prefer_not_to_say'
  date_of_birth?: string
  phone_number?: string
  
  // Location
  continent?: string
  region?: string
  country?: string
  city?: string
  
  // Verification & Status
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  identity_verified?: boolean
  address_verified?: boolean
  verification_date?: string
  status?: 'active' | 'suspended' | 'banned' | 'pending_verification'
  last_login?: string
  
  // Referral
  personal_referral_code?: string
  sponsor_id?: number
  
  // RBAC
  role_id?: number
  role?: UserRole
}
