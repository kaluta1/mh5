# Final Regression and Production Readiness Report

Audit date: 2026-09-10  
Project: MyHigh5 / Kaluta Foundation  
Prompt: 10  
Decision: **C — READY FOR STAGING ONLY**

This audit was non-destructive. Production data and schema were queried only through bounded `SELECT`/catalog reads in explicit read-only transactions with statement timeouts. No deployment, migration, stamp, index build, data correction, credential rotation, provider mutation, or service restart occurred.

## 1. Executive summary

The combined Prompt 2–9 code is internally coherent and its available automated regression evidence is strong: the backend finished with **302 passed, 0 failed, 2 skipped**; frontend tests finished with **75 passed, 0 failed**; separate TypeScript and ESLint checks passed; and the Next.js production build generated **88/88 pages**. Prompt 10 also repaired final cross-cutting conflicts: protected diagnostic and maintenance endpoints, removed request-time DDL, removed a duplicate in-process monthly scheduler, fixed a stale frontend user endpoint and logout call, standardized active public-domain fallbacks, and added production route/release gates.

This is not sufficient for production deployment. The application is **READY FOR STAGING ONLY** because the production Alembic marker `f3merge01` is missing from all reachable repository history while the repository has three divergent heads; active financial workflows still need database-enforced provider/payout/refund idempotency; two approved commissions remain under-posted by exactly USD 1.00 each; production category/period anomalies block some constraints; the five-row USD 2,441 plural-wallet subsystem remains of unknown provenance; NOWPayments credentials must be rotated; the restored-production migration dry run and PostgreSQL concurrency tests have not occurred; and live container/config/backup/SSL termination evidence could not be revalidated from this workstation.

There are **15 consolidated P0 schema requirement groups**. Eleven relate to currently exposed production domains; four are activation gates for variable-price commerce, native ads, clubs, and marketplace. Six important current-data precheck sets pass. Three groups are blocked by existing production data. A safe *strategy* for recovering Alembic is defined, but it remains **PARTIAL** until tested on a fresh production snapshot and until deployment backups/images are searched for the original `f3merge01` source.

## 2. Combined architecture

| Domain | Classification | Authoritative implementation |
|---|---|---|
| Voting/ranking | CANONICAL | `VotingRankingService`; current/future ballots are context and category scoped |
| Contest context | CANONICAL | `ContestContextService`; ambiguity fails closed |
| Categories | CANONICAL | `categories.id` → `contest.category_id` |
| Media | CANONICAL + COMPATIBILITY | Prompt 4 resolver, ownership/upload validation, safe video embeds; legacy-host resolution remains compatibility-only |
| Accounting | CANONICAL FOR COVERED EVENTS | `journal_entries` + `journal_lines`; subledgers remain necessary for commission/payment state |
| Affiliate | CANONICAL | `users.sponsor_id` hierarchy (maximum 10 levels) + `affiliate_commissions` |
| Payment | CANONICAL | durable server-priced `Deposit`/payment-intent creation and Prompt 6 finalization services |
| Refund/reversal | CANONICAL SERVICE, SCHEMA-INCOMPLETE | compensating `FinancialReversalService`; no first-class production refund table |
| Payout | CANONICAL SERVICE, SCHEMA-INCOMPLETE | durable cashout intent/reservation then provider call, with application idempotency |
| Active advertising | ACTIVE EXTERNAL | AnnualAds and AdSense |
| Internal native advertising | DORMANT | models/integrity helpers retained; finance/mutations not registered |
| Premium Clubs | DORMANT | marketing/demo read only; no financial activation |
| Marketplace | DORMANT | models retained; no checkout/entitlement/seller payout activation |
| KYC | ACTIVE/PARTIAL | provider dispatcher; Kaluta selected by production configuration; signed legacy Shufti callback is provider-gated |
| Cache | OPTIONAL ACCELERATOR | Redis-backed cache/rate-limit/single-flight with correct fallback |

No second active ranking, payment, ledger, commission, refund, or payout engine was found. Legacy and dormant models remain for forensic/compatibility purposes and must not be activated through router imports or flags.

## 3. Change inventory

The final worktree inventory contains **218 modified/untracked/deleted paths** across Prompts 2–10. Each preceding report contains its prompt-specific exact file list; the grouping below is the master architectural inventory and identifies all overlapping areas.

| Group | Changed implementation areas |
|---|---|
| Voting/ranking | `backend/app/api/api_v1/endpoints/{votes,voting,analytics}.py`, `backend/app/services/{voting_ranking,contest_context}.py`, voting/ranking models, schemas, frontend contest/TopHigh5 views, voting tests/scripts |
| Contest | contest/contestant/round/season APIs, CRUD, models, scheduler/monthly services, contest frontend pages and cards, lifecycle report/analyzers/tests |
| Category | category endpoint/model/schema, contest category integrity service, admin category UI, category production auditor/tests |
| Media | media API, storage/S3/moderation/relevance services, frontend upload/media/video/TikTok/link-preview utilities and tests |
| Performance | DB session/cache/search/contest query paths, engagement aggregation, performance auditor/tests, deploy configuration |
| Financial | affiliate/payment/wallet/admin/webhook endpoints; accounting, commission, payout, reversal, balance, hierarchy services; schemas/models; reconciliation scripts/tests |
| Advertising | advertising model/schema/integrity, AnnualAds endpoint/component/tests, native-ad production auditor/report |
| Clubs/marketplace | club and DSP models/schemas/integrity guard, read-only/demo frontend, production auditor/report |
| Security/integrations | auth/dependencies/security/rate limits/config/public URL/KYC/provider clients; Prompt 9 tests and report; secret setup script cleanup |
| Config/runtime | `backend/main.py`, backend/frontend Docker assets, `deploy/hostinger/*`, Next config, frontend config, TypeScript config |
| Frontend | active page/API/service/component changes described above plus metadata/domain fixes and tests |
| Reports | the nine prior reports and this final report |

Overlapping files were reviewed directly. Material conflict repairs in Prompt 10 were:

- `api.py`: production never registers the temporary debug route; DB schema diagnostics are admin-only.
- `admin.py`: GET accounting health cannot auto-seed accounts; production accounting backfills and account bootstrap are maintenance-gated.
- `rounds.py` and `scheduler.py`: manual lifecycle mutation requires admin/cron-secret authorization.
- `feed_messages.py` and `feed_keys.py`: request-time `CREATE TABLE`/`ALTER TABLE` was removed; incompatible schema returns 503.
- `scheduler_manager.py`: `monthly-round` is now an alias of the sole `monthly-ops` runner, not a second background loop.
- Frontend affiliate agreement now uses `/api/v1/users/me`; logout clears local bearer state rather than calling an unregistered backend logout endpoint.
- Active runtime/SEO fallbacks use `kalutafoundation.com`; MyHigh5 brand email and legacy media-host compatibility were intentionally retained.

Prompt 10 directly changed/added the following release-audit files (generated `tsconfig.tsbuildinfo` excluded):

- Backend: `backend/app/api/api_v1/api.py`, `endpoints/{admin,feed_keys,feed_messages,rounds,scheduler}.py`, `backend/app/services/scheduler_manager.py`, `backend/scripts/{audit_production_readiness_readonly,audit_registered_routes}.py`, `backend/tests/test_prompt10_release_gates.py`, and the adjusted health/e2e/login regression tests.
- Frontend contract/domain/type fixes: `frontend/lib/{api,config,performance,referral-share,safe-remote-url}.ts`, `frontend/services/{contest-service,kyc-service,social-service}.ts`, `frontend/next.config.js`, `frontend/tsconfig.json`, `frontend/styles/quill-snow.css.d.ts`, the link-preview route/test, metadata/layout/robots/sitemap/maintenance/public redirect routes, contest layouts/list, affiliate/founding pages, About variants, footer, KYC/location/participation components.
- Report: `FINAL_REGRESSION_PRODUCTION_READINESS_REPORT.md`.

## 4. Cross-prompt conflicts

| Conflict | Result |
|---|---|
| Multiple ranking calculations | Consolidated behind `VotingRankingService`; compatibility callers delegate |
| Context-free historical ranking | Fails closed; no historical inference was added |
| Category text vs ID | Canonical ID retained; legacy strings are display/compatibility only |
| Multiple media URL rules | Canonical resolver retained; compatibility transformations bounded |
| Wallet fields vs ledger/subledger | Journal is authoritative only for covered entries; plural `wallets` is not promoted |
| Direct financial mutations | Active paths routed through Prompt 6 services; dormant paths unavailable |
| Active external ads vs native ads | AnnualAds/AdSense active; native platform dormant |
| Clubs/marketplace models vs product claims | Both explicitly dormant/fail-closed; some marketing copy remains P1 governance work |
| Celery disabled vs scheduler work | Four in-process loops remain; duplicate monthly loop removed |
| Request handlers creating schema | Removed from feed key/message routes |

## 5. Registered route audit

Production-shaped application import enumerated **381 FastAPI routes** with **0 duplicate method/path pairs**. The debug route is absent in production.

The 15 unauthenticated non-GET routes were reviewed. They are public auth/contact/newsletter/referral inputs, authenticated-by-signature/provider callbacks (Kaluta, Shufti, NOWPayments, AnnualAds), or the secret-protected scheduler hook. The Shufti route cannot mutate unless Shufti is the selected provider and its signature is valid. The scheduler secret uses constant-time comparison.

No state-changing GET was found. The GETs flagged by a conservative name heuristic were status/statistics/preview/currency reads. The legacy admin NOWPayments TOTP route is authenticated/admin-only and deliberately returns 410.

Dormant native-ad finance, club payment/payout, marketplace checkout/seller payout, plural-wallet mutation, and unregistered accounting modules have no registered mutation route. Production accounting bootstrap/backfill mutation returns 409; dry-run reads remain available to admins.

## 6. Frontend/API contract audit

The frontend has **88 Next.js page routes** and 20 `route.ts` handlers, nine of which are frontend API handlers. Active calls were mapped by search and tests to registered backend routes with matching auth expectations.

Repaired breakages:

- `/api/v1/user/me` → registered `/api/v1/users/me`.
- Removed a call to nonexistent `/api/v1/auth/logout`; bearer logout is local token/cache deletion.
- Response typings were aligned for contest context, KYC status, FMP detail, affiliates, and location/language selectors.
- SSRF validation was extracted to `frontend/lib/safe-remote-url.ts` because Next route modules may not export arbitrary helpers.

One unused social-service compatibility block still refers to `/private-messages`; the active backend is `/messages`, but there is no frontend caller. It is classified REMOVE LATER, not an active breakage. Club UI uses demo/read-only data. No marketplace checkout or native-ad finance client is active.

## 7. Production schema vs ORM

The catalog audit compared **167 production public tables** with **127 imported ORM tables**. Every ORM table exists in production. No ORM-required missing column, missing FK, or missing unique constraint was detected by the catalog comparison.

Forty database-only tables were found: `accounting_periods`, `ad_credit_accounts`, `ad_domain_blocklist`, `ad_slot_bookings`, `affiliations`, `alembic_version`, `app_votes`, `cache`, `cache_locks`, `comments`, `contest_entries`, `contest_templates`, `email_outbox`, `failed_jobs`, `follows`, `fx_rates`, `invoice_sequences`, `invoices`, `job_batches`, `jobs`, `likes`, `link_scan_results`, `locations`, `migration_job_runs`, `migrations`, `password_reset_tokens`, `payout_batch_items`, `payout_batches`, `personal_access_tokens`, `prize_winners`, `prizes`, `referral_codes`, `reports`, `revoked_tokens`, `sessions`, `suggested_contests`, `top_high5_leaderboard`, `user_transactions`, `vote_rankings`, and `wallets`.

There are 28 tables with substantive drift. Important classes:

- Native advertising tables contain legacy fields and mixed enum labels; dormant code must not be activated against them.
- `contest`, `contest_seasons`, `contestants`, posts, groups, and users contain database-only soft-delete columns.
- `deposits` contains 13 legacy/tax/club/DSP fields and a database `refunded` enum label absent from active ORM. Production has 35 expired, 27 pending, and 7 validated deposits—zero refunded rows.
- `journal_entries`/`journal_lines` contain production typed source, idempotency, currency, reversal, and reference fields not fully mapped by current ORM.
- KYC enums contain historical mixed labels. The only row is `SHUFTI_PRO/PENDING`; it is provider-gated legacy data.
- Round timestamps/nullability, financial-report enums, contest numeric types, and several legacy ad enum/type definitions differ.

The code can import and test against its isolated schema, but the production drift is not migration-safe evidence. Full fingerprinting must additionally compare defaults, checks, triggers, functions, extensions, sequences, grants, and enum ordering on a snapshot.

## 8. Alembic forensic analysis

- Production marker: `f3merge01`.
- Repository heads: `c9d0e1f2a3b4`, `s3t4u5v6w7x8`, `u4v5w6x7y8z9`.
- `f3merge01` does not exist in the current filesystem or any reachable Git history inspected.
- `c9d0e1f2a3b4 ← b4c5d6e7f8a9 ← p8q9r0s1t2u3`.
- `s3t4u5v6w7x8` and `u4v5w6x7y8z9` both descend from `r2s3t4u5v6w7`, then `q1r2s3t4u5v6`, then `p8q9r0s1t2u3`.
- All three heads share `p8q9r0s1t2u3`; the two latter heads share the immediate ancestor `r2s3t4u5v6w7`.
- The repository contains 80 revision modules plus `__init__.py`, multiple historical roots/mergepoints, hand-written idempotent migrations, and an empty `20260330_accounting_rollout` placeholder.
- The `u4...` commission unique effect and `s3...` KYC enum effect are already visible in production despite the unrelated marker. Equivalence of `c9...` is not proven, and that revision includes data-changing contest behavior.

Conclusion: a merge revision would join repository heads but would not connect or prove production history. Blind stamping would discard evidence. Blind upgrade could re-run destructive or already-applied changes.

## 9. Alembic recovery recommendation

Status: **PARTIAL — a safe strategy is identified, not yet proven.**

Recommended strategy: **reconstruct `f3merge01` if possible; otherwise establish a verified production-equivalent baseline with that exact marker, then build a new single additive lineage.**

Preconditions:

1. Search deployed image layers, release archives, CI artifacts, server backups, and prior developer clones for the original `f3merge01` module and its parents.
2. Create a fresh Neon branch/snapshot and immutable production schema dump/fingerprint.
3. Securely back up DB, deployed code/image digests, environment, and proxy configuration.
4. Freeze schema-changing work and obtain DBA/application-owner review.

If the original revision cannot be recovered:

1. Author a reviewed baseline revision whose ID is `f3merge01`, `down_revision=None`, and whose upgrade can construct the verified production-equivalent schema **only on an empty database**.
2. Move the existing divergent legacy graph out of the active versions path but retain it in source control for forensics; do not pretend it ran.
3. Because production already carries `f3merge01`, do **not** stamp it and do **not** execute baseline DDL there.
4. Create new, additive reconciliation revisions descending solely from `f3merge01`; each begins with data/schema assertions and uses concurrent/online techniques where supported.
5. Validate both paths: empty-database bootstrap and production-snapshot upgrade.

Failure conditions: any fingerprint mismatch, failed data precheck, unexpected destructive DDL, enum rewrite, lock beyond the approved window, count/financial change, or inability to downgrade/restore. Rollback is snapshot/branch restore plus prior application image/config—not blind Alembic downgrade.

## 10. P0 schema requirements

There are **15 P0 groups**. Groups 1–10 and 15 apply before deploying currently exposed domains. Groups 11–14 apply only before activating dormant/new commerce features.

| # | Name / table / type | Why | Precheck / current conflict | Safety and dependency |
|---:|---|---|---|---|
| 1 | Migration lineage baseline; Alembic metadata | Required to make every later change reproducible | `f3merge01` missing; three heads | Blocked pending snapshot/reconstruction; rollback by snapshot |
| 2 | Official contest period/roster uniqueness; rounds/season/link tables; UNIQUE/FK/state | Prevent ambiguous official period/context | 3 duplicate non-cancelled months; historical roster ambiguity | Blocked by data/business review; never rewrite historical votes |
| 3 | Future ballot identity/five-slot constraints; `contestant_voting`/`votes`; UNIQUE/CHECK/FK | Enforce deterministic voting under concurrency | Current duplicate bucket 0, missing bucket 0, invalid position 0, missing stage 0 | Safe for conforming current rows after snapshot; exact five-slot rule needs reviewed DDL |
| 4 | Normalized category identity and required contest link; UNIQUE/CHECK/FK | Prevent category drift | normalized duplicate groups 0; 7 active contests lack category; 1 malformed slug | Unique part safe; required link/slug blocked by reconciliation |
| 5 | Provider webhook event identity; new/selected event table; UNIQUE/FK | Replay safety across processes | no canonical provider-event table | Additive; must be deployed before relying on webhook mutation |
| 6 | Deposit provider/reference and typed journal source/idempotency/currency/network; UNIQUE/CHECK/new mapping | Durable payment/accounting identity | deposit external/order duplicates 0; production journal columns exist but ORM drift | Data permits uniqueness; ORM/schema alignment and provider scoping required |
| 7 | Cashout/payout idempotency, provider ref, state/reservation; `affiliate_cashout_requests`; UNIQUE/CHECK/new columns | Prevent double external payout/overspend | payout-ref duplicates 0; no idempotency column | Additive state backfill required; no real payout during migration |
| 8 | First-class refund/reversal identity; refund table/link; UNIQUE/FK/state | Replay-safe compensating reversals | no refund table | Additive; reconciliation against journals/deposits required |
| 9 | Canonical wallet ownership/currency/asset/network/version; wallet decision; UNIQUE/FK/CHECK | Prevent mixed/duplicate balance authority | 5 unknown plural wallets, USD 2,441 | Blocked until provenance decision; keep read-only |
| 10 | Commission source-recipient-level/reversal/debt; `affiliate_commissions`; UNIQUE/FK/state/new references | Durable creation and reversal | duplicate deposit/user 0; invalid 0; orphan deposit 0; partial unique already exists | Extend after deposits 51/53 remediation plan and state review |
| 11 | Authoritative payer/order/item/beneficiary pricing linkage | Required before variable-price commerce | active product pricing exists only for current deposit products | **Activation-only**; do not add speculative dormant schema |
| 12 | Native-ad campaign/event/budget/payment identities | Required before native-ad activation | legacy ad schema materially drifts | **Activation-only**, currently dormant |
| 13 | Club membership/payment/hold/payout identities | Required before club activation | no operational canonical model | **Activation-only**, currently dormant |
| 14 | Marketplace order/entitlement/earning/refund/payout identities | Required before marketplace activation | no operational canonical model | **Activation-only**, currently dormant |
| 15 | Append-only audit event integrity; audit table; FK/immutable reference/index | Financial/admin changes require durable actor/target history | audit coverage is incomplete | Additive and required for sensitive production maintenance |

Each online unique constraint should be built through a unique index after a same-transaction or immediately preceding duplicate precheck, then attached where appropriate. Do not create blocked constraints by silently deleting or rewriting rows.

## 11. P1/P2 indexes

There are **23 recommendations**. No index was applied. Current-plan statements derive from the production catalog and Prompt 5 bounded explain/query analysis; a fresh snapshot must produce final `EXPLAIN (ANALYZE, BUFFERS)` evidence.

| Priority | Table / columns | Query and expected benefit | Write/lock risk |
|---|---|---|---|
| P1 | `page_views(contestant_id, viewed_at)` | grouped contestant/date view counts; avoid 504-scale scan of 504,629 rows | moderate insert cost; build concurrently |
| P1 | `votes(stage_id, contestant_id, voter_id) WHERE is_active` | current stage/category ranking aggregation | moderate vote-write cost; partial concurrent build |
| P1 | `contest_stages(season_id, start_date, end_date)` | active context resolution | low write cost |
| P1 | `contest_likes(contestant_id, created_at)` | batched engagement counts | moderate insert cost |
| P1 | `contestant_reactions(contestant_id, created_at, reaction_type)` | reaction grouping | moderate insert cost |
| P1 | `contestant_shares(contestant_id, created_at)` | share grouping | moderate insert cost |
| P1 | `contest_comments(contestant_id, created_at)` partial on visible rows | comment count/timeline | moderate write cost; confirm deletion predicate |
| P1 | legacy `comments(contestant_id, created_at)` partial | compatibility comment aggregation | only if active route confirmed |
| P1 | `contestant_voting(contestant_id, created_at)` | personal/current ranking lookup | moderate vote-write cost |
| P1 | contest-season link `(contest_id, season_id, is_active)` | context joins | low/moderate |
| P1 | `contest(category_id, is_active)` | category-filtered contest lists | low write cost |
| P1 | `deposits(status, user_id, product_type_id)` | payment scheduler/admin reconciliation | low/moderate |
| P1 | `affiliate_commissions(user_id, status, transaction_date)` | payable/available history | low/moderate |
| P1 | `affiliate_cashout_requests(user_id, status, created_at)` | wallet/withdrawal listing | low |
| P1 | `audit_trail(user_id, timestamp)` | actor audit search | moderate |
| P1 | `audit_trail(table_name, record_id, timestamp)` | target audit search | moderate |
| P1 | future `provider_events(provider, status, received_at)` | replay and failure operations | required when table introduced |
| P1 | future `refunds(status, created_at)` | reconciliation/operations | required when table introduced |
| P1 | `affiliate_cashout_requests(status, payout_reference)` | payout status/reconciliation | low; superseded by scoped unique where applicable |
| P2 | trigram index on normalized contest description/search text | bounded search containing term | large index/write cost; measure first |
| P2 | `ad_campaigns(status, start_date, end_date)` | native eligibility | activation-only |
| P2 | future club owner/state/date index | membership/admin lists | activation-only |
| P2 | future marketplace seller/order state/date index | browse/order operations | activation-only |

## 12. Production constraint prechecks

Satisfied current-data sets:

1. Future/current ballot and ranking duplicates/missing context: all checked counts 0.
2. Normalized category name/slug duplicates: 0 groups.
3. Commission duplicate deposit/user, invalid level/amount, and orphan deposit: all 0.
4. Deposit duplicate external payment and order IDs: 0 groups.
5. Cashout duplicate non-empty payout references: 0 groups.
6. Journal structural/balance/source checks: 38 journals; 0 missing-line, one-sided, unbalanced, or header mismatch.

Blocked by production data:

- Period/roster constraints: duplicate non-cancelled rounds for May (IDs 5/6), July (12/13), and August (14/15), plus inherently ambiguous historical attribution.
- Category required-link/slug constraints: 7 active contests without category and 1 malformed slug.
- Canonical wallet constraint/migration: 5 plural-wallet rows remain unknown.

Absent schema cannot be called “satisfied”: payout idempotency column, provider-event table, and refund table are absent. Their existing-data duplicate counts are therefore not meaningful.

## 13. Financial reconciliation

Read-only rerun results:

- Journal entries: 38.
- Every journal has at least two lines and balances; header totals also match lines.
- Approved affiliate commissions: 14 totaling USD 38.00.
- Commission payable (`2001`/`2002`): USD 36.00.
- Exact gap: USD -2.00 payable relative to subledger.
- No duplicate commission source/recipient pair, invalid level/amount, orphan deposit, duplicate deposit external ID/order ID, or duplicate non-empty payout reference was found.
- Refund and canonical provider-event tables do not exist.

The ledger is authoritative for events it covers, but coverage is incomplete. It must not be used to imply that absent refunds, external payout states, dormant commerce, or plural-wallet balances are reconciled.

## 14. Deposit 51/53 correction plan

Both gaps have the same proven shape:

| Deposit | Source record | Expected | Actual | Difference |
|---:|---|---|---|---:|
| 51 | one APPROVED level-1 commission | Dr `5001` referral commission expense USD 1.00; Cr `2001` direct commission payable USD 1.00 | no matching payable posting | USD -1.00 |
| 53 | one APPROVED level-1 commission | Dr `5001` referral commission expense USD 1.00; Cr `2001` direct commission payable USD 1.00 | no matching payable posting | USD -1.00 |

Future correction procedure, not executed:

1. Preconditions/proof: snapshot; re-run exact per-deposit commission and journal queries; confirm both commissions remain APPROVED, unpaid/unreversed, and still have no source journal.
2. Authorization: finance owner prepares; independent accounting/admin reviewer approves the two compensating entries and audit notes.
3. Post one balanced journal per deposit—never edit/delete the commission or old journals—with idempotency keys such as `commission_reconciliation:deposit:51:v1` and `...:53:v1`.
4. The entry is Dr `5001` USD 1.00 and Cr `2001` USD 1.00, currency USD, linked to the deposit/commission source and an immutable remediation audit reference.
5. Post-check: 40 balanced journals, payable USD 38.00, approved subledger USD 38.00, difference zero; repeat execution must create nothing.
6. Rollback/error handling: compensating reversal journal under separate approved key, never destructive editing.

## 15. Legacy wallet classification

Final classification: **UNKNOWN** (high suspicion of a legacy/import artifact, but not proven).

Evidence: five USD rows for existing user IDs 235–239, created seconds apart on 2026-06-10, totaling USD 2,441.00 (USD 428, 153, 339, 824, 697), frozen total zero; no FK, current ORM, writer, API, or active frontend reader was found. Absence of a writer is not proof of origin.

Recommendation: **KEEP READ-ONLY** and explicitly exclude from canonical available-balance calculations. Search import/release/operator records. Archive or migrate only after owner-by-owner provenance and legal/accounting approval. No amount was changed.

## 16. Historical voting status

Read-only before/after vote count: **86,345 / 86,345**. Missing stage and orphan-voter/contestant checks are zero. No historical row was modified.

Current/future voting is expected to use deterministic `VotingRankingService` + `ContestContextService`, category/stage/season isolation, and current ballot uniqueness guards. Historical contest attribution remains 100% ambiguous: 86,345 AMBIGUOUS, 0 exact/strong/orphan classifications under the approved evidence model. Historical TopHigh5 is therefore **not certified and must remain unavailable/fail-closed**. Duplicate historical months and non-period-keyed engagement further prevent retrospective certification.

## 17. Security regression

Backend tests cover registration mass assignment/role escalation, JWT issuer/audience/expiry, password-reset replay, admin authorization, wallet/payment/withdrawal/media/campaign IDOR, club/marketplace fail-closed behavior, signed webhooks/replay, KYC binding/provider gates, amount/network validation, SSRF, redirect and upload policies, raw-sort validation, rate limits, redaction, provider timeouts, accounting balance/source duplication, and reversals.

Prompt 10 route gates additionally verify production diagnostics, maintenance mutations, scheduler aliases, and absence of request-time DDL. No active raw SQL interpolation, user-controlled shell execution, unsafe deserialization, or repository private key was found.

Critical regression result: **PASS in automated isolated tests**. Remaining deployment risks are operational/schema/config risks, not a known test regression. Seven-day localStorage bearer tokens with no refresh/revocation are P1 post-deploy hardening—not a standalone blocker for the current bearer-only design—but CSP and XSS discipline are important compensating controls.

## 18. Secret rotation plan

Rotation is required for the NOWPayments API key and IPN secret because historical committed content remains recoverable from Git history. Values are intentionally omitted.

API key sequence:

1. Create a replacement provider key without immediately revoking the current key.
2. Store the replacement in the controlled production secret store/environment; dependencies are backend payment create/status/payout and the payment scheduler—not the browser.
3. Deploy/restart only in the approved coordinated release.
4. Validate with a non-mutating authenticated provider request and mocked/sandbox payment flow.
5. Revert environment/image if validation fails while the old key remains valid.
6. Revoke the old key only after payment status checks and monitoring succeed.

IPN secret sequence:

1. Schedule a brief payment-webhook maintenance window because current code accepts one secret.
2. Generate/set the replacement provider IPN secret and server secret as one coordinated change; preserve secure configuration rollback reference where the provider permits it.
3. Restart the backend in the release sequence; send only a provider-supported sandbox/test notification.
4. Verify raw-body HMAC rejection/acceptance and replay behavior in logs without exposing payload secrets.
5. Revoke/retire the old secret immediately after confirmation. If provider reset invalidates it at creation, rollback is a new coordinated secret—not restoration of a dead secret.

AnnualAds browser identifier scope still requires provider confirmation; rotate only if AnnualAds confirms it is a secret rather than a public client identifier.

## 19. External integration status

| Integration | Status | Contract/security result |
|---|---|---|
| NOWPayments | BLOCKED FOR RELEASE | explicit timeouts, server pricing, signed/replay-safe IPN, network validation; credential rotation, live-mode config, schema idempotency and sandbox validation remain |
| AnnualAds | READY WITH CONFIG | active SSO/payment receipt integration, signed callback and bounded client; browser identifier scope must be confirmed |
| AdSense | READY WITH CONFIG | browser advertising only; domain/config review required |
| Kaluta KYC | READY WITH CONFIG | selected provider, signed/bound callbacks, timeout/error handling; live credentials/endpoints must be operator-validated |
| Shufti | LEGACY/DISABLED | one pending legacy row; callback provider-gated and signed, cannot approve from arbitrary JSON |
| UploadThing | READY WITH CONFIG | authenticated upload middleware and SDK callback verification; deployed callback URL/token/config must be checked |
| S3/local media | PARTIAL | safe resolver/fallback and bounded provider calls; legacy localhost objects and cross-provider GC remain |
| Email | READY WITH CONFIG | bounded/deferred where implemented; production sending must be disabled in candidate |
| Moderation/translation/metadata | PARTIAL | bounded failures and safe URL/media policies; paid/provider contracts require config checks |
| Geography | PARTIAL | bounded; GeoNames `demo` fallback is P1 reliability/config debt |
| Redis | READY AS OPTIONAL | correctness falls back without cache; production availability/topology must be rechecked |

NOWPayments’ official API/IPN documentation confirms API-key authentication and an IPN secret for callback authenticity; payout creation and verification are distinct provider steps ([API guide](https://nowpayments.io/help/payments/api), [IPN guide](https://nowpayments.io/help/what-is/what-is-ipn)). UploadThing documents server-side upload authorization and automatic HMAC-SHA256 callback verification in current SDKs ([auth/security](https://docs.uploadthing.com/concepts/auth-security), [uploads](https://docs.uploadthing.com/uploading-files)). Redis `SET` with `NX` and expiry is the cache single-flight primitive; cache loss does not affect correctness ([Redis SET](https://redis.io/docs/latest/commands/set/)).

## 20. Production config audit

Previously verified runtime: `ENVIRONMENT=production`, `DEBUG=false`, `USE_CELERY=false`, backend `127.0.0.1:8001→8000`, frontend `127.0.0.1:3000→3000`, remote Neon DB.

Repository production compose is fail-closed for production environment validation and configures explicit CORS origins. No secret values were printed. Current code rejects insecure production defaults for JWT/provider mode and enforces explicit external timeouts.

This workstation could not authenticate to the production host over passive SSH, and public DNS resolution also failed locally. Therefore the *current live values* for secret/JWT, frontend/backend URLs, CORS, NOWPayments mode, KYC provider, Redis, S3/media, AnnualAds, UploadThing, SSL termination, image digests, and backup state remain **operator revalidation requirements**. A local `.env` shape is not treated as live production evidence.

## 21. Domain/URL audit

Active runtime, metadata, sitemap, robots, referral sharing, maintenance redirects, and public-link fallbacks now use `kalutafoundation.com`. Remaining `myhigh5.com` occurrences are either product/business email branding or legacy media compatibility and must be reviewed rather than mass-replaced. `kalutasociety.com` remains only in historical reporting; no active `kipe.foundation` reference was found. Localhost references are predominantly development/tests and the intentional legacy-media resolver; prior production media audit found 153 legacy localhost references that remain a data/content issue.

Classification: active old API/domain fallback bugs repaired; brand email INTENTIONAL/OWNER REVIEW; historical reports LEGACY; media references LEGACY; development endpoints INTENTIONAL.

## 22. Performance regression

Prompt 5 performance guards remain green in the full 302-test run. Contest lists/details, current ranking/TopHigh5/MyHigh5, category filtering, search bounding, admin reports, engagement batching, cache hit/miss/invalidation/fallback, external timeout, media fallback, and DB-session cleanup are covered.

Best measured structural improvement remains engagement candidate aggregation from **6 SQL statements to 1 (83.3% fewer round trips)**. Admin reporting moved from `1+4N` to at most four grouped queries; TopHigh5 eliminates at least ten redundant queries per group. Reliable production response-time percentages were not measured because production load testing was prohibited. Application thresholds remain: FAST <150 ms, ACCEPTABLE 150–500 ms, SLOW 500–2,000 ms, CRITICAL >2,000 ms/timeout.

The repaired root causes were repeated ranking/engagement scans, N+1/count loops, unbounded lists, redundant serialization/fetching, and unbounded external calls—not the proxy timeout. Pending P1 indexes and live slow-request correlation still matter.

## 23. DB connection audit

The latest read-only catalog session saw its own PgBouncer active connection plus one `application_name=unspecified` session idle in transaction for approximately 473 seconds. An immediately prior check saw only the auditor; Prompt 5 had observed two such sessions. The issue is therefore intermittent but recurrent. No session was terminated.

The engine is singleton-scoped with dependency cleanup, `pool_pre_ping`, bounded pool timeout/recycle, and no per-request engine creation. With the repository’s one Uvicorn process, maximum configured DB pool capacity is 30. Any worker increase must multiply that capacity calculation and isolate scheduler ownership.

Release gate: identify the unspecified client/process, verify transaction age/statement/application-name telemetry, and prove no request/external call holds a transaction open.

## 24. Runtime/container topology

Repository candidate topology:

- backend container, one Uvicorn process, loopback port 8001→8000, restart `unless-stopped`, fast `/health` check;
- frontend container, loopback port 3000→3000, restart `unless-stopped`; no container health check is defined;
- Redis 7 Alpine with AOF and health check;
- host Apache reverse proxy in the supplied configuration, not Nginx.

Passive SSH access was denied, so actual live container names, image digests, resources, health, and absence of stale traffic-serving containers could not be independently reconfirmed. Do not multiply backend workers until VPS memory/CPU and Neon connection budget are measured.

## 25. Scheduler/Celery status

`USE_CELERY=false`; no active correctness-critical path was found that queues solely to Celery. Four in-process operations remain: payment reconciliation, contest status, season migration, and monthly operations. The prior duplicate monthly-round scheduler was removed by aliasing it to the single monthly-ops runner.

This is acceptable only with one backend scheduler owner. Multiple Uvicorn workers/replicas would duplicate loops unless a dedicated scheduler role or DB/Redis lease is introduced. Current/future lifecycle calls are idempotent/fail-closed, but process downtime pauses jobs; catch-up behavior must be tested in candidate. Celery remains disabled and was not activated.

## 26. Nginx findings

No Nginx production file is present in the supplied deployment bundle; it contains an Apache virtual host. Every `ProxyPass` has `retry=0`, so the supplied proxy does not retry non-idempotent mutations. The configured timeout is 120 seconds; this is not recommended as a substitute for fixing slow endpoints. Backend/client/DB/provider timeouts are shorter and bounded.

The supplied file does not prove the active SSL virtual host, compression/static caching, HSTS/CSP/referrer/permissions headers, request body limits, forwarded-proto handling, or current production include order. Exact future change: preserve `retry=0` for API/GraphQL/payment/webhook routes, add headers/body/static rules only in the actual SSL vhost after an AnnualAds iframe CSP report-only trial, and never enable generic failover retries for mutation requests.

## 27. Backup/rollback plan

Before any deployment:

1. Create and verify a fresh Neon snapshot/branch; test a restore/read connection and record immutable reference/time.
2. Archive current deployed application tree and record backend/frontend image tags and digests.
3. Securely export the effective environment inventory and secret references without placing values in Git/logs.
4. Back up Apache/SSL configuration and enabled-site mapping.
5. Record baseline counts, schema fingerprint, journal/commission totals, connection state, and health/latency.

Rollback triggers: migration/precheck failure; schema fingerprint surprise; health/login failure; material 5xx/504 increase; ranking mismatch; vote-count change; unbalanced journal; payment/webhook/KYC failure; or container crash loop.

Rollback: stop release traffic if necessary; redeploy prior immutable images/config; restore snapshot only if schema/data mutation occurred and after preserving failed-state evidence; revalidate counts/journals/login/health. Do not use blind Alembic downgrade for recovery. Payout/refund/provider operations remain disabled during rollout so rollback cannot duplicate external money movement.

## 28. Staging/candidate plan

Create an isolated production-like candidate using a restored Neon branch, distinct Redis namespace, production build flags, and the combined code. Block outbound live NOWPayments payout/payment creation, KYC, blockchain, production email, and destructive media calls at both config and network levels; use provider sandbox/mocks and separate secrets.

Candidate gates:

1. Apply the reconstructed-baseline/reconciliation plan from an `f3merge01`-equivalent snapshot.
2. Compare complete schema fingerprints and run all constraint prechecks.
3. Start backend/frontend/Redis/proxy; verify health and registered routes.
4. Run smoke and full suites, then PostgreSQL concurrency tests.
5. Verify votes remain 86,345 and journals/commissions/wallets are unchanged unless a separately approved candidate-only correction replay is being tested.
6. Exercise payment/KYC/AnnualAds only with mocks/sandbox.
7. Prove backup restore and application rollback.

No safe restored snapshot was available in this environment, so candidate validation is **BLOCKED/NOT RUN**, not passed.

## 29. Concurrency validation

SQLite/isolated application tests cover idempotent payment finalization, commission creation, withdrawal reservation, payout state, refund replay, webhook replay, voting uniqueness, cache single-flight, and ranking concurrency behavior.

The two tests requiring real PostgreSQL row locking are explicitly skipped unless `RUN_POSTGRES_TESTS=1`. The local configured DB is production and therefore was not used. Docker, `psql`, and an isolated local PostgreSQL service were unavailable. Status: **BLOCKED pending candidate PostgreSQL** for duplicate payment webhook, duplicate commission, concurrent withdrawal, payout/refund/provider replay, and ballot uniqueness under actual row locks/unique constraints.

## 30. Backend tests

Command: `backend/venv/Scripts/python.exe -m pytest -q` from `backend`.

Result: **302 passed, 0 failed, 2 skipped in 22.06s**. Both skips are in `tests/test_accounting_flow.py` and require an explicitly isolated live PostgreSQL database. They were not hidden or forced against production.

Prompt 2, 3, 4, 5, 6, 7, 8, and 9 regression groups all pass in the combined suite. Prompt 10 added release-gate coverage for routes, maintenance mode, scheduler aliasing, and request-time DDL.

## 31. Frontend tests/build

- Unit tests: **17 files, 75 passed, 0 failed**.
- TypeScript: `tsc --noEmit` **PASS** (32 prior errors across 13 files repaired).
- ESLint: **PASS with warnings**, no errors. Remaining warnings concern hooks, `<img>`, accessibility, and console usage.
- Production build: **PASS**, compile succeeded and **88/88 pages** generated.
- Warnings: stale `caniuse-lite` data and one edge-runtime/static-generation limitation.
- Next config skips build-integrated type/lint checks, but both were run separately and passed.

## 32. Smoke test matrix

| Path | Isolated automated result | Candidate/live result |
|---|---|---|
| Auth/login/token/profile | PASS | BLOCKED pending candidate/live access |
| Contest list/detail | PASS | BLOCKED |
| Ranking/TopHigh5/MyHigh5 | PASS; historical fails closed | BLOCKED |
| Categories/media/search | PASS | BLOCKED |
| Admin authentication/gates | PASS | BLOCKED |
| Financial reads/payment mock/refund mock | PASS | BLOCKED |
| KYC session/callback mock | PASS | BLOCKED |
| AnnualAds auth/receipt mock | PASS | BLOCKED |
| Health/readiness | PASS | BLOCKED; public DNS failed locally |

No production financial provider was contacted.

## 33. Dormant-feature validation

- Internal native advertising finance: **fail-closed**; model/helper remains, mutation/finance router absent.
- Premium Clubs: **fail-closed**; UI is demo/read only; no payment/payout activation.
- Marketplace: **fail-closed**; no checkout, entitlement, earning, refund, or seller-payout activation.
- Shufti mutation: provider-gated and signed; arbitrary JSON cannot approve.
- Plural wallets: no active ORM/API/writer.
- Legacy accounting modules: not registered; production maintenance mutations are guarded.

This is a successful release property. Do not treat build success as authorization to activate these domains.

## 34. Feature readiness matrix

| Feature | Code | DB | Security | Financial | Tests | Production status |
|---|---|---|---|---|---|---|
| Authentication | repaired | compatible, token revocation incomplete | PASS/P1 token hardening | n/a | PASS | READY WITH RESTRICTION |
| Profiles | repaired | compatible | PASS | n/a | PASS | READY WITH RESTRICTION |
| Contests | repaired | history anomalies | PASS | n/a | PASS | READY WITH RESTRICTION |
| Voting | repaired | current rows conform | PASS | n/a | PASS | READY WITH RESTRICTION |
| Current ranking | canonical | current prechecks pass | PASS | n/a | PASS | READY WITH RESTRICTION |
| Historical ranking | fail-closed | context ambiguous | safe denial | n/a | PASS | BLOCKED |
| Categories | canonical | 7 missing links/1 slug | PASS | n/a | PASS | READY WITH RESTRICTION |
| Media | canonical | legacy references | PASS | n/a | PASS | READY WITH RESTRICTION |
| Affiliate | canonical | uniqueness partly present | PASS | USD 2 gap | PASS | READY WITH RESTRICTION |
| Payments | repaired | idempotency schema incomplete | PASS | ledger partial | PASS | BLOCKED pending P0 |
| Withdrawals | repaired | payout state schema incomplete | PASS | canonical service | PASS/PG skip | BLOCKED pending P0 |
| Payouts | durable intent service | idempotency schema incomplete | PASS | canonical service | PASS/PG skip | BLOCKED pending P0 |
| Refunds | compensating service | first-class schema absent | PASS | canonical service | PASS | BLOCKED pending P0 |
| KYC | provider dispatcher | legacy enum/data | PASS | current deposit integration | PASS | READY WITH CONFIG |
| AnnualAds | active external | existing receipt model | PASS | signed receipt path | PASS | READY WITH CONFIG |
| AdSense | active external | n/a | config/CSP review | external | build | READY WITH CONFIG |
| Native advertising | dormant | legacy/incomplete | fail-closed | disabled | PASS | DORMANT |
| Premium Clubs | dormant | incomplete | fail-closed | disabled | PASS | DORMANT |
| Marketplace | dormant | incomplete | fail-closed | disabled | PASS | DORMANT |

## 35. P0 blocker matrix

There are **9 remaining deployment blockers**.

| # | Blocker / domain / why P0 | Exact remediation | Change types | Staging/downtime/validation |
|---:|---|---|---|---|
| 1 | Alembic lineage and production schema equivalence unproven | recover/build `f3merge01` baseline, fingerprint, dry-run | schema/process | staging yes; brief production schema window likely; exact fingerprint/count checks |
| 2 | Active finance lacks final DB provider/payout/refund idempotency/state constraints | implement groups 5–8/10/15 after snapshot prechecks | schema/code | staging yes; online builds preferred; concurrency + replay tests |
| 3 | NOWPayments credentials historically exposed and live contract unverified | controlled API/IPN rotation and sandbox/live config validation | config/provider | staging plus provider action; payment maintenance window; signed callback/status test |
| 4 | Deposits 51/53 understate payable by USD 1 each | independently approve/post two idempotent balanced compensating journals | data | rehearse staging; no broad downtime; reconciliation to zero |
| 5 | Category/period production anomalies block intended invariants | business-owned mapping for 7 contests/1 slug and disposition of 3 duplicate month pairs | data/schema | staging rehearsal; maintenance approval; rerun prechecks |
| 6 | Historical TopHigh5 cannot be certified | keep unavailable and obtain explicit product acceptance; never infer | product/config | staging verify denial; no downtime |
| 7 | Plural wallet USD 2,441 provenance unknown | governance signoff to keep isolated/read-only; investigate import history | data governance | staging not enough; no change/downtime; prove no writer |
| 8 | No restored-production dry run or PostgreSQL concurrency/provider-mock validation | create candidate and complete sections 28–32 | test/infrastructure | staging required; no production downtime |
| 9 | Current live topology/config/backup/SSL-proxy state not independently verified; recurrent idle transaction | operator inventory, backup proof, identify session/client, health/config capture | operations/config | mostly production read-only; no downtime; signed evidence/checklist |

## 36. P1/P2 deferred work

P1: create measured performance indexes; shorten browser token lifetime/add refresh rotation/revocation; deploy distributed/edge rate limiting; CSP report-only then enforcement compatible with AnnualAds; DNS rebinding-resistant egress resolver/firewall; unified role governance; identify/alert idle transactions; frontend health check; production log/metrics integration; GeoNames credential; clarify AnnualAds identifier; complete media-provider garbage collection; label/remove mock historical vote-history UI; review marketing claims for dormant shop/clubs.

P2: legacy code/table cleanup after provenance proof; optional trigram and dormant feature indexes; replace `<img>` warnings; refresh browserslist data; accessibility/hook warning cleanup; scheduler extraction if scaling beyond one worker.

## 37. Recommended deployment unit

**NOT READY.** After P0 remediation, use a **phased release**, not one blind combined push:

1. Preparation phase: snapshot, lineage reconstruction, data review, candidate dry run, secrets staged, dormant gates verified.
2. Schema/data-control phase: approved baseline/reconciliation migrations and only approved deposits 51/53 corrections; validate before application traffic.
3. Coordinated application/config phase: backend/frontend images, environment/provider rotations, proxy/header changes.
4. Validation/monitor phase: smoke, reconciliation, metrics, then release traffic.

Code and schema phases must be backward/forward compatible. No phase may activate native ads, clubs, marketplace, or historical TopHigh5.

## 38. Future migration sequence

1. Change freeze and approvals.
2. Verified Neon snapshot/branch, app/image/config/proxy backups.
3. Capture schema/data/financial/connection baseline.
4. Run preflight SQL for every constraint.
5. Reconstruct/approve the `f3merge01` baseline; no production stamp.
6. Dry-run all additive reconciliation revisions on restored production.
7. Add compatible source/idempotency/audit columns and backfill deterministic values in candidate.
8. Build unique/performance indexes concurrently where supported; attach constraints after duplicate checks.
9. Re-run schema fingerprint, counts, financial reconciliation, and PG concurrency suite.
10. Execute the approved production migration window from the existing `f3merge01` marker only after equivalence is proven.
11. Apply separately approved compensating data entries.
12. Deploy immutable backend/frontend images and environment.
13. Rotate NOWPayments secrets in controlled order.
14. Restart only required services, validate health/smoke/reconciliation, monitor, then release.

Abort on any unexpected revision, DDL, duplicate, lock, count change, or financial mismatch.

## 39. Future data-correction sequence

1. Category/period owners decide mappings/dispositions with preserved audit evidence; historical vote attribution remains untouched.
2. Finance owner and independent reviewer approve deposit 51 and 53 journals described in section 14.
3. Apply each correction through a one-time idempotent maintenance command after schema source uniqueness exists.
4. Verify journal/subledger equality and record immutable audit notes.
5. Keep plural wallets read-only; it is not a correction candidate.
6. Historical voting ambiguity is not a correction candidate.

## 40. Observability requirements

Use existing logs/health plus whatever metrics facility the operator confirms. Initial provisional alerts, to be tuned from staging baseline:

- any 504 in five minutes; 5xx >1% for five minutes;
- p95 public API >2 seconds for ten minutes, or ranking p95 >2 seconds;
- DB connections >80% of effective pool/Neon limit;
- any idle-in-transaction >60 seconds or query >30 seconds;
- payment/IPN signature/finalization failures >0 sustained, replay conflicts above known retry baseline;
- any payout state stuck/submission failure (payout remains disabled during release);
- KYC callback signature/binding failures >0 sustained;
- ranking/context fail-closed error-rate spike;
- unhealthy backend/frontend/Redis container or repeated restart;
- Apache upstream/connect errors >0 sustained.

Logs must include request/reference IDs and state transitions, not secrets, authorization headers, raw KYC payloads, or full payment payloads.

## 41. Post-deployment validation

Future checklist: confirm container/image/config versions and health; homepage; login/logout/new-token behavior; profile; contest list/detail; current voting/ranking/TopHigh5/MyHigh5; category filters; media fallback/upload authorization; search; admin authorization; financial read-only endpoints; non-mutating NOWPayments status/currency plus provider-sandbox signed webhook; safe Kaluta sandbox callback; AnnualAds SSO/receipt sandbox; DB table/vote/journal/commission/wallet counts; deposits 51/53 approved correction result if separately authorized; connection/idle-transaction state; Apache upstream logs; 5xx/504/latency.

Do not validate using a real payout, refund, KYC charge, blockchain transaction, production email, or fake production engagement event.

## 42. Remaining code risks

Production-relevant markers: historical vote-history UI still has mock/TODO data and must not be represented as certified; club cards use demo data and must remain marketing-only; GeoNames defaults to `demo`; voice comparison is incomplete and must not be treated as strong verification; suggested users/groups return empty placeholders; some analytics screens use mock fallback and must not become financial authority; marketing copy references shop purchases while marketplace is dormant.

Intentionally retained dormant modules are safe only while routers, links, scheduler imports, and feature flags remain absent. No new high-confidence secret was found in the current tree. Historical Git exposure of NOWPayments credentials remains until provider rotation and repository-history access governance are addressed.

## 43. Final readiness decision

**C — READY FOR STAGING ONLY.**

Evidence for readiness to stage: single canonical implementations are identified; 381 routes have no duplicates; critical dormant paths fail closed; all available backend/frontend tests and checks pass; current production votes and journal balances were verified read-only; material frontend contracts and final cross-prompt conflicts were repaired.

Evidence against production deployment: nine P0 blockers remain, including unproven Alembic recovery, active financial schema/idempotency gaps, two approved data corrections, known production category/period anomalies, unknown plural-wallet provenance, required NOWPayments rotation, absent restored-snapshot/PG concurrency validation, recurrent idle transaction, and missing current live topology/config/backup proof.

Exact next action: **create a fresh isolated Neon production branch/snapshot, recover/search for `f3merge01`, capture a full schema fingerprint, and execute the documented baseline/reconciliation dry run with the full PostgreSQL concurrency and provider-mock suites.** Do not deploy, stamp, migrate, correct data, or rotate production credentials before that gate passes and the P0 owners approve remediation.
