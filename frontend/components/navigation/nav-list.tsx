"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

interface NavListProps {
  children: React.ReactNode
  className?: string
  direction?: "horizontal" | "vertical"
}

export function NavList({ children, className, direction = "horizontal" }: NavListProps) {
  return (
    <nav
      className={cn(
        "flex",
        direction === "horizontal" ? "flex-row space-x-1" : "flex-col space-y-1",
        className
      )}
    >
      {children}
    </nav>
  )
}
