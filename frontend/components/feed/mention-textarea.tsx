'use client'

import { useEffect, useRef, useState } from 'react'

import { Textarea, TextareaProps } from '@/components/ui/textarea'
import { UserAvatar } from '@/components/user/user-avatar'
import { cn } from '@/lib/utils'
import { MentionUser, userService } from '@/services/user-service'

interface MentionTextareaProps extends Omit<TextareaProps, 'value' | 'onChange'> {
  value: string
  onChange: (value: string) => void
  onMentionSelect?: (user: MentionUser) => void
}

export function MentionTextarea({
  value,
  onChange,
  onMentionSelect,
  className,
  onKeyDown,
  ...props
}: MentionTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionStart, setMentionStart] = useState<number | null>(null)
  const [suggestions, setSuggestions] = useState<MentionUser[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)

  useEffect(() => {
    if (!showSuggestions || !mentionQuery.trim()) {
      setSuggestions([])
      return
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const users = await userService.searchUsers(mentionQuery, 8)
        setSuggestions(users.filter((user) => user.username).slice(0, 5))
        setSelectedIndex(0)
      } catch (error) {
        console.error('Error loading mention suggestions:', error)
        setSuggestions([])
      }
    }, 150)

    return () => window.clearTimeout(timeoutId)
  }, [mentionQuery, showSuggestions])

  const updateMentionState = (nextValue: string, cursorPos: number) => {
    const textBeforeCursor = nextValue.slice(0, cursorPos)
    const mentionMatch = textBeforeCursor.match(/(?:^|\s)@([A-Za-z0-9_]*)$/)

    if (!mentionMatch) {
      setMentionQuery('')
      setMentionStart(null)
      setShowSuggestions(false)
      setSuggestions([])
      return
    }

    const query = mentionMatch[1]
    const start = cursorPos - query.length - 1

    setMentionQuery(query)
    setMentionStart(start)
    setShowSuggestions(query.length > 0)
  }

  const handleChange = (nextValue: string) => {
    onChange(nextValue)

    const cursorPos = textareaRef.current?.selectionStart ?? nextValue.length
    updateMentionState(nextValue, cursorPos)
  }

  const selectUser = (user: MentionUser) => {
    const username = user.username?.trim()
    if (!username || mentionStart === null) return

    const selectionStart = textareaRef.current?.selectionStart ?? value.length
    const textBefore = value.slice(0, mentionStart)
    const textAfter = value.slice(selectionStart)
    const nextValue = `${textBefore}@${username} ${textAfter}`

    onChange(nextValue)
    onMentionSelect?.(user)
    setMentionQuery('')
    setMentionStart(null)
    setShowSuggestions(false)
    setSuggestions([])

    window.setTimeout(() => {
      const nextCursorPos = mentionStart + username.length + 2
      textareaRef.current?.focus()
      textareaRef.current?.setSelectionRange(nextCursorPos, nextCursorPos)
    }, 0)
  }

  const handleKeyDownInternal = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSuggestions && suggestions.length > 0) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : prev))
        return
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0))
        return
      }

      if ((event.key === 'Enter' || event.key === 'Tab') && suggestions[selectedIndex]) {
        event.preventDefault()
        selectUser(suggestions[selectedIndex])
        return
      }

      if (event.key === 'Escape') {
        event.preventDefault()
        setShowSuggestions(false)
        return
      }
    }

    onKeyDown?.(event)
  }

  return (
    <div className="relative">
      <Textarea
        {...props}
        ref={textareaRef}
        value={value}
        onChange={(event) => handleChange(event.target.value)}
        onKeyDown={handleKeyDownInternal}
        onClick={() => {
          const cursorPos = textareaRef.current?.selectionStart ?? value.length
          updateMentionState(value, cursorPos)
        }}
        onKeyUp={() => {
          const cursorPos = textareaRef.current?.selectionStart ?? value.length
          updateMentionState(value, cursorPos)
        }}
        onBlur={() => {
          window.setTimeout(() => setShowSuggestions(false), 150)
        }}
        onFocus={() => {
          const cursorPos = textareaRef.current?.selectionStart ?? value.length
          updateMentionState(value, cursorPos)
        }}
        className={className}
      />

      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 z-50 mt-2 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800">
          {suggestions.map((user, index) => (
            <button
              key={user.id}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => selectUser(user)}
              className={cn(
                'flex w-full items-center gap-3 px-3 py-2 text-left transition-colors',
                index === selectedIndex
                  ? 'bg-gray-100 dark:bg-gray-700'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700/60'
              )}
            >
              <UserAvatar
                user={{
                  id: user.id,
                  username: user.username,
                  full_name: user.full_name,
                  avatar_url: user.avatar_url,
                }}
                className="h-8 w-8"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-gray-900 dark:text-white">
                  {user.full_name || user.username}
                </div>
                <div className="truncate text-xs text-gray-500 dark:text-gray-400">
                  @{user.username}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
