"use client"

import React, { createContext, useContext, useEffect, useState, useMemo } from "react"

interface ClockContextValue {
  now: Date
}

const ClockContext = createContext<ClockContextValue | null>(null)

export function ClockProvider({ children }: { children: React.ReactNode }) {
  const [now, setNow] = useState<Date>(() => new Date())

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>
    let intervalId: ReturnType<typeof setInterval>

    const tick = () => setNow(new Date())

    const start = () => {
      const ms = 1000 - (Date.now() % 1000)
      timeoutId = setTimeout(() => {
        tick()
        intervalId = setInterval(tick, 1000)
      }, ms)
    }

    const stop = () => {
      clearTimeout(timeoutId)
      clearInterval(intervalId)
    }

    const onVisibility = () => {
      stop()
      if (!document.hidden) start()
    }

    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
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
