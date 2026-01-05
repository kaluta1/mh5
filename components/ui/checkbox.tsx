"use client"

import * as React from "react"
import { Check } from "lucide-react"

interface CheckboxProps {
  id?: string
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  className?: string
  disabled?: boolean
}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ id, checked, onCheckedChange, className = "", disabled }, ref) => {
    return (
      <div className="relative inline-flex items-center">
        <input
          ref={ref}
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheckedChange?.(e.target.checked)}
          disabled={disabled}
          className="sr-only"
        />
        <div
          className={`
            h-4 w-4 shrink-0 rounded-sm border border-gray-300 dark:border-gray-600
            flex items-center justify-center cursor-pointer
            transition-colors duration-200
            ${checked 
              ? 'bg-blue-600 border-blue-600 text-white' 
              : 'bg-white dark:bg-gray-800 hover:border-blue-400'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
            focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2
            ${className}
          `}
          onClick={() => !disabled && onCheckedChange?.(!checked)}
        >
          {checked && <Check className="h-3 w-3" />}
        </div>
      </div>
    )
  }
)

Checkbox.displayName = "Checkbox"

export { Checkbox }
