import Link from 'next/link'
import { Fragment } from 'react'

const MENTION_REGEX = /(@[A-Za-z0-9_]+)/g
const SINGLE_MENTION_REGEX = /^@[A-Za-z0-9_]+$/

interface MentionTextProps {
  text: string
}

export function MentionText({ text }: MentionTextProps) {
  const parts = text.split(MENTION_REGEX)

  return (
    <>
      {parts.map((part, index) => {
        if (!part) return null

        if (SINGLE_MENTION_REGEX.test(part)) {
          const username = part.slice(1)

          return (
            <Link
              key={`${part}-${index}`}
              href={`/dashboard/users/username/${encodeURIComponent(username)}`}
              className="font-medium text-myhigh5-primary dark:text-myhigh5-blue-400"
            >
              {part}
            </Link>
          )
        }

        return <Fragment key={`${part}-${index}`}>{part}</Fragment>
      })}
    </>
  )
}
