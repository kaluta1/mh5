"use client"

import * as React from "react"
import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface NavIconProps {
  icon: LucideIcon
  className?: string
  size?: "sm" | "md" | "lg"
}

export function NavIcon({ icon: Icon, className, size = "md" }: NavIconProps) {
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-5 w-5", 
    lg: "h-6 w-6"
  }

  return (
    <Icon 
      className={cn(
        sizeClasses[size],
        "text-muted-foreground",
        className
      )} 
    />
  )
}
