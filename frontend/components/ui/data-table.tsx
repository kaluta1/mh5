'use client'

import React from 'react'
import { Card } from '@/components/ui/card'

export interface Column<T> {
  key: string
  header: string | React.ReactNode
  render: (item: T, index: number) => React.ReactNode
  className?: string
  headerClassName?: string
}

interface DataTableProps<T> {
  data: T[]
  columns: Column<T>[]
  emptyIcon?: React.ReactNode
  emptyTitle?: string
  emptyDescription?: string | React.ReactNode
  className?: string
  rowClassName?: string | ((item: T, index: number) => string)
  onRowClick?: (item: T, index: number) => void
}

export function DataTable<T extends { id?: string | number }>({
  data,
  columns,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  className = '',
  rowClassName = '',
  onRowClick
}: DataTableProps<T>) {
  if (data.length === 0) {
    return (
      <Card className="text-center py-12">
        {emptyIcon && <div className="mb-4">{emptyIcon}</div>}
        {emptyTitle && (
          <p className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">
            {emptyTitle}
          </p>
        )}
        {emptyDescription && (
          <div className="text-gray-500 dark:text-gray-400">
            {typeof emptyDescription === 'string' ? (
              <p>{emptyDescription}</p>
            ) : (
              emptyDescription
            )}
          </div>
        )}
      </Card>
    )
  }

  const getRowClassName = (item: T, index: number) => {
    const baseClass = 'border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors'
    const customClass = typeof rowClassName === 'function' ? rowClassName(item, index) : rowClassName
    const clickableClass = onRowClick ? 'cursor-pointer' : ''
    return `${baseClass} ${customClass} ${clickableClass}`.trim()
  }

  return (
    <Card className={`overflow-hidden ${className}`}>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={`px-6 py-4 text-left text-xs font-semibold text-gray-900 dark:text-white uppercase tracking-wider ${
                    column.headerClassName || ''
                  }`}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
            {data.map((item, index) => (
              <tr
                key={item.id || index}
                className={getRowClassName(item, index)}
                onClick={() => onRowClick?.(item, index)}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100 ${
                      column.className || ''
                    }`}
                  >
                    {column.render(item, index)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

