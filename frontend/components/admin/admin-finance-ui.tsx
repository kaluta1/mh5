import { humanize, tone } from '@/lib/finance-admin'

// Small presentational pieces shared by the Finance & Payments admin sections.

export const inputClass = 'w-full px-3 py-2 border rounded-md bg-white dark:bg-gray-800 text-sm border-gray-300 dark:border-gray-700'

const TONES = {
  green: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  red: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

export function StatusPill({ status, children }: { status: string | null | undefined; children?: React.ReactNode }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${TONES[tone(status)]}`}>
      {children ?? humanize(status)}
    </span>
  )
}

export function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium text-right text-gray-900 dark:text-white">{value}</dd>
    </div>
  )
}
