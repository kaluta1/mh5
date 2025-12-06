"use client"

import * as React from "react"
import Image from "next/image"
import { LogOut, Settings, User, Shield } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useLanguage } from "@/contexts/language-context"

interface UserDropdownProps {
  user: {
    username?: string
    name?: string
    first_name?: string
    last_name?: string
    full_name?: string
    email?: string
    avatar?: string
    avatar_url?: string
    profile_photo?: string
  }
  onLogout?: () => void
  onSettings?: () => void
  onProfile?: () => void
  onKYC?: () => void
}

export function UserDropdown({ user, onLogout, onSettings, onProfile, onKYC }: UserDropdownProps) {
  const { t } = useLanguage()
  
  // Construct display name from available fields
  const displayName = user.first_name && user.last_name 
    ? `${user.first_name} ${user.last_name}`
    : user.full_name || user.name || user.username || 'Utilisateur'
  
  const initials = displayName
    ? displayName
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : 'U'
  
  const avatarUrl = user.avatar_url || user.profile_photo || user.avatar

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center rounded-full focus:outline-none focus:ring-2 focus:ring-myfav-primary/50 transition-all hover:opacity-80">
          {avatarUrl ? (
            <div className="relative w-10 h-10 rounded-full overflow-hidden ring-2 ring-myfav-primary/30 shadow-lg">
              <Image
                src={avatarUrl}
                alt={displayName}
                fill
                className="object-cover"
              />
            </div>
          ) : (
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-myfav-primary to-purple-600 flex items-center justify-center text-white font-semibold text-sm ring-2 ring-myfav-primary/30 shadow-lg">
              {initials}
            </div>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent 
        className="w-56 max-w-[calc(100vw-2rem)] rounded-xl shadow-xl border-gray-100 dark:border-gray-800" 
        align="end" 
        forceMount
        side="bottom"
        sideOffset={8}
        alignOffset={-8}
      >
        <DropdownMenuLabel className="font-normal px-3 py-2">
          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
            {displayName}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {user.email}
          </p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        
        <DropdownMenuItem onClick={onSettings} className="cursor-pointer rounded-lg mx-1 my-0.5">
          <Settings className="mr-2 h-4 w-4 text-gray-500" />
          <span>{t('user.settings')}</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onKYC} className="cursor-pointer rounded-lg mx-1 my-0.5">
          <Shield className="mr-2 h-4 w-4 text-gray-500" />
          <span>{t('user.kyc')}</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onLogout} className="cursor-pointer rounded-lg mx-1 my-0.5 text-red-600 focus:text-red-600 focus:bg-red-50 dark:focus:bg-red-950/20">
          <LogOut className="mr-2 h-4 w-4" />
          <span>{t('user.logout')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
