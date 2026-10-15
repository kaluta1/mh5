# Kaluta KYC (default provider)

MyHigh5 uses **Kaluta KYC** for identity verification. **Shufti Pro** remains in the codebase as a legacy provider (`KYC_PROVIDER=shufti_pro`).

Provider documentation: <https://kalutakyc.com/docs>.

## Settings: managed in the Admin Panel only (the database is the single source)

Admin → KYC → **Kaluta KYC settings** (`GET|PUT /api/v1/kyc/admin/settings`), one form and one Save button:

| Setting | Stored as | Notes |
|---|---|---|
| Kaluta KYC on/off | `kyc_settings.kaluta_enabled` (one row) | No row / NULL = **off**. Switching on is refused unless a key and a secret are saved and readable and `KYC_PROVIDER` is `kaluta` |
| Kaluta API key | AES-256-GCM ciphertext in `payment_credentials` (`provider = 'kaluta'`, name `API_KEY`) | Write-only. Never shown again, logged, audited or returned; the page shows only *configured / not configured* |
| Kaluta webhook secret | same (`WEBHOOK_SECRET`) | A URL-shaped value is refused (the known mistake of pasting the webhook URL) |
| Member KYC fee (USD) | `product_types.price` of `kyc` | 0 to 1000.00, two decimals; 0 = free. See below |
| Sessions per attempt | `kyc_settings.sessions_per_attempt` | 1 to 10 (CHECK constraint); NULL = the default 3 (migration `e6f7a8b9c0d1`) |
| Webhook URL | not stored | Read-only, with a Copy button, for the Kaluta dashboard |

- **The server environment is not read** for the on/off switch, the key or the secret: `KALUTA_KYC_ENABLED`, `KALUTA_API_KEY` and `KALUTA_WEBHOOK_SECRET` have no effect. If they are present, startup prints `IGNORED: <names>` (names only, never values). Nothing is copied from them into the database.
- **Fail closed.** No saved settings, a key or secret that cannot be decrypted (e.g. a different `PAYMENT_SETTINGS_ENCRYPTION_KEY`), or a database read error: Kaluta KYC is treated as off. `initiate` answers 503 before anything is opened (no attempt, no payment used); the webhook answers 503 when off and 401 when no readable secret is saved. A webhook is never accepted unsigned, in any environment.
- Encryption uses the dedicated `PAYMENT_SETTINGS_ENCRYPTION_KEY` (the Finance & Payments key; HKDF purpose `mh5-kyc:kaluta-credential:<name>`, so a KYC ciphertext can never be read as a payment credential). Without that key a key or secret cannot be saved (409 `ENCRYPTION_KEY_MISSING`).
- A blank key/secret field keeps the saved value; saving a new one replaces it. There is no "delete" (rotation = replace).
- One save is ONE transaction: every value is validated first (422 with `field` = `MEMBER_FEE`, `SESSIONS_PER_ATTEMPT`, `API_KEY` or `WEBHOOK_SECRET`), and any refusal (bad value, stale page, switching on without a secret, missing `kyc` product) leaves everything as it was.
- Every change needs the explicit `manage_kyc_settings` permission (or a Super Admin) AND the administrator's current password (shared wrong-password lockout), is refused if the page was stale (`expected_version`, `expected_fee`), and writes one `audit_trails` row `KYC_SETTINGS_CHANGED` naming what changed (`API_KEY`, `WEBHOOK_SECRET`, `KALUTA_ENABLED`, `MEMBER_FEE`, `SESSIONS_PER_ATTEMPT`) with the old and new on/off, fee and sessions values. Never a key or secret. A fee change also writes its own `KYC_MEMBER_FEE_CHANGED` row.
- The saved values are re-read on every KYC request, so a change takes effect on every worker without a restart.

Server environment (only what is not a KYC setting):

```env
KYC_PROVIDER=kaluta
```

Optional overrides (defaults are derived from `BACKEND_PUBLIC_URL` and `FRONTEND_URL`):

```env
KALUTA_WEBHOOK_URL=https://myhigh5.com/api/v1/kyc/webhook/kaluta
KALUTA_REDIRECT_URL=https://myhigh5.com/dashboard/kyc
```

The key and the secret never reach a browser, a log line or an API answer.

## The `manage_kyc_settings` permission

Created by migration `b3c4d5e6f7a8` and assigned to NO role and NO user. It is not implied by `is_admin`, by the `all` wildcard or by `manage_payment_settings`, and it cannot be given through the role management API (it is a protected permission). Until it is granted, nobody can change the KYC fee or the Kaluta settings or allow an extra session; administrators can still view them.

Secure grant procedure (on the server, by the operator, one named administrator at a time):

1. Confirm the target account is an active administrator who should hold it and uses a strong, recently set password.
2. Dry run (writes nothing; prints the database host/name and the role that would be used):
   `python -m app.scripts.grant_payment_permissions --email <admin email> --permission manage_kyc_settings`
3. Check the printed database and role name (`finance_manager_k_<base role>`, or with other letters if the account already holds Finance & Payments permissions from this tool).
4. Apply: the same command with `--apply`. The account moves to a dedicated role that inherits its current role, so it keeps every permission it had and nobody else is affected. One `audit_trails` row `PAYMENT_PERMISSION_GRANTED` is written.
5. Revoke: `... --revoke --permission manage_kyc_settings --apply`.

Nothing is granted by default and there is no "grant all".

## What the provider documents

| Topic | Contract |
|---|---|
| Authentication | `X-API-Key: klt_...` on server-to-server calls |
| Create a session | `POST https://kalutakyc.com/v1/sessions` → `session_id`, `verification_url`, `expires_at` |
| Session lifetime | 24 hours |
| Statuses | `created`, `document_submitted`, `face_submitted`, `approved`, `rejected`, `expired` |
| Decision | Automatic; score 60 and above is approved |
| Webhook signature | `X-Kaluta-Signature: t=<unix>,v1=<hex>`; `v1` = HMAC-SHA256 of `<t>.<raw body>`; refuse when `t` is older than 5 minutes |
| Webhook events | `session.created`, `.document_submitted`, `.face_submitted`, `.approved`, `.verified` (alias of approved), `.rejected`, `.expired` |
| Delivery | Retried with backoff until a 2xx within 10 seconds; handlers must be idempotent |
| Retries | After a rejection the member can retry in the widget: a NEW session with the SAME `external_id` |
| Billing | Per completed verification; one charge covers a block of 3 attempts |

## Flow

1. The member sees the Member KYC Verification Fee and, unless it is 0, pays it through the existing payment flow (see below).
2. `POST /api/v1/kyc/initiate` (signed-in member) creates a Kaluta session server-side. `external_id` is our reference (`mh5_<user>_<random>`); the session id, URL and expiry are stored on the single `kyc_verifications` row of that member.
3. The frontend opens `KalutaKYC.open({ url })` from `https://kalutakyc.com/embed.js`. Only an `https://kalutakyc.com/...` URL is opened. If the script cannot load, the member is offered the provider's hosted page.
4. When the widget finishes, the frontend reads `GET /api/v1/kyc/status-detailed` (a few times, the webhook can be a moment late). What the widget or the redirect query string says is never taken as the result.
5. Kaluta posts to `POST /api/v1/kyc/webhook/kaluta`. The signature is checked on the raw body before anything is read or looked up.
6. Identity accepted → the existing proof-of-address step, unless Kaluta itself verified the address in the session.

## Member KYC Verification Fee

One figure, in USD: what a member pays MyHigh5 for one new verification attempt. It is the price of the existing `kyc` product (`product_types.price`), the row the payment flow already charges from. What Kaluta charges MyHigh5 is not configured, stored or calculated in MyHigh5.

| Rule | Behaviour |
|---|---|
| Who sets it | An administrator with the `manage_kyc_settings` permission (NOT `manage_payment_settings`), confirming with their current password (Admin → KYC). The KYC settings form (`PUT /api/v1/kyc/admin/settings`, field `member_fee`; the older `PUT /api/v1/kyc/admin/fee` still works under the same rules); each change writes one `audit_trails` row (`KYC_MEMBER_FEE_CHANGED`, old and new amount) |
| Range | 0 to 1000.00, at most two decimals |
| Free KYC | Fee 0: an attempt starts without a payment, and a KYC payment cannot be created (409 `KYC_FEE_NOT_REQUIRED`). A paid, unused KYC payment the member already holds is NOT used: it stays paid and unused, unchanged, and opens a later attempt once the fee is no longer 0 |
| Shown to the member | `GET /api/v1/kyc/fee` and `status-detailed` (`kyc_price`, `kyc_is_free`), on the KYC page before the member starts |
| Existing payments | A payment keeps the amount it was created with (`deposits.amount`), paid or not. A paid, unused payment opens one attempt whatever the (non-zero) fee is now |
| Retry | Every NEW attempt (after a rejection or a review) costs the fee in force when it is paid for; free while the fee is 0. Continuing an open attempt, or renewing a session that ran out, costs nothing and is not a new attempt. `max_attempts` applies to new attempts |
| No duplicate charge | A new KYC payment is refused (409) when the member holds a paid, unused KYC payment, has a KYC payment in progress (partially paid, or an unpaid invoice less than one hour old), has an attempt open, is verified, or has no attempt left. The member's row is locked while the payment is created, so requests arriving together create one. One payment opens one attempt |
| Trail | Each attempt writes a `kyc_audit_logs` row `kyc_attempt_fee`: the payment and amount used, or that no fee applied |

The commission and ledger rules of a KYC payment are unchanged: they work from the amount of the payment that was made. A free attempt creates no payment, so no ledger entry and no commission.

## Webhook handling

The handler locks the verification row, decides on its CURRENT status, and answers `{"ok": true, "result": ...}`:

| Result | Meaning |
|---|---|
| `applied` | The event changed the verification (or a progress event was noted) |
| `duplicate` | The same decision was already applied; nothing changed, no second email |
| `ignored` | A late or superseded event (after a decision, another provider, an earlier reference, an older session) |
| `unknown` | No verification has this reference or session; acknowledged so that it is not retried |

Rules:

- An approval is applied to an open verification, or to one the PROVIDER rejected for the same reference (the member retried in the widget). It never reopens a verification an administrator rejected, an `expired` one (older records), or one under review.
- A rejection is applied to an open verification only. An expiry is applied to the CURRENT session of an open verification only, and ends that session, not the attempt (see below).
- Progress events never overwrite a decision.
- An event whose name and `session.status` disagree decides nothing.
- Every delivery that concerned a verification writes one `kyc_audit_logs` row (event, outcome, session id; no personal data).
- The raw model output (`ai_extraction`) is not stored; the decision, the scores and the extracted identity are.

Unsigned, wrongly signed or stale deliveries get 401; a body that is not a JSON object gets 400; with the integration switched off the endpoint answers 503.

## Session expiry

A provider session that runs out never uses up the member's paid attempt.

- The expiry returned by the provider is stored. Once it has passed, or a `session.expired` webhook (or a status read reporting `expired`) arrives for the CURRENT session, the verification stays open (`in_progress`, same attempt, same payment) and only the session is ended: the link is no longer handed out and `status-detailed` reports `session_expired: true`. An expiry is never treated as a rejection.
- The next "continue" opens a fresh session for the SAME attempt: new reference, no payment, `attempts_count` unchanged. A KYC payment is refused meanwhile (409 `KYC_ATTEMPT_OPEN`).
- Older records with status `expired` are treated the same way: an open attempt whose session ended.
- **Limit.** Each provider session may be charged to MyHigh5, so one attempt may open at most the **sessions per attempt** setting (default 3) (`kyc_verifications.attempt_sessions_count`; `force_new` counts too). The session is taken under the member's row lock BEFORE the provider is asked, so requests arriving together cannot pass the limit. It is given back only when the provider certainly opened nothing (4xx answer, or switched off); after a timeout or a 5xx it stays counted. `status-detailed` reports `sessions_remaining` and `session_limit_reached`; past the limit `initiate` answers 409 `KYC_SESSION_LIMIT_REACHED` and the member is asked to contact support.
- **Controlled recovery.** An administrator with `manage_kyc_settings` can allow ONE more session for that open attempt (`POST /api/v1/kyc/admin/verification/{id}/grant-session`, current password; refused while the member still has a session, at most 3 extra per attempt). Each grant writes `kyc_audit_logs` (`kyc_session_granted`) and `audit_trails` (`KYC_SESSION_GRANTED`). No payment and no new attempt.
- A new attempt (after a rejection or a review) starts with a full allowance.
- The last attempt (`attempts_count == max_attempts`) can still renew its session; `max_attempts` limits new attempts only.

## Provider cannot be used

A refused key (401), an empty balance (402), a rate limit (429), a provider fault, a timeout or an unusable answer all give the member `503` with one generic sentence. The cause is in the server log (status code only). The call is not repeated automatically; the member can start the same paid attempt again. With Kaluta switched off or without a key, `initiate` answers 503 before anything is opened: no attempt starts and no payment is used.

## Kaluta dashboard setup

1. Add the webhook endpoint `{BACKEND_PUBLIC_URL}/api/v1/kyc/webhook/kaluta`.
2. Subscribe to `session.approved` (or `session.verified`), `session.rejected`, `session.expired`. Progress events are optional.
3. Save the webhook signing secret and an API key in Admin → KYC → Kaluta KYC settings (the server environment is not used). The webhook URL to register is shown there with a Copy button.
4. Keep a balance on the account (Dashboard → Billing).

`GET /api/v1/kyc/deployment/kaluta-urls` (administrators) shows the URLs this server uses and whether a key and a secret are configured, without their values.

## Open points (not decided in code)

- **Reading a session back.** The documentation's example for `GET /v1/sessions/{id}` shows a dashboard JWT, not the API key. The status poll uses the API key and is treated as best-effort: if it is refused, nothing changes and the webhook decides.
- **Provider retries inside the widget.** Retries after a rejection happen inside the provider's widget (same session reference) and are unlimited and billed by the provider; MyHigh5 cannot cap them. The session limit above caps only the sessions MyHigh5 opens.
- **Refund of an unused payment while KYC is free.** A member who paid and then gets free KYC keeps the unused payment; whether to refund it is not decided in code.

## Legacy Shufti Pro

Set `KYC_PROVIDER=shufti_pro` and configure `SHUFTI_CLIENT_ID`, `SHUFTI_SECRET_KEY`. Webhook: `/api/v1/kyc/webhook/shufti-pro`.
