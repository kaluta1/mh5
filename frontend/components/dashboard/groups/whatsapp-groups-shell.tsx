"use client"

import * as React from "react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  ArrowLeft,
  Globe,
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
      addToast(t("errors.generic") || "Failed to load groups", "error")
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

  const clearSelection = () => {
    router.replace("/dashboard/groups", { scroll: false })
    setMobilePanel("list")
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
        "-mx-4 sm:-mx-6 lg:-mx-8 min-h-[calc(100dvh-8rem)] flex flex-col border border-gray-200/80 dark:border-gray-700/80 rounded-none md:rounded-xl overflow-hidden bg-[#f8f9fa] dark:bg-gray-950",
      )}
    >
      <div className="flex flex-1 min-h-0">
        {/* Left — conversation list */}
        <aside
          className={cn(
            "flex flex-col w-full md:w-[380px] md:min-w-[320px] border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900",
            selectedId && mobilePanel === "chat" ? "hidden md:flex" : "flex",
          )}
        >
          <div className="flex items-center justify-between px-3 py-3 border-b border-gray-100 dark:border-gray-800">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {t("dashboard.groups.title")}
            </h1>
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={() => setCreateOpen(true)}
              aria-label={t("dashboard.groups.create_group")}
            >
              <Plus className="h-5 w-5" />
            </Button>
          </div>
          <div className="px-2 py-2 border-b border-gray-100 dark:border-gray-800 space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                value={listQuery}
                onChange={(e) => setListQuery(e.target.value)}
                placeholder={t("dashboard.groups.search_placeholder")}
                className="pl-9 rounded-full bg-gray-100 dark:bg-gray-800 border-0"
              />
            </div>
            <div className="flex gap-1.5">
              {(["all", "joined"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setListFilter(f)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs font-medium transition-colors",
                    listFilter === f
                      ? "bg-emerald-600 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200",
                  )}
                >
                  {f === "all"
                    ? t("dashboard.groups.filter_all") || "All"
                    : t("dashboard.groups.filter_mine") || "My groups"}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto min-h-0">
            {listLoading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
              </div>
            ) : filteredList.length === 0 ? (
              <div className="p-6 text-center text-sm text-gray-500">
                {t("dashboard.groups.no_groups_found")}
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
                      "w-full text-left flex gap-3 px-3 py-2.5 border-b border-gray-100/80 dark:border-gray-800/80 hover:bg-gray-50 dark:hover:bg-gray-800/80 transition-colors",
                      selectedId === g.id && "bg-emerald-50/80 dark:bg-emerald-950/30",
                    )}
                  >
                    <div className="h-12 w-12 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center overflow-hidden shrink-0">
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
                            ? t("dashboard.groups.tap_to_chat") || "Tap to chat"
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
            "flex-1 flex flex-col min-w-0 min-h-0 bg-[#efeae2] dark:bg-gray-900",
            !selectedId ? "hidden md:flex" : "",
            selectedId && mobilePanel === "list" ? "hidden md:flex" : "flex",
          )}
        >
          {!selectedGroup ? (
            <div className="flex-1 hidden md:flex flex-col items-center justify-center text-center px-6 border-l border-gray-200/80 dark:border-gray-800">
              <MessageCircle className="h-20 w-20 text-gray-300 dark:text-gray-600 mb-4" />
              <p className="text-lg font-medium text-gray-600 dark:text-gray-300">
                {t("dashboard.groups.select_chat") || "Select a group to start"}
              </p>
            </div>
          ) : (
            <>
              {/* Chat header */}
              <header className="flex items-center gap-2 px-2 py-2 bg-[#f0f2f5] dark:bg-gray-900 border-b border-gray-200/90 dark:border-gray-800">
                <Button
                  variant="ghost"
                  size="icon"
                  className="md:hidden"
                  onClick={() => {
                    clearSelection()
                  }}
                >
                  <ArrowLeft className="h-5 w-5" />
                </Button>
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center overflow-hidden shrink-0">
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
                  <div className="text-xs text-gray-500 truncate">
                    {selectedGroup.members_count}{" "}
                    {t("dashboard.groups.members")} ·{" "}
                    {myRole === "owner"
                      ? t("dashboard.groups.role_owner") || "Owner"
                      : myRole === "admin"
                        ? t("dashboard.groups.role_admin") || "Admin"
                        : myRole === "moderator"
                          ? "Moderator"
                          : t("dashboard.groups.role_member") || "Member"}
                  </div>
                </div>
                {selectedGroup.is_member && (
                  <div className="flex items-center gap-0.5 shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(chatSearchOpen && "bg-gray-200 dark:bg-gray-800")}
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
                    {selectedGroup.is_member && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label="Menu">
                            <MoreVertical className="h-5 w-5 text-gray-600 dark:text-gray-300" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {isAdmin && (
                            <>
                              <DropdownMenuItem
                                onClick={() => setSettingsOpen(true)}
                              >
                                <Settings className="h-4 w-4 mr-2" />
                                {t("dashboard.groups.group_settings") || "Group settings"}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => setAddUserOpen(true)}
                              >
                                <Plus className="h-4 w-4 mr-2" />
                                {t("dashboard.groups.add_member") || "Add member"}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                )}
              </header>

              {chatSearchOpen && selectedGroup.is_member && (
                <div className="px-3 py-2 bg-[#f0f2f5] dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
                  <Input
                    value={chatSearch}
                    onChange={(e) => setChatSearch(e.target.value)}
                    placeholder={
                      t("dashboard.groups.search_messages_placeholder") ||
                      "Search in conversation..."
                    }
                    className="rounded-lg"
                  />
                </div>
              )}

              {/* Messages */}
              <div
                className="flex-1 overflow-y-auto px-2 py-3 min-h-0"
                style={{
                  backgroundColor: "var(--wa-bg, #efeae2)",
                  backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23c4c4c4' fill-opacity='0.12'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2V6h4V4H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
                }}
              >
                {!selectedGroup.is_member ? (
                  <div className="text-center text-sm text-gray-600 py-8 px-4 bg-white/80 dark:bg-gray-800/80 rounded-lg">
                    {t("dashboard.groups.join_to_chat")}
                  </div>
                ) : msgLoading ? (
                  <div className="flex justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
                  </div>
                ) : orderedMessages.length === 0 ? (
                  <div className="text-center text-sm text-gray-600 py-8">
                    {debouncedChatSearch
                      ? t("dashboard.groups.no_search_hits") || "No messages match."
                      : t("dashboard.groups.no_messages")}
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
                              "max-w-[85%] rounded-lg px-2 py-1.5 shadow-sm text-sm",
                              mine
                                ? "bg-[#d9fdd3] dark:bg-emerald-900/50 text-gray-900 dark:text-gray-100"
                                : "bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100",
                            )}
                          >
                            {!mine && (
                              <div className="text-xs font-medium text-emerald-700 dark:text-emerald-400 mb-0.5">
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
                                "text-[10px] text-right mt-0.5 opacity-70",
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
                <footer className="flex items-end gap-2 px-2 py-2 bg-[#f0f2f5] dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800">
                  <Textarea
                    value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    placeholder={
                      t("dashboard.messages.type_message") || "Type a message"
                    }
                    className="min-h-[44px] max-h-32 resize-none rounded-xl border-0 bg-white dark:bg-gray-800 shadow-inner"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault()
                        void handleSend()
                      }
                    }}
                  />
                  <Button
                    size="icon"
                    className="rounded-full shrink-0 bg-emerald-600 hover:bg-emerald-700"
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

      {/* Settings */}
      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("dashboard.groups.group_settings") || "Group settings"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="text-xs font-medium text-gray-500">
                {t("dashboard.groups.group_name")}
              </label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500">
                {t("dashboard.groups.description")}
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
              {t("dashboard.groups.cancel")}
            </Button>
            <Button
              onClick={() => void saveSettings()}
              disabled={savingSettings || !editName.trim()}
              className="bg-emerald-600 hover:bg-emerald-700"
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
              {t("dashboard.groups.add_member") || "Add member"}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-500">
            {t("dashboard.groups.add_by_username_hint") ||
              "Enter the exact username (without @)."}
          </p>
          <Input
            placeholder="username"
            value={addUsername}
            onChange={(e) => setAddUsername(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddUserOpen(false)}>
              {t("dashboard.groups.cancel")}
            </Button>
            <Button
              onClick={() => void addMember()}
              disabled={addingUser || !addUsername.trim()}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {addingUser ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("dashboard.groups.create_new_group")}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder={t("dashboard.groups.group_name_placeholder")}
              value={newGroup.name}
              onChange={(e) =>
                setNewGroup({ ...newGroup, name: e.target.value })
              }
            />
            <Textarea
              placeholder={t("dashboard.groups.description_placeholder")}
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
              >
                <Globe className="h-4 w-4 mr-1" />
                {t("dashboard.groups.public")}
              </Button>
              <Button
                type="button"
                variant={newGroup.is_private ? "default" : "outline"}
                size="sm"
                onClick={() => setNewGroup({ ...newGroup, is_private: true })}
              >
                <Lock className="h-4 w-4 mr-1" />
                {t("dashboard.groups.private")}
              </Button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {newGroup.is_private
                ? t("dashboard.groups.private_visibility_help") ||
                  "Private groups are hidden from people who are not members. Anyone you add by username becomes a member and will see this group."
                : t("dashboard.groups.public_visibility_help") ||
                  "Public groups appear in everyone’s list and can be joined without an invite code."}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("dashboard.groups.cancel")}
            </Button>
            <Button
              onClick={() => void handleCreate()}
              disabled={creating || !newGroup.name.trim()}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
