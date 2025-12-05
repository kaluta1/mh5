import * as React from "react"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {}

function Badge({ className, ...props }: BadgeProps) {
  return (
    <div
      className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${className}`}
      {...props}
    />
  )
}

export { Badge }
