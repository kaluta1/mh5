'use client'

import * as React from "react"
import { cn } from "@/lib/utils"

interface TabsProps {
  value: string
  onValueChange: (value: string) => void
  children: React.ReactNode
  className?: string
}

interface TabsListProps {
  children: React.ReactNode
  className?: string
}

interface TabsTriggerProps {
  value: string
  children: React.ReactNode
  className?: string
}

interface TabsContentProps {
  value: string
  children: React.ReactNode
  className?: string
}

export const Tabs = React.forwardRef<HTMLDivElement, TabsProps>(
  ({ value, onValueChange, children, className }, ref) => (
    <div ref={ref} className={cn("w-full", className)}>
      {React.Children.map(children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(child as React.ReactElement<any>, {
              activeValue: value,
              onValueChange,
            })
          : child
      )}
    </div>
  )
)
Tabs.displayName = "Tabs"

export const TabsList = React.forwardRef<HTMLDivElement, TabsListProps & { activeValue?: string; onValueChange?: (value: string) => void }>(
  ({ children, className, activeValue, onValueChange }, ref) => (
    <div
      ref={ref}
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-md bg-muted p-1",
        className
      )}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(child as React.ReactElement<any>, {
              activeValue,
              onValueChange,
            })
          : child
      )}
    </div>
  )
)
TabsList.displayName = "TabsList"

export const TabsTrigger = React.forwardRef<HTMLButtonElement, TabsTriggerProps & { activeValue?: string; onValueChange?: (value: string) => void }>(
  ({ value, children, className, activeValue, onValueChange }, ref) => (
    <button
      ref={ref}
      onClick={() => onValueChange?.(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        activeValue === value
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  )
)
TabsTrigger.displayName = "TabsTrigger"

export const TabsContent = React.forwardRef<HTMLDivElement, TabsContentProps & { activeValue?: string }>(
  ({ value, children, className, activeValue }, ref) => (
    <div
      ref={ref}
      className={cn(
        "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        activeValue === value ? "block" : "hidden",
        className
      )}
    >
      {children}
    </div>
  )
)
TabsContent.displayName = "TabsContent"
