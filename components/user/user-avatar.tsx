"use client"

import * as React from "react"
import { User } from "lucide-react"
import { cn } from "@/lib/utils"

interface UserAvatarProps {
  src?: string
  alt?: string
  user?: {
    id?: number
    username?: string
    full_name?: string
    avatar_url?: string
  }
  size?: "sm" | "md" | "lg" | "xl"
  className?: string
  fallback?: string
}

export function UserAvatar({ 
  src, 
  alt, 
  user,
  size = "md", 
  className,
  fallback 
}: UserAvatarProps) {
  const avatarSrc = src || user?.avatar_url
  const avatarAlt = alt || user?.full_name || user?.username || "User avatar"
  const avatarFallback = fallback || user?.username?.[0]?.toUpperCase() || user?.full_name?.[0]?.toUpperCase() || "U"
  const sizeClasses = {
    sm: "h-8 w-8",
    md: "h-10 w-10",
    lg: "h-12 w-12",
    xl: "h-16 w-16"
  }

  const iconSizes = {
    sm: "h-4 w-4",
    md: "h-5 w-5", 
    lg: "h-6 w-6",
    xl: "h-8 w-8"
  }

  return (
    <div 
      className={cn(
        "relative inline-flex items-center justify-center rounded-full bg-muted overflow-hidden",
        sizeClasses[size],
        className
      )}
    >
      {avatarSrc ? (
        <img
          src={avatarSrc}
          alt={avatarAlt}
          className="h-full w-full object-cover"
        />
      ) : avatarFallback ? (
        <span className="text-sm font-medium text-muted-foreground">
          {avatarFallback}
        </span>
      ) : (
        <User className={cn("text-muted-foreground", iconSizes[size])} />
      )}
    </div>
  )
}
