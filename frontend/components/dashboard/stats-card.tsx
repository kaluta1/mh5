'use client'

import { LucideIcon } from 'lucide-react'

interface StatsCardProps {
  icon: LucideIcon
  title: string
  value: string | number
  subtitle?: string
  iconBgColor?: string
  iconColor?: string
  trend?: {
    value: number
    isPositive: boolean
  }
}

export function StatsCard({
  icon: Icon,
  title,
  value,
  subtitle,
  iconBgColor = 'bg-myhigh5-blue-100 dark:bg-myhigh5-blue-900/50',
  iconColor = 'text-myhigh5-primary dark:text-myhigh5-blue-400',
  trend
}: StatsCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow duration-300">
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-4 flex-1">
          <div className={`w-12 h-12 ${iconBgColor} rounded-xl flex items-center justify-center flex-shrink-0`}>
            <Icon className={`w-6 h-6 ${iconColor}`} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
              {title}
            </p>
            <h3 className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {value}
            </h3>
            {subtitle && (
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        
        {trend && (
          <div className={`flex items-center space-x-1 px-2 py-1 rounded-lg ${
            trend.isPositive 
              ? 'bg-green-100 dark:bg-green-900/30' 
              : 'bg-red-100 dark:bg-red-900/30'
          }`}>
            <span className={`text-sm font-semibold ${
              trend.isPositive 
                ? 'text-green-600 dark:text-green-400' 
                : 'text-red-600 dark:text-red-400'
            }`}>
              {trend.isPositive ? '+' : '-'}{Math.abs(trend.value)}%
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
