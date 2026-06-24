import { describe, expect, it } from 'vitest'
import { REGISTER_COPY } from './register-copy'

describe('REGISTER_COPY', () => {
  it('includes all labels required on the register form', () => {
    expect(REGISTER_COPY.title.length).toBeGreaterThan(0)
    expect(REGISTER_COPY.email.length).toBeGreaterThan(0)
    expect(REGISTER_COPY.username.length).toBeGreaterThan(0)
    expect(REGISTER_COPY.password.length).toBeGreaterThan(0)
    expect(REGISTER_COPY.emailPlaceholder.length).toBeGreaterThan(0)
    expect(REGISTER_COPY.submit.length).toBeGreaterThan(0)
  })
})
