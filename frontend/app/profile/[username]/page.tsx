import { redirect } from 'next/navigation'

/** Legacy shared links: /profile/{username} → public profile flow. */
export default async function LegacyProfileUsernamePage({
  params,
  searchParams,
}: {
  params: Promise<{ username: string }>
  searchParams: Promise<{ ref?: string }>
}) {
  const { username } = await params
  const { ref } = await searchParams
  const qs = ref ? `?ref=${encodeURIComponent(ref)}` : ''
  redirect(`/${encodeURIComponent(username)}${qs}`)
}
