# Accounting, Security & External Integrations Repair Report

Date: 2026-09-09  
Scope: Prompt 9 only; Prompts 2-8 remain unapproved and undeployed.  
Implementation status: **PARTIAL**.

Prompt 9 repaired the immediately exploitable registration, KYC webhook, financial GraphQL, token-in-URL, SSRF, raw-rendering, provider-route, and production-configuration weaknesses. It also completed a read-only production accounting/security audit. The result is not deployment-ready: required database constraints cannot be applied while Alembic is divergent, two historical commission postings remain missing, wallet provenance remains unproved, two committed NOWPayments secrets require controlled rotation, and several defense-in-depth items need infrastructure work.

No production row or schema was changed. No provider mutation, payment, payout, refund, KYC request, email payment request, deployment, migration, stamp, or service restart occurred.

## 1. Accounting coverage

`journal_entries` plus `journal_lines` are authoritative double-entry accounting only for the business events that call the canonical posting services. They are not a universal reconstruction of every historical or dormant money-like table.

**Covered by canonical ledger:**

- validated fixed-price KYC cash receipt, deferred revenue, recognition, provider/pool allocations, and related affiliate payables;
- annual and founding membership receipts, recognition/allocation, and commission payables;
- generic club-membership accounting helper, although there is no operational club order/entitlement system and it must remain dormant;
- affiliate commission accrual generated from a covered deposit;
- affiliate commission cashout/payout posting;
- full payment refund reversal, unpaid-commission reversal, paid-commission receivable, and founding-point compensating entry;
- AnnualAds sponsor-payment receipt and scheduled revenue recognition;
- founding-member point ledger movements where the existing FMP service applies them.

**Partial:**

- historical deposit/commission coverage: two approved USD 1.00 commissions have no payable posting;
- payout/refund/provider-event source identity is partly encoded in descriptions and application references rather than first-class constrained source columns;
- the admin payment-grant path uses canonical server pricing/posting and now has an audit record, but historical grants are not universally represented by a typed financial-event table;
- KYC provider expense/recognition coverage exists only where the canonical KYC posting path is reached.

**Not covered, legacy, or dormant:**

- singular legacy `wallet`, plural unmapped `wallets`, empty legacy `transactions`/`user_transactions`, and arbitrary balance-like legacy fields;
- variable-price `ad_credit`, `dsp_topup`, and `shop_purchase`, which deliberately fail closed until an authoritative order model exists;
- internal native advertising finance, Premium Club payments/payouts, and marketplace checkout/earnings/entitlements;
- dormant accounting/revenue endpoint modules that are not registered in the active API router.

No journal history was synthesized to hide these gaps.

## 2. Accounting event matrix

Account codes below describe the current code-supported flow. A dash means the feature is absent/dormant, not that a posting was fabricated.

| Event | Source | Debit | Credit | Currency | Journal | Reversal | Idempotency | Status |
|---|---|---|---|---|---|---|---|---|
| KYC cash receipt | `deposits.id` | cash `1001` | deferred KYC `2113` | USD | Yes | Full refund | order/provider binding + deposit lock | Covered |
| KYC recognition | KYC verification + deposit | deferred `2113`; expense/allocation accounts as applicable | KYC revenue `4001`; provider/pool payables | USD | Yes | Compensating entry | description/source guards; needs typed unique event | Covered/partial schema |
| Annual membership | `deposits.id` | cash `1001`; commission expense `5001` | deferred `2110`, revenue `4002`, commission/provider payables | USD | Yes | Full refund | unique order + locked deposit + commission uniqueness | Covered |
| Founding membership | `deposits.id` | cash `1001`; commission expense `5001` | deferred `2111`, revenue `4002`, commission/payables | USD | Yes | Full refund + FMP reversal | same as deposit plus FMP source check | Covered |
| Affiliate commission accrual | `affiliate_commissions.deposit_id` | commission expense/allocation | direct/indirect payables `2001`/`2002` | USD | Yes for covered deposits | Cancel/reverse; paid amount becomes receivable | application check + existing partial unique index | Covered except deposits 51/53 |
| Affiliate withdrawal/payout | `affiliate_cashout_requests` + commission IDs | payables `2001`/`2002` and fee treatment | cash `1001` / fee revenue `4005` | USD settled as USDT-BSC | Yes | Unknown outcome is reserved for review | durable intent, user/row locks, provider reference | Covered; schema hardening required |
| Full provider refund | original `deposits.id` | mirror of original credits; receivable `1200` if commission already paid | mirror of original debits and payable restoration as applicable | original USD | Yes, compensating | Idempotent full reversal | deposit lock + durable state/description; event table needed | Covered |
| Partial refund | deposit/provider event | — | — | — | No | No guessed allocation | rejected | Fail closed/manual review |
| AnnualAds sponsor receipt | provider transaction hash | USDT cash `1030` | deferred sponsor revenue `2310` | USDT-BSC | Yes | No automatic refund policy invented | advisory lock + existing-entry check | Covered; unique event constraint needed |
| AnnualAds recognition | recognized receipt | deferred `2310` | sponsor revenue `4010` plus defined loss/receivable treatment | USDT-BSC | Yes | Compensating journal possible | existing receipt identity | Covered |
| Admin payment grant | `deposits.id`, actor | same product flow as validated server-priced deposit | same product flow | USD | Yes | canonical refund path | order/provider checks + audit | Covered for new operations |
| Club membership helper | deposit only | cash/club allocation accounts | deferred/revenue/payables | USD | Code exists | canonical full refund can apply | deposit/commission guards | Dormant; no operational entitlement source |
| Native-ad payment/spend | dormant advertising tables | — | — | — | No canonical operational flow | No | No | Dormant/fail closed |
| Marketplace order/seller earning | no operational canonical order | — | — | — | No | No | No | Dormant/fail closed |

Production validation of the ledger itself found 38 journals with zero missing-line, one-sided, unbalanced, header-mismatch, both-sided-line, zero-line, zero-value, or orphan-account anomalies.

## 3. Wallet provenance

The read-only production audit established:

- plural `wallets` has five USD rows for existing users 235-239;
- balances are USD 428.00, 153.00, 339.00, 824.00, and 697.00, totaling **USD 2,441.00**;
- frozen balances total USD 0.00;
- all were created within roughly 27 seconds on 2026-06-10; `updated_at` equals `created_at` for every row;
- the table has no foreign keys;
- the active codebase has no ORM model, registered API, or write service for plural `wallets`; references are confined to read-only audit tooling;
- repository history inspected for this task does not establish a plural-wallet model or creation workflow; the historical ORM maps singular `wallet`, which is empty in production;
- the active affiliate wallet API derives balances from `affiliate_commissions`, not either wallet table.

Classification: **probable migration/import artifact or legacy snapshot; exact provenance UNKNOWN**. It is neither proven authoritative nor safe to discard. No amount was merged, mapped, or changed.

## 4. USD 2.00 discrepancy investigation

Production has 14 APPROVED affiliate commissions totaling **USD 38.00**. Commission-payable accounts `2001`/`2002` total **USD 36.00**, a **USD -2.00** accounting difference.

The complete source-level difference is now identified:

| Source record | Expected accounting | Actual payable posting | Difference |
|---|---:|---:|---:|
| Deposit 51 / affiliate commission 1, level 1 | USD 1.00 | USD 0.00 | USD -1.00 |
| Deposit 53 / affiliate commission 3, level 1 | USD 1.00 | USD 0.00 | USD -1.00 |

All other deposit-backed approved commission sources (52, 54-58, and 64-69) reconcile exactly. The second dollar is therefore no longer UNKNOWN: deposit 53 explains it. Production was not corrected; resolution requires reviewed compensating journals after migration/source-identity approval.

## 5. Authentication architecture

- Primary users: email/password with Passlib hashing and bearer JWT access tokens.
- Admins: the same authentication, followed by server-side active/admin role checks. GraphQL financial queries now use the same admin requirement.
- Email/reset flows: typed JWTs with issuer, audience, issued-at, unique ID, expiration, and token purpose.
- Password reset: token is bound to a hash of the current stored password hash; after a successful reset, replay fails because the binding changes.
- Service-to-service: provider-specific webhook signatures; the scheduler/cron bridge uses its configured service secret.
- OAuth/SSO: AnnualAds embed SSO is an application-to-provider signed contract, not an alternate application login.

Access/email/reset tokens created before this patch lack the new issuer/audience/type claims and will be invalid after deployment. That is a deliberate secure cutover effect and needs user communication. Remaining P1 work is refresh rotation/revocation: browser access tokens are still long-lived (seven days), stored in `localStorage`, and logout has no server-side blacklist.

## 6. Authorization matrix

Authorization is enforced by backend dependencies and ownership checks, not frontend visibility.

| Role | Public/read own | Create/update own | Read others | Admin/financial action |
|---|---|---|---|---|
| Anonymous | public contests/categories/media-safe views | register/login and signed webhooks only | No private data | No |
| User | own profile, KYC, payment, affiliate/wallet views | permitted own actions | denied unless resource is public | No |
| Advertiser | ordinary user only | AnnualAds embed under signed server contract | No native campaign administration | native system dormant |
| Seller | ordinary user only | no operational marketplace seller flow | No | dormant/fail closed |
| Club owner | ordinary user only | no operational Premium Club finance flow | No | dormant/fail closed |
| Moderator | no consistently defined broad platform role | route-specific only where present | no implicit admin powers | No general financial authority |
| Admin | admin-scoped views/actions | moderated state changes | authorized admin scope | Yes, audited where repaired |
| Superadmin | stored role plus admin flag semantics | same registered admin router currently | admin scope | no separate universal bypass inferred |
| Service account/provider | no interactive access | one authenticated callback/cron contract | No | only idempotent bound event action |

The dormant accounting REST module is not registered. The registered GraphQL accounting reads were previously anonymous and are now admin-only with bounded pagination.

## 7. IDOR findings

Repairs and verified controls:

- public registration cannot select `is_admin`, `is_verified`, `is_active`, owner, status, or balance fields;
- payment invoice retrieval no longer accepts a JWT in a query string and requires the authenticated bearer session;
- financial GraphQL data requires an active admin;
- KYC deployment diagnostics now require admin rather than any logged-in user;
- wallet and withdrawal handlers derive the owner from the authenticated user and reserve only that user's commissions;
- Prompt 4 media ownership and Prompt 7 campaign ownership guards remain intact;
- Prompt 8 club/marketplace mutation routes remain unregistered/fail closed.

No active endpoint was found that permits user A to mutate user B's wallet, payment, withdrawal, campaign, club, marketplace order, or private media by submitting another ID. The largest remaining authorization risk is consistency: legacy routers use a mix of boolean `is_admin`, role fields, and RBAC permissions. These need one policy layer before adding more privileged features.

## 8. Admin security

The `/api/v1/admin` router has a router-wide admin dependency and sensitive handlers retain resource-specific checks. Prompt 9 additionally:

- replaced free-form role/status bodies with strict Pydantic DTOs that forbid extra fields;
- bounded payment-grant notes and forbade unknown grant fields;
- records durable `AuditTrail` entries for role changes, active-status changes, soft delete, KYC verify/unverify, KYC-with-grant, and manual payment grant within the same transaction;
- keeps the prior TOTP disclosure endpoint disabled;
- leaves state changes on POST/PATCH/DELETE rather than GET;
- restricts the KYC configuration diagnostic endpoint to admins.

Remaining P1: normalize every legacy admin exception so client errors never echo raw provider/database messages, and make audit-event structure/immutability database-enforced.

## 9. Mass-assignment findings

`UserCreate` and `UserUpdate` now use `extra="forbid"`. Registration forces active=true, verified=false, and admin=false server-side. User update no longer accepts password or privileged flags through the generic DTO. Admin changes use dedicated strict DTOs.

The immediately exploitable privilege escalation was fixed and tested (privileged registration fields return 422). Dormant club/marketplace schemas were already fail-closed by Prompt 8. Any future generic `model_update(**payload)` use must retain explicit allowlists.

## 10. Webhook inventory

| Webhook | Authentication | Timestamp | Replay/idempotency | Binding | Error behavior |
|---|---|---|---|---|---|
| NOWPayments `/api/v1/webhooks/nowpayments` | HMAC-SHA512 over provider canonical JSON; constant-time comparison | provider payload status/identity; no separate signed timestamp in current contract | deposit row lock, terminal-state handling, commission uniqueness | local order/payment ID, server price/currency | reject invalid signature/identity before mutation |
| AnnualAds `/api/v1/webhooks/sponsor-payment` | HMAC-SHA256 over timestamp plus raw body | 5-minute window | transaction advisory lock and existing posting check | event type, tenant contract, transaction hash, net/fee/asset | missing secret or mismatch fails closed |
| Kaluta `/api/v1/kyc/webhook/kaluta` | HMAC-SHA256 over timestamp plus raw body; constant-time | 300 seconds | terminal transition idempotency; stale downgrade rejected | reference/session and metadata user ID | invalid/expired signature rejected before parsing/mutation |
| Shufti `/api/v1/kyc/webhook/shufti-pro` | provider response signature from exact raw body and configured secret; constant-time | provider contract has no application timestamp field used here | terminal state idempotency; stale downgrade rejected | stored verification reference | endpoint is 404 unless Shufti is active; invalid signature rejected first |
| UploadThing callback | UploadThing SDK/server secret contract | SDK-managed | file/ownership validation in callback workflow | authenticated uploader metadata | provider failure denies finalization |

The Shufti verification implementation follows the provider's documented response-signature construction and validates the exact raw body before parsing: [Shufti Pro verification responses](https://developers.shuftipro.com/docs/verification_endpoints/responses) and [Shufti eIDV response reference](https://eidv.shuftipro.com/response/).

## 11. Webhook security

The unauthenticated Shufti approval path is repaired. While Kaluta is active, the legacy Shufti mutating endpoint is unreachable (404). If Shufti is deliberately enabled later, its configured secret and valid raw-body signature are mandatory. Neither user-controlled JSON nor a parsed/re-serialized body can mark KYC approved.

Kaluta validates signature/timestamp before JSON processing, binds provider metadata to the stored user where available, and prevents replay/stale rejection from downgrading terminal approval. NOWPayments binds provider IDs, price, currency, and order before finalization. AnnualAds validates timestamp, tenant/event semantics, positive Decimal amounts, fee/net equality, BSC asset, and transaction identity.

Application replay safety is present now. P0 database event uniqueness remains required for crash/concurrency finality across every provider.

## 12. KYC integrations

- **Kaluta KYC — ACTIVE/default:** bounded HTTP timeouts, signed raw webhook, 300-second timestamp validation, session/reference and user binding, idempotent terminal transitions, no API-key disclosure.
- **Shufti Pro — LEGACY/disabled by active-provider gate:** mutating callback is fail closed unless explicitly selected and correctly signed. Its HTTP calls are bounded. Stored raw provider/webhook fields remain sensitive KYC audit material and are not included in normal user response DTOs; encryption/retention governance is P1.
- Other KYC-like verification branches are code-supported legacy/manual flows, not a second trusted provider webhook.

No live KYC session, poll, or callback was invoked.

## 13. Payment integrations

NOWPayments remains the active crypto payment/payout provider. Fixed prices come from `product_types`; client amount/status/network/beneficiary cannot authorize a deposit. Local pending intent is committed before provider I/O, payment/payout calls have explicit timeouts, and provider results are bound to the local record. Mutating POSTs are not broadly retried.

AnnualAds payment receipts are a separate signed integration but post through the canonical accounting service. Variable-price DSP/shop/ad products remain disabled instead of trusting a client total.

## 14. Blockchain/network safety

Repaired financial paths enforce USD price denomination and USDT-BSC settlement. Wallet validation distinguishes BSC from ERC20/TRC20 labels and validates the address/network independently. Unknown network values fail closed. A client transaction hash or claimed confirmation is not authoritative; provider identity and status must match the durable intent.

No blockchain transaction was sent.

## 15. Secret inventory

Secret values are intentionally omitted.

| File/location | Secret type | Exposure class | Action |
|---|---|---|---|
| `scripts/set_nowpayments_mh5.sh` (before repair and repository history) | NOWPayments API key and IPN secret | **Committed/high** | removed fallback values; rotate both in controlled phase |
| `frontend/.env.production` and AnnualAds embed contract | browser-visible AnnualAds tenant/embed identifier named `API_KEY` | Public integration identifier by current design; naming/scope ambiguity | confirm provider contract and scope; rotate if provider treats it as a secret |
| backend runtime `.env` | DB/JWT/provider/webhook/SMTP/storage secrets | expected operational secret store; not printed | restrict file permissions, inject via deployment secret manager, validate presence |
| examples/docs/tests | placeholder variable names and dummy values | Low | retain placeholders only; automated scanning recommended |

The tracked scan found no private-key block or common live private-key prefix. This is not proof that no historical commit contains other credentials; repository-wide history scanning should be run with a dedicated secret scanner before release.

## 16. Secret rotation requirements

**Rotation required — NOWPayments API key and IPN secret.** Reason: both existed as committed shell-script defaults, so deletion cannot revoke copies or erase Git history. Dependencies: backend payment creation/status, signed IPN verification, provider dashboard webhook configuration, and deployment secret injection.

Safe order for the later controlled phase:

1. create/reissue provider credentials without exposing them in chat, logs, or source;
2. update the deployment secret store/backend environment and dashboard webhook secret together;
3. deploy/restart only in the approved maintenance procedure;
4. verify payment creation and signed webhook behavior using a sandbox/controlled provider test;
5. revoke the old credentials and monitor rejected old signatures.

The AnnualAds browser identifier requires provider-contract confirmation. If it grants privileged API access, add it to the same controlled rotation plan. No secret was rotated in Prompt 9.

## 17. Environment/config findings

Production startup now fails closed when:

- CORS origins are wildcard/non-HTTPS or missing;
- public backend/frontend URLs are not HTTPS;
- JWT issuer/audience/secret semantics are invalid;
- active KYC provider credentials are absent or a secret field contains a URL-shaped value;
- provider HMAC algorithms are outside the allowlist;
- NOWPayments mode is ambiguous or critical IPN configuration is absent where the active production flow requires it.

Production disables API docs/redoc and the CORS debug endpoint. The legacy serverless adapter received the same CORS/docs restrictions. The verified compose file sets `ENVIRONMENT=production`, `DEBUG=false`, and exact Kaluta domains. Database-only inspection cannot prove the secret values inside a running production container, so provider-secret presence was not claimed from the read-only DB audit.

## 18. CORS/CSRF

Production CORS now uses exact configured HTTPS origins, no permissive origin regex, credentials only for those origins, and a minimal exposed-header set. The prior development regex remains non-production only.

The primary API authentication is an Authorization bearer token, not an authentication cookie, so traditional cookie-CSRF does not authorize API mutations. `SameSite` still matters for non-auth UI cookies, but adding a CSRF token to bearer-only calls would not address the larger risk. The P1 browser risk is token theft through XSS because the current access token is stored in `localStorage`.

## 19. XSS

The participation description no longer uses `dangerouslySetInnerHTML`; React renders it as text while preserving whitespace. No active path was found that deliberately executes advertiser/user HTML or JavaScript. Prompt 4 video allowlisting remains in place, and TikTok rendering uses validated known-provider URLs rather than provider HTML.

A strict production CSP is not yet enabled because AnnualAds, video, storage, and analytics origins must be inventoried in a report-only rollout first. This is P1 defense-in-depth, especially while bearer tokens remain in browser storage.

## 20. SSRF

The Next.js link-preview route now:

- permits only HTTP/HTTPS without URL credentials;
- resolves DNS and rejects loopback, RFC1918, link-local, carrier-grade NAT, multicast/reserved, metadata, and private IPv6 destinations;
- validates every redirect with a maximum of three;
- uses manual redirects, an 8-second deadline, and a 1 MiB response bound.

Both duplicate TikTok resolver routes now accept only HTTPS TikTok hosts, validate every redirect, and use bounded manual redirect logic. Automated tests cover localhost/private/metadata rejection and public literal acceptance.

Residual P1: DNS validation and connection are separate operations in the standard fetch stack, leaving a DNS-rebinding/time-of-check gap. Strong completion requires egress firewall/proxy rules or a fetch client that pins the validated address while preserving TLS host verification.

## 21. Open redirects

KYC status redirects always target the configured frontend origin; query values are URL-encoded and length-bounded. TikTok redirect resolution is constrained to the TikTok host policy. Advertising destinations retain Prompt 7 HTTP/HTTPS/internal-host validation. No trusted-domain endpoint was found that blindly redirects to an arbitrary `next`, `return_url`, or callback URL.

## 22. File security

Prompt 4 MIME/signature, extension, path, video-provider, upload ownership, and media fallback protections remain passing. User SVG/executable uploads are not newly enabled. Prompt 8 private digital delivery remains dormant/fail closed, so no predictable paid-download URL was exposed. File-disposition and signed-download expiry must be revisited when marketplace entitlement storage is approved.

## 23. Rate limiting

Application middleware now covers global traffic plus stricter prefixes for login, registration, reset, share links, KYC initiation/webhooks, payments, wallet, votes, comments, media upload, and search. Forwarded client IP is trusted only when the immediate peer is in `TRUSTED_PROXY_IPS`; a public client cannot rotate `X-Forwarded-For` to bypass a bucket. Bucket growth is capped.

The limiter is in-memory and therefore per-worker. Correctness does not depend on Redis, but protection is not globally consistent across multiple workers/instances and is lost on restart. P1 requires reverse-proxy/edge limits or Redis atomic buckets for login, webhook, payment, KYC, upload, and engagement abuse.

Login/reset responses should continue converging toward indistinguishable messages/timing to reduce enumeration; operator logs can retain the internal reason without PII or credentials.

## 24. SQL/command safety

Active backend/frontend scans found no user-controlled `subprocess`, `os.system`, `shell=True`, `eval`, `exec`, Pickle, or unsafe YAML deserialization path. Raw SQL values are parameterized; the performance statement-timeout f-string uses a clamped integer rather than request text. Dynamic order/sort fields inspected use allowlists or ORM expressions.

No active SQL-injection or command/code-execution vulnerability was identified. Future dynamic identifiers must remain allowlisted because SQL parameters cannot safely represent column names.

## 25. Audit logging

Financial journals and commissions already retain durable financial history. Prompt 9 added `AuditTrail` records for the highest-risk registered admin actions: role, active status, soft delete, KYC decision, KYC-with-payment grant, and payment grant. Webhook signature failures, unknown provider events, permission denials, provider identity mismatch, and suspicious payout/replay states are logged without credentials.

Production error responses now replace unhandled 5xx detail with a generic message; docs and diagnostic endpoints no longer disclose production internals publicly. Raw passwords, Authorization headers, provider secrets, and KYC payloads are not intentionally logged.

P1: make security audit events append-only with typed action/target/request/source fields, add retention/access policies for stored raw KYC payloads, and normalize legacy `detail=str(exc)` client errors.

## 26. External HTTP/retry policy

| Call class | Timeout/failure | Retry rule |
|---|---|---|
| provider status GET/poll | bounded connect/read/write/pool timeout | safe for bounded retry with backoff |
| public metadata/oEmbed GET | bounded deadline, size/redirect policy where server-side | bounded retry only if request budget permits |
| create payment | bounded; durable local intent first | retry only with stable provider/order idempotency and reconciliation semantics |
| create payout/refund | bounded; durable intent/reservation first | **do not auto-retry** unless provider guarantees the same idempotency key |
| KYC session creation | bounded; stored reference required | no blind retry after ambiguous success |
| webhook processing | local transaction and idempotent transition | provider may redeliver; handler must not duplicate effects |
| storage/upload/moderation/translation | bounded active paths; failure is non-mutating/fail closed for safety decisions | retry reads/idempotent uploads only |

NOWPayments, Kaluta, Shufti, backend moderation/relevance, link preview, server-auth checks, and translation have explicit bounds. Some optional client/server geography and deeper AssemblyAI/moderation helper calls do not yet share one standardized timeout wrapper; this is P1 if those branches are promoted to production-critical use.

## 27. Integration inventory

Base URLs are named but secrets are not shown.

| Provider | Purpose / active | Auth | Timeout | Webhook/auth | Idempotency/live mode | Owner |
|---|---|---|---|---|---|---|
| NOWPayments | pay-in/payout/refund; active financial | API key plus payout authentication/TOTP | explicit per operation | yes, HMAC-SHA512 | durable local intents; explicit sandbox/live required | backend payments/finance |
| AnnualAds | active sponsored iframe/receipt | signed SSO and tenant identifier | iframe/provider contract; receipt local | yes, timestamped HMAC-SHA256 | transaction lock/check; production tenant | sponsor AnnualAds module |
| Kaluta KYC | active/default KYC | API key | explicit connect/read/write/pool | yes, timestamped HMAC-SHA256 | bound session/terminal replay | KYC service |
| Shufti Pro | legacy/disabled unless selected | client/secret | explicit total/connect/read | yes, raw response signature | state replay guard | legacy KYC service |
| UploadThing | optional/active media route | server token/SDK | SDK plus bounded backend auth check | SDK callback auth | owner metadata | frontend upload route |
| S3-compatible/local media | production media storage/fallback | access key or local filesystem | botocore bounded config / local | no | object key/ownership | backend storage/feed media |
| Sightengine | optional moderation | API user/secret | bounded | no | read/check request | moderation services |
| OpenAI-compatible translation/moderation | optional translation/content | bearer API key | bounded | no | non-financial | Next API/backend moderation |
| AssemblyAI | optional audio moderation | bearer API key | partial helper bounds; P1 standardization | callback/poll depending branch | non-financial | frontend moderation service |
| Resend/SMTP | email | provider/SMTP credential | provider library | provider callbacks not registered as financial mutation | notifications only | email service |
| TikTok/YouTube oEmbed | public media metadata/embed | none | bounded on hardened resolver/preview | no | read only | Next media routes |
| IP/geography providers | enrichment | optional API identity | mixed optional-client bounds | no | read only | geography/location helpers |
| Redis | cache/rate/background support | internal URL/password if configured | connection/pool bounds from Prompt 5 | no | optional correctness fallback | backend cache |

## 28. Legacy integrations

- Shufti is legacy while Kaluta is active; its mutation route remains registered only to support an explicit future provider switch, but returns 404 under the current provider and still requires a signature if enabled.
- Internal native advertising, Premium Clubs, and marketplace financial integrations remain dormant/fail closed.
- DSP/ad-credit/shop variable-price product hooks are incomplete and cannot enter fixed-price checkout.
- Accounting REST/revenue modules exist but are not registered; financial GraphQL reads are registered and are now admin-only.
- Plural `wallets`, singular `wallet`, and empty transaction tables are not treated as an active payment system.
- Two TikTok route generations remain for compatibility; both now share the same host policy.

Unsafe unused provider code was not deleted blindly.

## 29. Production read-only findings

The new `backend/scripts/analyze_accounting_security_production_readonly.py` explicitly begins a PostgreSQL READ ONLY transaction, sets an 8-second statement timeout and 1-second lock timeout, avoids credentials/PII output, and rolls back.

Results:

- 239 users: 194 role `user`, 43 unassigned role, one role `is_admin`, and one role `super_admin`; all these groups are active;
- four users have `is_admin=true`, demonstrating that role text and the boolean flag are not one normalized classification;
- 38 journals are structurally balanced with no detected line/account anomalies;
- 14 approved commissions total USD 38.00; payable ledger is USD 36.00;
- missing postings are exactly deposits 51 and 53, USD 1.00 each;
- no duplicate non-null deposit external payment ID, order ID, or cashout payout reference was found;
- plural-wallet facts are documented in section 3;
- database connections at the observation point: one active audit connection, four idle, and one idle-in-transaction. The idle transaction requires operational source tracing/monitoring but was not terminated.

The database audit cannot verify live container environment values. Production configuration conclusions are based on the repository deployment configuration, not guessed from local development warnings.

## 30. Consolidated schema requirements

Nothing below was applied.

### P0 — required for correctness

1. Reconcile the Alembic graph and production drift before any migration.
2. Add a canonical contest-period roster/participation relationship and uniqueness across contestant, contest, season, round/stage; add official-period uniqueness after data reconciliation.
3. Enforce future voting bucket/five-slot/position uniqueness and typed stage/season context without rewriting ambiguous historical votes.
4. Enforce normalized category name/slug uniqueness and required canonical category relationships only after the seven active categoryless contests and malformed slug are reconciled.
5. Add provider event storage unique on `(provider, event_id)` with payload hash, received/applied state, tenant, timestamp, and journal/refund link.
6. Add unique non-null provider payment IDs and typed financial source/idempotency/currency/asset/network references on journals.
7. Add payout idempotency key, unique provider payout reference, constrained payout state, and a payout-to-commission reservation relation.
8. Add first-class refund/reversal records unique by provider event/original source with amount, currency, state, allocation, and reversal journal.
9. Decide one canonical wallet only after the five plural rows are provenance-reviewed; then enforce `(owner, currency, asset, network)` uniqueness.
10. Add explicit commission reversal/debt linkage and constrained source-recipient-level identity.
11. Add authoritative payer/order/order-item/beneficiary sources before variable-price products can activate.
12. Before native ads activate: campaign funding/order source, unique delivery/billable-event identity, atomic budget constraints, and moderation/audit state.
13. Before clubs activate: plan/order/payment membership source uniqueness, entitlement state, hold/release references, and payout idempotency.
14. Before marketplace activates: checkout/order-line identity, unique buyer/order/product entitlement, seller-earning source, hold/release, refund, payout, and private media-object authorization.
15. Make privileged security/audit events append-only with stable actor/action/target/source/request identity.

### P1 — strongly recommended indexes/constraints

- performance composites already documented for page views, votes/stages, contest-season/category, and engagement time filters;
- indexes for provider IDs/events, commission owner/status/reservation/source, deposit status/product/user, journal typed source, and refund/payout status;
- ad-serving placement/category/status/schedule and delivery-event indexes before activation;
- club/marketplace state, owner, order, entitlement, earnings, and browsing indexes before activation;
- audit indexes on actor/time and target/time; webhook event received/applied time;
- constrained sponsor non-self relation, commission level/rate/non-negative money, currency/network allowlists, and explicit state-transition metadata.

P2 hardening includes eventual partitioning for high-volume event tables, optimistic wallet versions only if mutable wallets are approved, and separate custody accounts per crypto network.

## 31. Files changed

Prompt 9 changed or added:

- Configuration/security: `backend/main.py`, `backend/api/index.py`, `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/app/core/rate_limit.py`, `backend/app/api/deps.py`.
- Auth/authorization/API: `backend/app/api/api_v1/endpoints/auth.py`, `payments.py`, `kyc.py`, `admin.py`, `backend/app/graphql/schema.py`.
- Schemas/CRUD: `backend/app/schemas/user.py`, `backend/app/crud/crud_user.py`.
- Integrations/services: `backend/app/services/shufti_pro.py`, `kaluta_kyc.py`, `kyc_provider_dispatch.py`, `content_moderation.py`.
- Safe configuration script: `scripts/set_nowpayments_mh5.sh`.
- Read-only audit/tests: `backend/scripts/analyze_accounting_security_production_readonly.py`, `backend/tests/test_prompt9_security.py`, `backend/tests/unit/test_security.py`, plus updated KYC/e2e expectations.
- Frontend security: `frontend/lib/server-auth.ts`, `frontend/lib/tiktok-url-policy.ts`, both TikTok resolver routes, link-preview route/test, content moderation/ownership/translation API routes, moderation service, participation form, and wallet transaction table.
- Report: `ACCOUNTING_SECURITY_INTEGRATIONS_REPAIR_REPORT.md`.

The worktree also contains preserved and unapproved changes from Prompts 2-8. They were not reverted or attributed to Prompt 9.

## 32. Tests

Final verification after the last authorization change:

- Backend: **294 passed, 0 failed, 2 skipped** in 23.30s.
- Skips: two opt-in live PostgreSQL accounting/concurrency write tests; they were not enabled against production.
- Prompt 9 focused backend: 12 passed, including privileged registration rejection, bearer-only validation, admin-only financial GraphQL/KYC diagnostics, inactive/signed Shufti behavior, token purpose/binding, and trusted-proxy handling.
- Frontend: **75 passed, 0 failed** across 17 files.
- Frontend production build: **PASS**, 88/88 static-generation tasks completed.
- Build caveat: project configuration still skips TypeScript and ESLint build failures; dedicated tests pass, but CI should run typecheck/lint separately.
- Prompt 2 voting/ranking regressions: PASS.
- Prompt 3 contest-context/lifecycle regressions: PASS.
- Prompt 4 category/media regressions: PASS.
- Prompt 5 performance guards: PASS.
- Prompt 6 financial regressions: PASS.
- Prompt 7 advertising integrity regressions: PASS.
- Prompt 8 club/marketplace fail-closed integrity regressions: PASS.

No production brute force, forged callback, provider call, or write test was performed.

## 33. Remaining P0/P1 security risks

**P0/blocking:**

- the committed NOWPayments API/IPN credentials must be rotated; removing them from the working tree does not revoke them or purge history;
- provider-event, payout, refund, typed journal source, and dormant-feature integrity constraints await safe Alembic reconciliation;
- USD 2.00 of historical commissions (deposits 51 and 53) lack payable accounting and require reviewed compensating entries, not edits;
- plural-wallet USD 2,441.00 provenance remains unproved;
- Prompts 2-8 and all Prompt 9 changes remain unapproved and undeployed.

**P1:**

- seven-day browser bearer token in `localStorage` with no refresh rotation/revocation;
- no staged CSP yet; AnnualAds/video/storage domains must be tested in report-only mode;
- rate limiting is per worker, not distributed/edge-enforced;
- SSRF DNS-rebinding defense needs egress controls/address pinning;
- inconsistent legacy role/`is_admin`/RBAC semantics and four production admin booleans versus two admin-like role strings need governance review;
- stored raw KYC provider payloads need encryption, retention, and access policy;
- one idle-in-transaction production session requires source tracing;
- remaining optional provider helpers should adopt the standardized timeout wrapper before becoming critical;
- legacy client-facing `str(exc)` errors and audit-log schema should be normalized;
- build-time type/lint bypass must be addressed in CI.

## 34. Deployment recommendation

**NO.** Prompt 9 is PARTIAL and must not be deployed with Prompts 2-8 yet. First perform controlled secret rotation planning, reconcile Alembic/schema drift, approve the P0 constraint design, review the two compensating commission postings and wallet provenance without mutating history, run isolated PostgreSQL concurrency/provider-contract tests, add edge/distributed abuse controls, and complete a candidate-environment security/regression review.

Alembic was not touched. Production data/schema were not modified. Production services were not restarted. No real external side effect occurred.
