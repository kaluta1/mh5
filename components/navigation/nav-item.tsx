"use client"

import * as React from "react"
import Link from "next/link"
import { cn } from "@/lib/utils"

interface NavItemProps {
  href: string
  children: React.ReactNode
  className?: string
  active?: boolean
  onClick?: () => void
}

export function NavItem({ href, children, className, active, onClick }: NavItemProps) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none disabled:pointer-events-none disabled:opacity-50",
        active && "bg-accent text-accent-foreground",
        className
      )}
      onClick={onClick}
    >
      {children}
    </Link>
  )
}
