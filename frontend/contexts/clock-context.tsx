"use client"

import React, { createContext, useContext, useEffect, useState, useMemo } from "react"

interface ClockContextValue {
  now: Date
}

const ClockContext = createContext<ClockContextValue | null>(null)

export function ClockProvider({ children }: { children: React.ReactNode }) {
  const [now, setNow] = useState<Date>(() => new Date())

  useEffect(() => {
    // Sync to the start of the next second to keep all consumers aligned.
    const ms = 1000 - (Date.now() % 1000)
    let timeoutId: ReturnType<typeof setTimeout>
    let intervalId: ReturnType<typeof setInterval>

    const tick = () => setNow(new Date())

    timeoutId = setTimeout(() => {
      tick()
      intervalId = setInterval(tick, 1000)
    }, ms)

    return () => {
      clearTimeout(timeoutId)
      clearInterval(intervalId)
    }
  }, [])

  const value = useMemo(() => ({ now }), [now])
  return <ClockContext.Provider value={value}>{children}</ClockContext.Provider>
}

export function useClock(): Date {
  const ctx = useContext(ClockContext)
  if (!ctx) {
    throw new Error("useClock must be used within a ClockProvider")
  }
  return ctx.now
}
