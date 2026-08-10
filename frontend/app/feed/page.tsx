import { redirect } from 'next/navigation'

/** /feed without an id — send visitors to the dashboard feed. */
export default function FeedIndexPage() {
  redirect('/dashboard/feed')
}
