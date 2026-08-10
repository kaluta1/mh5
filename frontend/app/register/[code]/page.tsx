import { redirect } from 'next/navigation'

/** Legacy referral URLs: /register/ABC123 → /register?ref=ABC123 */
export default async function RegisterReferralPage({
  params,
}: {
  params: Promise<{ code: string }>
}) {
  const { code } = await params
  redirect(`/register?ref=${encodeURIComponent(code)}`)
}
