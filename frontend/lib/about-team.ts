/**
 * Public "Our Team" entries for the About pages.
 *
 * Only `published` entries are rendered. An entry is published only once its designation and
 * an authorised photograph of that person are supplied; a placeholder photo of someone else is
 * never used.
 */
export type AboutTeamMember = {
  name: string
  /** Key into the page's team label map; null until a verified designation is supplied. */
  roleKey: string | null
  /** Authorised photograph under /public/team; null until supplied. */
  image: string | null
  published: boolean
}

export const ABOUT_TEAM_MEMBERS: AboutTeamMember[] = [
  { name: "Shafi Kaluta Abedi", roleKey: "team.founder_president", image: "/team/shafi-kaluta-abedi.png", published: true },
  // Authorised profile and photograph supplied by the client (2026-09-28).
  { name: "Md Shakil Ahsan", roleKey: "team.director_ict", image: "/team/md-shakil-ahsan.jpg", published: true },
]

export function publishedTeamMembers(members: AboutTeamMember[] = ABOUT_TEAM_MEMBERS): AboutTeamMember[] {
  return members.filter((m) => m.published)
}
