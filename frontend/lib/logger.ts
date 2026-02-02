/**
 * Logger utility for frontend
 * Replaces console statements with proper logging
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

class Logger {
  private isDevelopment = process.env.NODE_ENV === 'development'

  private log(level: LogLevel, message: string, ...args: unknown[]): void {
    if (!this.isDevelopment && level === 'debug') {
      return // Don't log debug in production
    }

    const timestamp = new Date().toISOString()
    const prefix = `[${timestamp}] [${level.toUpperCase()}]`

    switch (level) {
      case 'debug':
        if (this.isDevelopment) {
          console.debug(prefix, message, ...args)
        }
        break
      case 'info':
        if (this.isDevelopment) {
          console.info(prefix, message, ...args)
        }
        break
      case 'warn':
        console.warn(prefix, message, ...args)
        break
      case 'error':
        console.error(prefix, message, ...args)
        // In production, you might want to send errors to a logging service
        // e.g., Sentry, LogRocket, etc.
        break
    }
  }

  debug(message: string, ...args: unknown[]): void {
    this.log('debug', message, ...args)
  }

  info(message: string, ...args: unknown[]): void {
    this.log('info', message, ...args)
  }

  warn(message: string, ...args: unknown[]): void {
    this.log('warn', message, ...args)
  }

  error(message: string, error?: unknown, ...args: unknown[]): void {
    if (error instanceof Error) {
      this.log('error', message, error.message, error.stack, ...args)
    } else {
      this.log('error', message, error, ...args)
    }
  }
}

export const logger = new Logger()
