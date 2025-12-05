'use client'

import { useState, useEffect, useRef } from 'react'
import Image from 'next/image'

interface MentionUser {
  id: number
  username: string
  name: string
  avatar_url?: string
}

interface MentionAutocompleteProps {
  value: string
  onChange: (value: string) => void
  onMentionSelect: (username: string) => void
  users: MentionUser[]
  placeholder?: string
  className?: string
  disabled?: boolean
}

export function MentionAutocomplete({
  value,
  onChange,
  onMentionSelect,
  users,
  placeholder,
  className = '',
  disabled = false
}: MentionAutocompleteProps) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [filteredUsers, setFilteredUsers] = useState<MentionUser[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [mentionStart, setMentionStart] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const suggestionsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const cursorPos = inputRef.current?.selectionStart || 0
    const textBeforeCursor = value.substring(0, cursorPos)
    const mentionMatch = textBeforeCursor.match(/@(\w*)$/)

    if (mentionMatch) {
      const query = mentionMatch[1].toLowerCase()
      const start = cursorPos - mentionMatch[0].length
      
      setMentionStart(start)
      setShowSuggestions(true)
      
      // Filtrer les utilisateurs
      const filtered = users.filter(user => 
        user.username.toLowerCase().includes(query) ||
        user.name.toLowerCase().includes(query)
      ).slice(0, 5) // Limiter à 5 suggestions
      
      setFilteredUsers(filtered)
      setSelectedIndex(0)
    } else {
      setShowSuggestions(false)
      setMentionStart(null)
    }
  }, [value, users])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || filteredUsers.length === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(prev => 
        prev < filteredUsers.length - 1 ? prev + 1 : prev
      )
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(prev => prev > 0 ? prev - 1 : 0)
    } else if (e.key === 'Enter' && filteredUsers.length > 0) {
      e.preventDefault()
      selectUser(filteredUsers[selectedIndex])
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  const selectUser = (user: MentionUser) => {
    if (!mentionStart) return

    const textBefore = value.substring(0, mentionStart)
    const textAfter = value.substring(inputRef.current?.selectionStart || value.length)
    const newValue = `${textBefore}@${user.username} ${textAfter}`
    
    onChange(newValue)
    onMentionSelect(user.username)
    setShowSuggestions(false)
    setMentionStart(null)
    
    // Repositionner le curseur après la mention
    setTimeout(() => {
      const newCursorPos = mentionStart + user.username.length + 2 // +2 pour @ et espace
      inputRef.current?.setSelectionRange(newCursorPos, newCursorPos)
      inputRef.current?.focus()
    }, 0)
  }

  return (
    <div className="relative w-full">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          // Délai pour permettre le clic sur une suggestion
          setTimeout(() => setShowSuggestions(false), 200)
        }}
        onFocus={() => {
          // Vérifier s'il y a une mention en cours
          const cursorPos = inputRef.current?.selectionStart || 0
          const textBeforeCursor = value.substring(0, cursorPos)
          if (textBeforeCursor.match(/@(\w*)$/)) {
            setShowSuggestions(true)
          }
        }}
        placeholder={placeholder}
        className={className}
        disabled={disabled}
      />
      
      {showSuggestions && filteredUsers.length > 0 && (
        <div
          ref={suggestionsRef}
          className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto"
        >
          {filteredUsers.map((user, index) => (
            <div
              key={user.id}
              onClick={() => selectUser(user)}
              className={`px-3 py-2 cursor-pointer flex items-center gap-2 ${
                index === selectedIndex
                  ? 'bg-gray-100 dark:bg-gray-700'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
              }`}
            >
              {user.avatar_url ? (
                <Image
                  src={user.avatar_url}
                  alt={user.name}
                  width={32}
                  height={32}
                  className="w-8 h-8 rounded-full"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-myfav-primary to-myfav-primary-dark flex items-center justify-center text-white text-sm">
                  {user.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {user.name}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  @{user.username}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

