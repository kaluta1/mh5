'use client'

import { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'

interface QuickActionCardProps {
  title: string
  description: string
  icon: LucideIcon
  href: string
  gradientFrom?: string
  gradientTo?: string
  iconColor?: string
}

export function QuickActionCard({
  title,
  description,
  icon: Icon,
  href,
  gradientFrom = 'from-blue-500',
  gradientTo = 'to-purple-600',
  iconColor = 'text-white'
}: QuickActionCardProps) {
  return (
    <Link href={href} className="block h-full">
      <Card className="h-full group relative overflow-hidden border-2 border-transparent hover:border-myfav-primary/30 dark:hover:border-myfav-blue-400/30 transition-all duration-300 hover:shadow-2xl hover:-translate-y-1 bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900">
        <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${gradientFrom} ${gradientTo}`} />
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className={`relative flex-shrink-0 w-16 h-16 rounded-2xl bg-gradient-to-br ${gradientFrom} ${gradientTo} flex items-center justify-center shadow-lg group-hover:scale-110 group-hover:rotate-3 transition-all duration-300`}>
              <Icon className={`w-8 h-8 ${iconColor}`} />
              <div className="absolute inset-0 rounded-2xl bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2 group-hover:text-myfav-primary dark:group-hover:text-myfav-blue-400 transition-colors">
                {title}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-2">
                {description}
              </p>
            </div>
            <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${gradientFrom} ${gradientTo} flex items-center justify-center`}>
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

