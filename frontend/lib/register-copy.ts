/**
 * Bundled register form copy — labels must never render blank on first paint.
 */
import en from './translations/en.json'

const auth = (en as { auth?: Record<string, unknown> }).auth ?? {}
const register = (auth.register as Record<string, unknown>) ?? {}
const errors = (register.errors as Record<string, string>) ?? {}

export const REGISTER_COPY = {
  title: String(register.title ?? 'Join MyHigh5'),
  subtitle: String(register.subtitle ?? 'Create your account and start competing'),
  email: String(auth.email ?? 'Email'),
  username: String(auth.username ?? 'Username'),
  password: String(auth.password ?? 'Password'),
  emailPlaceholder: String(register.email_placeholder ?? 'your@email.com'),
  usernamePlaceholder: String(register.username_placeholder ?? 'Choose a username'),
  passwordPlaceholder: String(register.password_placeholder ?? 'Create a password'),
  confirmPasswordPlaceholder: String(
    register.confirm_password_placeholder ?? 'Confirm password',
  ),
  usernameHint: String(
    register.username_hint ?? 'Only letters, numbers, and underscores are allowed',
  ),
  termsAccept: String(
    register.terms_accept ?? 'I agree to the Terms of Service and Privacy Policy',
  ),
  loading: String(register.loading ?? 'Creating account...'),
  submit: String(register.submit ?? 'Create Account'),
  haveAccount: String(register.have_account ?? 'Already have an account?'),
  loginLink: String(register.login_link ?? 'Sign in'),
  usernameInvalidChars: String(
    errors.username_invalid_chars ??
      'Only letters, numbers, and underscores are allowed',
  ),
} as const
