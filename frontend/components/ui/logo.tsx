"use client"

import Image from "next/image"
import Link from "next/link"
import { Heart } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"

interface LogoProps {
  className?: string
  showText?: boolean
  size?: "sm" | "md" | "lg"
  href?: string
}

const sizeMap = {
  sm: {
    icon: "w-6 h-6",
    text: "text-lg",
    container: "h-8"
  },
  md: {
    icon: "w-10 h-10",
    text: "text-xl",
    container: "h-12"
  },
  lg: {
    icon: "w-14 h-14",
    text: "text-2xl",
    container: "h-16"
  }
}

export function Logo({ 
  className, 
  showText = true, 
  size = "md",
  href = "/"
}: LogoProps) {
  const sizes = sizeMap[size]
  const [logoError, setLogoError] = useState(false)
  
  const LogoContent = () => (
    <div className={cn("flex items-center space-x-2.5 group", className)}>
      <div className="relative">
        {/* Try to load official logo, fallback to icon */}
        <div className={cn(
          "rounded-xl flex items-center justify-center bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary shadow-lg group-hover:shadow-xl transition-all duration-300 group-hover:scale-105",
          sizes.icon
        )}>
          {/* Official Logo Image */}
          {!logoError ? (
            <Image
              src="/logo.png"
              alt="MyHigh5 Logo"
              width={size === "sm" ? 24 : size === "md" ? 40 : 56}
              height={size === "sm" ? 24 : size === "md" ? 40 : 56}
              className="object-contain p-1"
              onError={() => {
                // Fallback to icon if logo doesn't exist
                setLogoError(true)
              }}
            />
          ) : (
            <Heart className={cn("text-white fill-current", size === "sm" ? "w-4 h-4" : size === "md" ? "w-5 h-5" : "w-7 h-7")} />
          )}
        </div>
        <div className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-gray-900 animate-pulse" />
      </div>
      {showText && (
        <div className="flex flex-col">
          <span className={cn(
            "font-black bg-gradient-to-r from-myhigh5-primary to-myhigh5-secondary bg-clip-text text-transparent",
            sizes.text
          )}>
            MyHigh5
          </span>
          <span className={cn(
            "font-medium text-gray-500 dark:text-gray-400 -mt-1 hidden sm:block",
            size === "sm" ? "text-[8px]" : size === "md" ? "text-[10px]" : "text-xs"
          )}>
            Global Contest Platform
          </span>
        </div>
      )}
    </div>
  )

  if (href) {
    return (
      <Link href={href} className="inline-block">
        <LogoContent />
      </Link>
    )
  }

  return <LogoContent />
}
