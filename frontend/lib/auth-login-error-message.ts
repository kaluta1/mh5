import type { AxiosError } from 'axios'

function looksLikeGatewayHtml(body: string): boolean {
  const s = body.slice(0, 800).toLowerCase()
  return (
    s.includes('<html') ||
    s.includes('<!doctype') ||
    s.includes('bad gateway') ||
    s.includes('gateway timeout') ||
    s.includes('nginx/')
  )
}

/**
 * Map login failures to a short user-facing string. Never surface raw HTML from nginx/502 bodies.
 */
export function resolveAuthLoginErrorMessage(
  err: unknown,
  t: (key: string) => string | undefined
): string {
  const fallbackInvalid = () => t('auth.login.errors.invalid_credentials') || 'Invalid credentials'
  const fallbackNetwork = () => t('auth.login.errors.network_error') || 'Network error. Please try again.'
  const fallbackUnavailable = () =>
    t('auth.login.errors.service_unavailable') ||
    'The server is temporarily unavailable. Please try again in a moment.'
  const fallbackTimeout = () => t('auth.login.errors.timeout') || 'Request timed out. Please try again.'

  const axiosError = err as AxiosError
  const status = axiosError.response?.status

  if (status === 503 || status === 502 || status === 504 || status === 500) {
    return fallbackUnavailable()
  }

  if (axiosError.code === 'ECONNABORTED' || axiosError.message?.includes('timeout')) {
    return fallbackTimeout()
  }

  if (!axiosError.response && axiosError.request) {
    return fallbackNetwork()
  }

  const mapInvalid = (message: string): string => {
    const lowerMessage = message.toLowerCase()
    if (
      lowerMessage.includes('incorrect') ||
      lowerMessage.includes('invalid') ||
      lowerMessage.includes('invalide') ||
      lowerMessage.includes('inválido') ||
      lowerMessage.includes('ungültig') ||
      (lowerMessage.includes('email') &&
        (lowerMessage.includes('password') ||
          lowerMessage.includes('mot de passe') ||
          lowerMessage.includes('contraseña') ||
          lowerMessage.includes('passwort'))) ||
      (lowerMessage.includes('username') &&
        (lowerMessage.includes('password') ||
          lowerMessage.includes('mot de passe') ||
          lowerMessage.includes('contraseña') ||
          lowerMessage.includes('passwort'))) ||
      (lowerMessage.includes("nom d'utilisateur") && lowerMessage.includes('mot de passe')) ||
      (lowerMessage.includes('nombre de usuario') && lowerMessage.includes('contraseña')) ||
      (lowerMessage.includes('benutzername') && lowerMessage.includes('passwort'))
    ) {
      return fallbackInvalid()
    }
    return message
  }

  const data = axiosError.response?.data
  if (data !== undefined && data !== null) {
    if (typeof data === 'string') {
      if (looksLikeGatewayHtml(data)) {
        return fallbackUnavailable()
      }
      return mapInvalid(data)
    }
    if (typeof data === 'object' && 'detail' in data) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') {
        if (looksLikeGatewayHtml(detail)) {
          return fallbackUnavailable()
        }
        return mapInvalid(detail)
      }
      if (Array.isArray(detail)) {
        const messages = detail
          .map((e) => (typeof e === 'object' && e && 'msg' in e ? String((e as { msg: unknown }).msg) : String(e)))
          .join(', ')
        return mapInvalid(messages)
      }
    }
    if (typeof data === 'object' && data && 'message' in data) {
      const m = (data as { message?: unknown }).message
      if (typeof m === 'string') {
        if (looksLikeGatewayHtml(m)) {
          return fallbackUnavailable()
        }
        return mapInvalid(m)
      }
    }
  }

  if (axiosError.message) {
    if (looksLikeGatewayHtml(axiosError.message)) {
      return fallbackUnavailable()
    }
    return mapInvalid(axiosError.message)
  }

  return fallbackInvalid()
}
