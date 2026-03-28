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
          return (
            <span
              key={`${part}-${index}`}
              className="font-medium text-myhigh5-primary dark:text-myhigh5-blue-400"
            >
              {part}
            </span>
          )
        }

        return <Fragment key={`${part}-${index}`}>{part}</Fragment>
      })}
    </>
  )
}
