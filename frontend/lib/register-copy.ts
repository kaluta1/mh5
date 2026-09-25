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
  dateOfBirth: String(register.date_of_birth ?? 'Date of birth'),
  dateOfBirthHint: String(
    register.date_of_birth_hint ??
      'Used to apply age-appropriate protections. It is never shown on your public profile.',
  ),
  dateOfBirthRequired: String(errors.date_of_birth_required ?? 'Please enter your date of birth'),
  guardianEmail: String(register.guardian_email ?? "Parent or guardian's email"),
  guardianEmailHint: String(
    register.guardian_email_hint ??
      'We will ask them to review your request. Your account is created only after they approve.',
  ),
  guardianPendingTitle: String(register.guardian_pending_title ?? 'Waiting for your parent or guardian'),
  loading: String(register.loading ?? 'Creating account...'),
  submit: String(register.submit ?? 'Create Account'),
  haveAccount: String(register.have_account ?? 'Already have an account?'),
  loginLink: String(register.login_link ?? 'Sign in'),
  usernameInvalidChars: String(
    errors.username_invalid_chars ??
      'Only letters, numbers, and underscores are allowed',
  ),
} as const
