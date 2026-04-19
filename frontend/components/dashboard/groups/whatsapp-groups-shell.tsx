"use client"

import * as React from "react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowLeft,
  Globe,
  Info,
  Loader2,
  Lock,
  MessageCircle,
  MoreVertical,
  Plus,
  Search,
  Send,
  Settings,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { UserAvatar } from "@/components/user/user-avatar"
import { cn } from "@/lib/utils"
import {
  socialService,
  SocialGroup,
  GroupMember,
  GroupMessage,
  CreateGroupRequest,
} from "@/services/social-service"
import { useAuth } from "@/hooks/use-auth"
import { useLanguage } from "@/contexts/language-context"
import { useToast } from "@/components/ui/toast"

type ListFilter = "all" | "joined"

/** Use when i18n key may be missing — `t()` returns the key string in that case. */
function tf(t: (key: string) => string, key: string, fallback: string): string {
  const v = t(key)
  return v === key ? fallback : v
}

function roleLabelText(
  role: string | null | undefined,
  t: (key: string) => string,
): string {
  const r = (role || "").toLowerCase()
  switch (r) {
    case "owner":
      return tf(t, "dashboard.groups.role_owner", "Owner")
    case "admin":
      return tf(t, "dashboard.groups.role_admin", "Admin")
    case "moderator":
      return tf(t, "dashboard.groups.role_moderator", "Moderator")
    case "member":
      return tf(t, "dashboard.groups.role_member", "Group member")
    default:
      return r ? r : ""
  }
}

function parseApiDate(value: string) {
  if (!value) return new Date()
  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(value)) return new Date(value)
  return new Date(`${value}Z`)
}

function formatListTime(iso: string) {
  const d = parseApiDate(iso)
  const now = new Date()
  const sameDay =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear()
  if (sameDay) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  return d.toLocaleDateString([], { month: "short", day: "numeric" })
}

export function WhatsAppGroupsShell() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const { addToast } = useToast()
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedParam = searchParams.get("g")

  const [groups, setGroups] = useState<SocialGroup[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listFilter, setListFilter] = useState<ListFilter>("all")
  const [listQuery, setListQuery] = useState("")
  const [previews, setPreviews] = useState<
    Record<number, { text: string; time: string }>
  >({})

  const selectedId = selectedParam ? Number(selectedParam) : null
  const selectedGroup = useMemo(
    () => groups.find((g) => g.id === selectedId) ?? null,
    [groups, selectedId],
  )

  const [mobilePanel, setMobilePanel] = useState<"list" | "chat">("list")

  const [members, setMembers] = useState<GroupMember[]>([])
  const [messages, setMessages] = useState<GroupMessage[]>([])
  const [msgLoading, setMsgLoading] = useState(false)
  const [messageText, setMessageText] = useState("")
  const [sending, setSending] = useState(false)

  const [chatSearchOpen, setChatSearchOpen] = useState(false)
  const [chatSearch, setChatSearch] = useState("")
  const [debouncedChatSearch, setDebouncedChatSearch] = useState("")

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")
  const [savingSettings, setSavingSettings] = useState(false)

  const [addUserOpen, setAddUserOpen] = useState(false)
  const [addUsername, setAddUsername] = useState("")
  const [addingUser, setAddingUser] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [newGroup, setNewGroup] = useState<CreateGroupRequest>({
    name: "",
    description: "",
    is_private: false,
  })
  const [creating, setCreating] = useState(false)

  const [groupInfoOpen, setGroupInfoOpen] = useState(false)
  const [previewMembers, setPreviewMembers] = useState<GroupMember[]>([])
  const [previewMembersLoading, setPreviewMembersLoading] = useState(false)
  const [joining, setJoining] = useState(false)
  const [inviteCode, setInviteCode] = useState("")

  useEffect(() => {
    setPreviewMembers([])
    setInviteCode("")
  }, [selectedId])

  useEffect(() => {
    if (!groupInfoOpen || !selectedId || Number.isNaN(selectedId) || !selectedGroup) {
      return
    }
    if (selectedGroup.is_member || selectedGroup.is_private) {
      return
    }
    let cancel = false
    setPreviewMembersLoading(true)
    ;(async () => {
      try {
        const mem = await socialService.getGroupMembers(selectedId)
        if (!cancel) setPreviewMembers(mem)
      } catch {
        if (!cancel) setPreviewMembers([])
      } finally {
        if (!cancel) setPreviewMembersLoading(false)
      }
    })()
    return () => {
      cancel = true
    }
  }, [groupInfoOpen, selectedId, selectedGroup])

  useEffect(() => {
    const t = window.setTimeout(
      () => setDebouncedChatSearch(chatSearch.trim()),
      320,
    )
    return () => window.clearTimeout(t)
  }, [chatSearch])

  const loadGroups = useCallback(async () => {
    setListLoading(true)
    try {
      const data = await socialService.getGroups(0, 80)
      setGroups(data)
    } catch (e) {
      console.error(e)
      addToast(tf(t, "errors.generic", "Failed to load groups"), "error")
    } finally {
      setListLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    void loadGroups()
  }, [loadGroups])

  useEffect(() => {
    if (selectedParam) setMobilePanel("chat")
  }, [selectedParam])

  // Ensure group in list when deep-linking ?g=
  useEffect(() => {
    if (!selectedId || Number.isNaN(selectedId)) return
    if (groups.some((g) => g.id === selectedId)) return
    let cancel = false
    ;(async () => {
      try {
        const g = await socialService.getGroup(selectedId)
        if (!cancel) {
          setGroups((prev) =>
            prev.some((x) => x.id === g.id) ? prev : [g, ...prev],
          )
        }
      } catch {
        /* 404 */
      }
    })()
    return () => {
      cancel = true
    }
  }, [selectedId, groups])

  // Last message previews for joined groups
  useEffect(() => {
    if (!groups.length) return
    let cancel = false
    const run = async () => {
      const memberGroups = groups.filter((g) => g.is_member).slice(0, 24)
      const next: Record<number, { text: string; time: string }> = {}
      await Promise.all(
        memberGroups.map(async (g) => {
          try {
            const msgs = await socialService.getGroupMessages(g.id, 0, 1)
            const m = msgs[0]
            if (m && !cancel) {
              next[g.id] = {
                text: (m.content || "").replace(/\s+/g, " ").slice(0, 72),
                time: m.created_at,
              }
            }
          } catch {
            /* ignore */
          }
        }),
      )
      if (!cancel) setPreviews((p) => ({ ...p, ...next }))
    }
    void run()
    return () => {
      cancel = true
    }
  }, [groups])

  const selectGroup = (id: number) => {
    const q = new URLSearchParams(searchParams.toString())
    q.set("g", String(id))
    router.replace(`/dashboard/groups?${q.toString()}`, { scroll: false })
    setMobilePanel("chat")
    setChatSearchOpen(false)
    setChatSearch("")
  }

  useEffect(() => {
    if (!selectedId || Number.isNaN(selectedId)) return
    if (!selectedGroup) return
    if (!selectedGroup.is_member) {
      setMembers([])
      setMessages([])
      return
    }
    let cancel = false
    const load = async () => {
      setMsgLoading(true)
      try {
        const [m, mem] = await Promise.all([
          socialService.getGroupMessages(
            selectedId,
            0,
            80,
            debouncedChatSearch || undefined,
          ),
          socialService.getGroupMembers(selectedId),
        ])
        if (cancel) return
        setMembers(mem)
        setMessages(Array.isArray(m) ? m.slice().reverse() : [])
      } catch {
        if (!cancel) addToast("Failed to load conversation.", "error")
      } finally {
        if (!cancel) setMsgLoading(false)
      }
    }
    void load()
    return () => {
      cancel = true
    }
  }, [selectedId, selectedGroup, debouncedChatSearch, addToast])

  useEffect(() => {
    if (selectedGroup) {
      setEditName(selectedGroup.name)
      setEditDesc(selectedGroup.description || "")
    }
  }, [selectedGroup])

  const myRole = useMemo(() => {
    if (!user?.id) return null
    const row = members.find((m) => m.user_id === user.id)
    return row?.role ?? null
  }, [members, user?.id])

  const isAdmin =
    myRole === "admin" || myRole === "owner" || myRole === "moderator"

  const headerSubtitle = useMemo(() => {
    if (!selectedGroup) return ""
    const countLabel = `${selectedGroup.members_count} ${tf(t, "dashboard.groups.members", "members")}`
    if (!selectedGroup.is_member) {
      return `${countLabel} · ${tf(t, "dashboard.groups.not_a_member", "Not a member")}`
    }
    const rl = roleLabelText(myRole, t)
    return rl ? `${countLabel} · ${rl}` : countLabel
  }, [selectedGroup, myRole, t])

  const filteredList = useMemo(() => {
    let rows = groups
    if (listFilter === "joined") rows = rows.filter((g) => g.is_member)
    const q = listQuery.trim().toLowerCase()
    if (q) {
      rows = rows.filter(
        (g) =>
          g.name.toLowerCase().includes(q) ||
          (g.description || "").toLowerCase().includes(q),
      )
    }
    return rows
  }, [groups, listFilter, listQuery])

  const orderedMessages = useMemo(() => {
    return [...messages].sort(
      (a, b) =>
        parseApiDate(a.created_at).getTime() -
        parseApiDate(b.created_at).getTime(),
    )
  }, [messages])

  const handleSend = async () => {
    if (!selectedId || !messageText.trim()) return
    setSending(true)
    try {
      const sent = await socialService.sendGroupMessage(selectedId, {
        content: messageText.trim(),
        message_type: "text",
      })
      setMessages((prev) => [...prev, sent])
      setMessageText("")
      setPreviews((p) => ({
        ...p,
        [selectedId]: {
          text: (sent.content || "").slice(0, 72),
          time: sent.created_at,
        },
      }))
    } catch (e: unknown) {
      addToast(
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Send failed",
        "error",
      )
    } finally {
      setSending(false)
    }
  }

  const saveSettings = async () => {
    if (!selectedId || !editName.trim()) return
    setSavingSettings(true)
    try {
      const updated = await socialService.updateFeedGroup(selectedId, {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
      })
      setGroups((prev) =>
        prev.map((g) => (g.id === selectedId ? { ...g, ...updated } : g)),
      )
      setSettingsOpen(false)
      addToast("Group updated.", "success")
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Update failed"
      addToast(String(msg), "error")
    } finally {
      setSavingSettings(false)
    }
  }

  const addMember = async () => {
    if (!selectedId || !addUsername.trim()) return
    setAddingUser(true)
    try {
      await socialService.addGroupMemberByUsername(selectedId, addUsername.trim())
      setAddUsername("")
      setAddUserOpen(false)
      const mem = await socialService.getGroupMembers(selectedId)
      setMembers(mem)
      addToast("Member added.", "success")
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Could not add user"
      addToast(String(msg), "error")
    } finally {
      setAddingUser(false)
    }
  }

  const handleJoin = async () => {
    if (!selectedId || !selectedGroup) return
    setJoining(true)
    try {
      await socialService.joinGroup(
        selectedId,
        selectedGroup.is_private ? inviteCode.trim() || undefined : undefined,
      )
      const g = await socialService.getGroup(selectedId)
      setGroups((prev) => {
        const rest = prev.filter((x) => x.id !== g.id)
        return [g, ...rest]
      })
      addToast("Successfully joined the group.", "success")
      setInviteCode("")
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ||
        tf(t, "errors.generic", "Could not join")
      addToast(String(msg), "error")
    } finally {
      setJoining(false)
    }
  }

  const handleCreate = async () => {
    if (!newGroup.name.trim()) return
    setCreating(true)
    try {
      const g = await socialService.createGroup(newGroup)
      setGroups((prev) => [g, ...prev])
      setCreateOpen(false)
      setNewGroup({ name: "", description: "", is_private: false })
      selectGroup(g.id)
      addToast("Group created.", "success")
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Create failed"
      addToast(String(msg), "error")
    } finally {
      setCreating(false)
    }
  }

  return (
    <div
      className={cn(
        "-mx-4 sm:-mx-6 lg:-mx-8 min-h-[calc(100dvh-8rem)] flex flex-col border border-gray-200/80 dark:border-gray-700/80 rounded-none md:rounded-xl overflow-hidden bg-white dark:bg-gray-950",
      )}
    >
      <div className="flex flex-1 min-h-0">
        {/* Left — conversation list */}
        <aside
          className={cn(
            "flex flex-col w-full md:w-[min(100%,420px)] md:min-w-[300px] lg:w-[400px] border-r border-gray-200 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-900/80",
            selectedId && mobilePanel === "chat" ? "hidden md:flex" : "flex",
          )}
        >
          <div className="flex items-center justify-between gap-2 px-3 py-3 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/90">
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white tracking-tight">
              {tf(t, "dashboard.groups.title", "Groups")}
            </h1>
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0 text-myhigh5-primary hover:text-myhigh5-primary hover:bg-myhigh5-primary/10"
              onClick={() => setCreateOpen(true)}
              aria-label={tf(t, "dashboard.groups.create_group", "Create a group")}
            >
              <Plus className="h-5 w-5" />
            </Button>
          </div>
          <div className="px-2 py-2 border-b border-gray-200 dark:border-gray-800 space-y-2 bg-white dark:bg-gray-900/50">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                value={listQuery}
                onChange={(e) => setListQuery(e.target.value)}
                placeholder={tf(
                  t,
                  "dashboard.groups.search_placeholder",
                  "Search groups…",
                )}
                className="pl-9 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700"
              />
            </div>
            <div className="flex gap-2">
              {(["all", "joined"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setListFilter(f)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border",
                    listFilter === f
                      ? "border-myhigh5-primary bg-myhigh5-primary text-white shadow-sm"
                      : "border-transparent bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700/50",
                  )}
                >
                  {f === "all"
                    ? tf(t, "dashboard.groups.filter_all", "All")
                    : tf(t, "dashboard.groups.filter_mine", "My groups")}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0 bg-white dark:bg-gray-900">
            {listLoading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
              </div>
            ) : filteredList.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-500">
                {tf(
                  t,
                  "dashboard.groups.no_groups_found",
                  "No groups match your search.",
                )}
              </div>
            ) : (
              filteredList.map((g) => {
                const pv = previews[g.id]
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => selectGroup(g.id)}
                    className={cn(
                      "w-full text-left flex gap-3 px-3 py-3 border-b border-gray-100 dark:border-gray-800/90 hover:bg-myhigh5-primary/[0.06] dark:hover:bg-gray-800/80 transition-colors",
                      selectedId === g.id &&
                        "bg-myhigh5-primary/10 dark:bg-myhigh5-primary/15 border-l-[3px] border-l-myhigh5-primary",
                    )}
                  >
                    <div className="h-12 w-12 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center overflow-hidden shrink-0 shadow-sm">
                      {g.avatar_url ? (
                        <img
                          src={g.avatar_url}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <Users className="h-6 w-6 text-white" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between gap-2 items-baseline">
                        <span className="font-medium text-gray-900 dark:text-white truncate">
                          {g.name}
                        </span>
                        {pv?.time && (
                          <span className="text-[11px] text-gray-400 shrink-0">
                            {formatListTime(pv.time)}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                        {pv?.text ||
                          g.description?.slice(0, 48) ||
                          (g.is_member
                            ? tf(
                                t,
                                "dashboard.groups.tap_to_chat",
                                "Open conversation",
                              )
                            : "—")}
                      </p>
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </aside>

        {/* Right — chat */}
        <section
          className={cn(
            "flex-1 flex flex-col min-w-0 min-h-0 bg-gray-100/90 dark:bg-gray-950 border-l border-gray-200 dark:border-gray-800",
            !selectedId ? "hidden md:flex" : "",
            selectedId && mobilePanel === "list" ? "hidden md:flex" : "flex",
          )}
        >
          {!selectedGroup ? (
            <div className="flex-1 hidden md:flex flex-col items-center justify-center text-center px-6">
              <MessageCircle className="h-16 w-16 text-myhigh5-primary/30 dark:text-myhigh5-primary/25 mb-4" />
              <p className="text-base font-medium text-gray-600 dark:text-gray-300 max-w-sm">
                {tf(
                  t,
                  "dashboard.groups.select_chat",
                  "Select a group to open the conversation.",
                )}
              </p>
            </div>
          ) : (
            <>
              {/* Chat header — tap row for group info */}
              <header className="flex items-center gap-2 px-2 py-2.5 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 shadow-sm">
                <Button
                  variant="ghost"
                  size="icon"
                  className="md:hidden shrink-0"
                  onClick={() => setMobilePanel("list")}
                  aria-label="Back to list"
                >
                  <ArrowLeft className="h-5 w-5" />
                </Button>
                <button
                  type="button"
                  onClick={() => setGroupInfoOpen(true)}
                  className="flex flex-1 min-w-0 items-center gap-2 rounded-lg px-1 py-0.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800/80 transition-colors -m-0.5"
                >
                  <div className="h-10 w-10 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center overflow-hidden shrink-0 shadow-sm ring-2 ring-white dark:ring-gray-800">
                    {selectedGroup.avatar_url ? (
                      <img
                        src={selectedGroup.avatar_url}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <Users className="h-5 w-5 text-white" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-gray-900 dark:text-white truncate">
                      {selectedGroup.name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {headerSubtitle}
                    </div>
                  </div>
                  <Info className="h-4 w-4 shrink-0 text-gray-400 hidden sm:block" aria-hidden />
                </button>
                <div className="flex items-center gap-0.5 shrink-0">
                  {selectedGroup.is_member && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          chatSearchOpen && "bg-myhigh5-primary/10 dark:bg-gray-800",
                        )}
                        onClick={() =>
                          setChatSearchOpen((v) => {
                            if (v) setChatSearch("")
                            return !v
                          })
                        }
                        aria-label="Search messages"
                      >
                        <Search className="h-5 w-5 text-gray-600 dark:text-gray-300" />
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label="Menu">
                            <MoreVertical className="h-5 w-5 text-gray-600 dark:text-gray-300" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => setGroupInfoOpen(true)}
                          >
                            <Info className="h-4 w-4 mr-2" />
                            {tf(
                              t,
                              "dashboard.groups.group_info",
                              "Group information",
                            )}
                          </DropdownMenuItem>
                          {isAdmin && (
                            <>
                              <DropdownMenuItem
                                onClick={() => setSettingsOpen(true)}
                              >
                                <Settings className="h-4 w-4 mr-2" />
                                {tf(
                                  t,
                                  "dashboard.groups.group_settings",
                                  "Group settings",
                                )}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => setAddUserOpen(true)}
                              >
                                <Plus className="h-4 w-4 mr-2" />
                                {tf(
                                  t,
                                  "dashboard.groups.add_member",
                                  "Add member",
                                )}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </>
                  )}
                </div>
              </header>

              {chatSearchOpen && selectedGroup.is_member && (
                <div className="px-3 py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
                  <Input
                    value={chatSearch}
                    onChange={(e) => setChatSearch(e.target.value)}
                    placeholder={tf(
                      t,
                      "dashboard.groups.search_messages_placeholder",
                      "Search messages in this chat…",
                    )}
                    className="rounded-lg border-gray-200 dark:border-gray-700"
                  />
                </div>
              )}

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-3 py-3 min-h-0 bg-[#eef1f8] dark:bg-gray-900/50">
                {!selectedGroup.is_member ? (
                  <div className="max-w-md mx-auto mt-4 space-y-4">
                    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-5 shadow-sm text-center">
                      <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
                        {tf(
                          t,
                          "dashboard.groups.join_to_chat",
                          "Join this group to read and send messages.",
                        )}
                      </p>
                      {selectedGroup.is_private ? (
                        <div className="space-y-3 text-left">
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {tf(
                              t,
                              "dashboard.groups.invite_code_hint",
                              "Enter the invite code you received from a member.",
                            )}
                          </p>
                          <Input
                            value={inviteCode}
                            onChange={(e) => setInviteCode(e.target.value)}
                            placeholder={tf(
                              t,
                              "dashboard.groups.invite_code",
                              "Invite code",
                            )}
                            className="font-mono"
                          />
                          <Button
                            className="w-full bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                            disabled={joining || !inviteCode.trim()}
                            onClick={() => void handleJoin()}
                          >
                            {joining ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              tf(t, "dashboard.groups.join_group", "Join group")
                            )}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          className="w-full sm:w-auto min-w-[200px] bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                          disabled={joining}
                          onClick={() => void handleJoin()}
                        >
                          {joining ? (
                            <>
                              <Loader2 className="h-4 w-4 animate-spin mr-2" />
                              {tf(t, "dashboard.groups.joining", "Joining…")}
                            </>
                          ) : (
                            tf(t, "dashboard.groups.join_group", "Join group")
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                ) : msgLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
                  </div>
                ) : orderedMessages.length === 0 ? (
                  <div className="text-center text-sm text-gray-600 dark:text-gray-400 py-8">
                    {debouncedChatSearch
                      ? tf(
                          t,
                          "dashboard.groups.no_search_hits",
                          "No messages match your search.",
                        )
                      : tf(
                          t,
                          "dashboard.groups.no_messages",
                          "No messages yet. Say hello.",
                        )}
                  </div>
                ) : (
                  <div className="space-y-2 max-w-3xl mx-auto">
                    {orderedMessages.map((message) => {
                      const mine = message.sender_id === user?.id
                      return (
                        <div
                          key={message.id}
                          className={cn(
                            "flex",
                            mine ? "justify-end" : "justify-start",
                          )}
                        >
                          <div
                            className={cn(
                              "max-w-[85%] rounded-xl px-3 py-2 shadow-sm text-sm border border-transparent",
                              mine
                                ? "bg-myhigh5-primary text-white border-myhigh5-primary/80"
                                : "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-200 dark:border-gray-700",
                            )}
                          >
                            {!mine && (
                              <div className="text-xs font-medium text-myhigh5-primary dark:text-myhigh5-secondary mb-0.5">
                                {message.sender?.full_name ||
                                  message.sender?.username ||
                                  `#${message.sender_id}`}
                              </div>
                            )}
                            <div className="whitespace-pre-wrap break-words">
                              {message.content}
                            </div>
                            <div
                              className={cn(
                                "text-[10px] text-right mt-0.5",
                                mine ? "text-white/80" : "opacity-70",
                              )}
                            >
                              {parseApiDate(
                                message.created_at,
                              ).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Composer */}
              {selectedGroup.is_member && (
                <footer className="flex items-end gap-2 px-3 py-2.5 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
                  <Textarea
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    placeholder={tf(
                      t,
                      "dashboard.messages.type_message",
                      "Type a message",
                    )}
                    className="min-h-[44px] max-h-32 resize-none rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/80"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        void handleSend()
                      }
                    }}
                  />
                  <Button
                    size="icon"
                    className="rounded-full shrink-0 bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                    disabled={sending || !messageText.trim()}
                    onClick={() => void handleSend()}
                  >
                    <Send className="h-5 w-5" />
                  </Button>
                </footer>
              )}
            </>
          )}
        </section>
      </div>

      {/* Group information (profile) */}
      <Dialog open={groupInfoOpen} onOpenChange={setGroupInfoOpen}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {tf(t, "dashboard.groups.group_info", "Group information")}
            </DialogTitle>
          </DialogHeader>
          {selectedGroup && (
            <div className="space-y-5 pt-1">
              <div className="flex items-start gap-3">
                <div className="h-14 w-14 rounded-full bg-gradient-to-br from-myhigh5-primary to-myhigh5-secondary flex items-center justify-center overflow-hidden shrink-0 shadow-md">
                  {selectedGroup.avatar_url ? (
                    <img
                      src={selectedGroup.avatar_url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <Users className="h-7 w-7 text-white" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-gray-900 dark:text-white text-lg leading-tight">
                    {selectedGroup.name}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-1.5">
                    {selectedGroup.is_private ? (
                      <>
                        <Lock className="h-3.5 w-3.5 shrink-0" />
                        {tf(t, "dashboard.groups.private", "Private")}
                      </>
                    ) : (
                      <>
                        <Globe className="h-3.5 w-3.5 shrink-0" />
                        {tf(t, "dashboard.groups.public", "Public")}
                      </>
                    )}
                    <span className="text-gray-300 dark:text-gray-600">·</span>
                    {selectedGroup.members_count}{" "}
                    {tf(t, "dashboard.groups.members", "members")}
                  </p>
                </div>
              </div>
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1.5">
                  {tf(t, "dashboard.groups.description_label", "Description")}
                </h3>
                <p className="text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap rounded-lg bg-gray-50 dark:bg-gray-800/80 p-3 border border-gray-100 dark:border-gray-700">
                  {selectedGroup.description?.trim()
                    ? selectedGroup.description
                    : tf(
                        t,
                        "dashboard.groups.no_description",
                        "No description yet.",
                      )}
                </p>
              </div>
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                  {tf(t, "dashboard.groups.members_heading", "Members")}
                </h3>
                {selectedGroup.is_member ? (
                  msgLoading && members.length === 0 ? (
                    <div className="flex justify-center py-6">
                      <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
                    </div>
                  ) : (
                    <ul className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
                      {members.map((m) => (
                        <li
                          key={m.id}
                          className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-2 bg-white dark:bg-gray-900/50"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <UserAvatar
                              user={m.user || { id: m.user_id }}
                              className="h-9 w-9 shrink-0"
                            />
                            <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {m.user?.full_name ||
                                m.user?.username ||
                                `User #${m.user_id}`}
                            </span>
                          </div>
                          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 capitalize">
                            {roleLabelText(m.role, t)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )
                ) : selectedGroup.is_private ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {tf(
                      t,
                      "dashboard.groups.members_private_hint",
                      "Member list is available after you join this group.",
                    )}
                  </p>
                ) : previewMembersLoading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="h-6 w-6 animate-spin text-myhigh5-primary" />
                  </div>
                ) : previewMembers.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    {tf(
                      t,
                      "dashboard.groups.no_members_preview",
                      "No members loaded.",
                    )}
                  </p>
                ) : (
                  <ul className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
                    {previewMembers.map((m) => (
                      <li
                        key={m.id}
                        className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-2 bg-white dark:bg-gray-900/50"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <UserAvatar
                            user={m.user || { id: m.user_id }}
                            className="h-9 w-9 shrink-0"
                          />
                          <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {m.user?.full_name ||
                              m.user?.username ||
                              `User #${m.user_id}`}
                          </span>
                        </div>
                        <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 capitalize">
                          {roleLabelText(m.role, t)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Settings */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {tf(t, "dashboard.groups.group_settings", "Group settings")}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="text-xs font-medium text-gray-500">
                {tf(t, "dashboard.groups.group_name", "Group name")}
              </label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                {tf(t, "dashboard.groups.description", "Description")}
              </label>
              <Textarea
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                className="min-h-[88px]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSettingsOpen(false)}>
              {tf(t, "dashboard.groups.cancel", "Cancel")}
            </Button>
            <Button
              onClick={() => void saveSettings()}
              disabled={savingSettings || !editName.trim()}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              {savingSettings ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={addUserOpen} onOpenChange={setAddUserOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {tf(t, "dashboard.groups.add_member", "Add member")}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-500">
            {tf(
              t,
              "dashboard.groups.add_by_username_hint",
              "Enter the exact username (without @).",
            )}
          </p>
          <Input
            placeholder="username"
            value={addUsername}
            onChange={(e) => setAddUsername(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddUserOpen(false)}>
              {tf(t, "dashboard.groups.cancel", "Cancel")}
            </Button>
            <Button
              onClick={() => void addMember()}
              disabled={addingUser || !addUsername.trim()}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              {addingUser ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {tf(t, "dashboard.groups.create_new_group", "Create a new group")}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder={tf(
                t,
                "dashboard.groups.group_name_placeholder",
                "Group name",
              )}
              value={newGroup.name}
              onChange={(e) =>
                setNewGroup({ ...newGroup, name: e.target.value })
              }
            />
            <Textarea
              placeholder={tf(
                t,
                "dashboard.groups.description_placeholder",
                "What is this group about?",
              )}
              value={newGroup.description}
              onChange={(e) =>
                setNewGroup({ ...newGroup, description: e.target.value })
              }
            />
            <div className="flex gap-2">
              <Button
                type="button"
                variant={newGroup.is_private ? "outline" : "default"}
                size="sm"
                onClick={() => setNewGroup({ ...newGroup, is_private: false })}
                className={
                  !newGroup.is_private
                    ? "bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                    : ""
                }
              >
                <Globe className="h-4 w-4 mr-1" />
                {tf(t, "dashboard.groups.public", "Public")}
              </Button>
              <Button
                type="button"
                variant={newGroup.is_private ? "default" : "outline"}
                size="sm"
                onClick={() => setNewGroup({ ...newGroup, is_private: true })}
                className={
                  newGroup.is_private
                    ? "bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                    : ""
                }
              >
                <Lock className="h-4 w-4 mr-1" />
                {tf(t, "dashboard.groups.private", "Private")}
              </Button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {newGroup.is_private
                ? tf(
                    t,
                    "dashboard.groups.private_visibility_help",
                    "Private groups are hidden from people who are not members. Anyone an admin adds by username becomes a member and will see this group.",
                  )
                : tf(
                    t,
                    "dashboard.groups.public_visibility_help",
                    "Public groups appear for everyone and can be joined without an invite code.",
                  )}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {tf(t, "dashboard.groups.cancel", "Cancel")}
            </Button>
            <Button
              onClick={() => void handleCreate()}
              disabled={creating || !newGroup.name.trim()}
              className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
