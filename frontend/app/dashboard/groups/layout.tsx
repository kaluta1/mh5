/**
 * Groups need min-w-0 so flex children truncate instead of clipping under the sidebar.
 */
export default function GroupsLayout({ children }: { children: React.ReactNode }) {
  return <div className="w-full min-w-0 max-w-full overflow-x-hidden">{children}</div>
}
