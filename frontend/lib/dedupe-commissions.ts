export type DedupeCommissionRow = {
  id: string
  level: number
  depositId?: number
  commissionType: string
  createdAt: string
  sourceUser: {
    name: string
    username?: string
  }
}

/** One row per payment in history — keeps lowest network level when duplicates exist. */
export function dedupeCommissionRows<T extends DedupeCommissionRow>(rows: T[]): T[] {
  const kept = new Map<string, T>()

  for (const row of rows) {
    const key =
      row.depositId != null
        ? `deposit:${row.depositId}`
        : `legacy:${row.sourceUser.username ?? row.sourceUser.name}:${row.commissionType}:${row.createdAt.slice(0, 10)}`

    const previous = kept.get(key)
    if (!previous) {
      kept.set(key, row)
      continue
    }

    if (row.level < previous.level) {
      kept.set(key, row)
      continue
    }

    if (row.level === previous.level && Number(row.id) < Number(previous.id)) {
      kept.set(key, row)
    }
  }

  return Array.from(kept.values())
}
