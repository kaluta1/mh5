'use client'

import AdminContentModeration from '@/components/admin/admin-content-moderation'

export default function ContentModerationPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Content moderation</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">Review held contest content. Codes only; child-safety items need an authorized reviewer.</p>
      </div>
      <AdminContentModeration />
    </div>
  )
}
