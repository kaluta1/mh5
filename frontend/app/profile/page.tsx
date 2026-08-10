import { redirect } from 'next/navigation'

/** Legacy /profile bookmark — settings is the closest account hub. */
export default function ProfileLegacyPage() {
  redirect('/dashboard/settings')
}
