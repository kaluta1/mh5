# MyHigh5 / Kaluta Society — Master Codebase and Database Audit

**Audit date:** 2026-09-06 (Asia/Dhaka)  
**Audited source:** local working tree at `D:\laragon\www\mh5`, Git commit `a134b6c93f95a3c71f81ad2c1bc743f2dd8d6fc0` plus pre-existing uncommitted changes  
**Production site probed:** `https://kalutasociety.com` using safe GET requests only  
**Production database:** Docker PostgreSQL `kalutasociety_db` as `kalutasociety_user` (identity confirmed by the live API; direct catalog access unavailable)  
**Reference database:** the existing Neon/reference connection in the local backend environment, queried in a read-only transaction only

## 1. Executive Summary

The application is a large FastAPI/Next.js monolith with 377 registered `/api/v1` route objects (376 unique method/path pairs), 126 registered SQLAlchemy mappers over 128 ORM tables, 88 Next.js page source files, Redis-backed caching/Celery plumbing, local/S3/UploadThing storage, three overlapping voting stores, and extensive payment, affiliate, KYC, advertising, club, marketplace, and accounting code.

Five P0 defects are confirmed in source: Shufti KYC callbacks are not authenticated; checkout accepts a client-supplied amount without matching the product price; NOWPayments payout calls occur before durable database completion; payout paths lack concurrency/idempotency protection; and a later provider refund is ignored once a deposit is marked validated. These can cause false KYC approval, underpayment for paid entitlements, duplicate payouts, or commissions/entitlements surviving refunds.

The active production database could not be queried directly. SSH to the supplied VPS was rejected and PostgreSQL is not exposed; Docker is not installed in the audit environment. A live non-mutating health response proves the application is connected to PostgreSQL database `kalutasociety_db` as `kalutasociety_user` and reports no missing `users` columns. It does **not** expose the catalog facts needed for a complete active-database audit. Therefore active table/index counts, constraints, row counts, PostgreSQL version, extensions, and active `alembic_version` remain **UNCONFIRMED**. The reference database has 167 public tables and matches all 128 registered ORM table/column sets, but it must not be treated as the active database.

### Audit totals

| Metric | Result |
|---|---:|
| P0 issues | **5** |
| P1 issues | **17** |
| P2 issues | **16** |
| P3 issues | **6** |
| Registered SQLAlchemy mappers | **126** |
| ORM tables | **128** |
| Active production public tables | **UNCONFIRMED — access blocked** |
| Reference public tables | **167** |
| Internal API route objects | **377** |
| Unique internal method/path pairs | **376** |
| Next.js page files | **88** |
| External integrations implemented/called | **20** |
| Additional configured/dormant integration hooks | **4** |
| Confirmed hardcoded/mock UI data locations | **6** |
| Alembic repository heads | **3** |

### Evidence boundary

- **PRODUCTION-CONFIRMED:** HTTPS response behavior, active DB name/user reported by the live health endpoint, and backend build ID `myhigh5-active-all-levels-20260818`.
- **SOURCE-CONFIRMED:** route registration, models, execution paths, security controls, service logic, migration graph, frontend consumers, and defects visible in this checkout.
- **REFERENCE-CONFIRMED:** the read-only Neon/reference database facts explicitly labeled “reference.”
- **UNCONFIRMED:** any claim requiring direct catalog/process access to the active Docker database or VPS, including whether every local uncommitted file is deployed.

No data, schema, deployment configuration, service, external provider, email, KYC session, payment, payout, or blockchain transaction was changed or triggered.

## 2. Current Architecture

```text
Browser / mobile web
  |
  +--> Next.js App Router (frontend/app)
  |      |-- client contexts/hooks/services --> /api/v1/*
  |      |-- server route handlers --> UploadThing, Sightengine,
  |      |                         OpenAI-compatible API, social oEmbed
  |      `-- AnnualAds iframe / Google AdSense
  |
  `--> reverse proxy (production behavior: /api/* reaches Uvicorn)
          |
          v
       FastAPI (backend/main.py)
          |-- middleware: CORS, logging, build ID, rate limit, headers
          |-- routers (backend/app/api/api_v1/api.py)
          |-- dependency auth/RBAC (backend/app/api/deps.py)
          |-- CRUD and services
          |-- SQLAlchemy synchronous Session
          |       `--> PostgreSQL service postgres:5432
          |             active DB kalutasociety_db
          |-- Redis cache / Celery broker+result backend
          |       `--> Celery worker + beat OR in-process schedulers
          |-- local media volume or AWS S3
          `-- external providers: NOWPayments, KYC, moderation,
              email, AnnualAds, geolocation, AI
```

The production root is served by Apache and Next.js; `/api/v1/*` is proxied to Uvicorn. `/health` and `/openapi.json` at the root returned the frontend 404, showing that only the API prefix is exposed through the observed proxy. The repository also mounts a root `/graphql` endpoint, but production proxy reachability was not proven.

## 3. Backend Architecture

| Responsibility | Exact source | Behavior |
|---|---|---|
| Application entry | `backend/main.py` | Creates FastAPI app, lifespan, middleware, API router, GraphQL and static media mounts, Socket.IO wrapper. |
| API composition | `backend/app/api/api_v1/api.py` | Registers 44 endpoint modules under `/api/v1`. Import failure aborts startup. |
| Settings/env | `backend/app/core/config.py`, `backend/app/core/env_loader.py` | Reads process env and `.env`; validates critical production secrets during lifespan. |
| DB engine/session | `backend/app/db/session.py`, `backend/app/db/base_class.py` | Sync SQLAlchemy engine; pool size 10, overflow 20, 10-second pool wait, default 20-second PostgreSQL statement timeout. Request dependency rolls back on errors and closes. |
| ORM | `backend/app/models/__init__.py`, `backend/app/models/*.py` | 126 runtime mappers, 128 metadata tables. |
| CRUD | `backend/app/crud/*.py` | Query and persistence layer; several endpoints also query ORM directly. |
| Services | `backend/app/services/*.py` | Contest transitions, payments, commissions, KYC, accounting, mail, storage, moderation, scheduling. |
| Auth/RBAC | `backend/app/api/deps.py`, `backend/app/core/security.py`, `backend/app/models/user.py` | HS256 bearer JWT, active-user check, admin boolean, role/permission dependencies. Default access token lifetime is seven days. |
| Redis | `backend/app/core/cache.py` | Eagerly connects at import; failures are fail-soft. JSON cache decorator; pattern invalidation uses blocking `KEYS`. |
| Celery | `backend/app/celery_app.py`, `backend/app/tasks/*.py` | Redis broker/backend; hourly monthly-round, season-migration, and status tasks. |
| In-process jobs | `backend/app/services/scheduler_manager.py`, `*_scheduler.py` | Starts four schedulers after 10 seconds when `USE_CELERY` is false. |
| Storage | `backend/app/core/storage.py`, `backend/app/services/feed_aws_s3.py` | Local volume with multiple fallback roots, optional S3, separate UploadThing frontend path. |
| GraphQL | `backend/app/graphql/schema.py` | Public query schema for contests/rounds and, critically, accounting data; each resolver opens its own sync session. |
| Realtime | `backend/app/socketio_app.py` and feed/message modules | Socket.IO plus REST messaging/feed APIs. |

Authorization is not uniform. Most admin endpoints call `check_admin`; RBAC endpoints depend on `PermissionChecker`; user endpoints generally use `get_current_active_user`; public discovery endpoints intentionally accept optional auth. The issue register documents exceptions.

## 4. Frontend Architecture

The frontend uses Next.js App Router and client-side bearer authentication. Primary files are `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/middleware.ts`, `frontend/contexts/auth-context.tsx`, `frontend/hooks/use-auth.tsx`, `frontend/lib/api.ts`, `frontend/lib/api-service.ts`, `frontend/services/*.ts`, and `frontend/lib/config.ts`.

There are 88 `page.tsx` files. Routes are:

`/`, `/about`, `/clear-cache`, `/clubs`, `/contact`, `/contestants/[id]`, `/contests`, `/contests/[contestId]/entry/[contestantId]`, `/cookies`, `/dashboard`, `/dashboard/admin`, `/dashboard/admin/{accounting,categories,commission-settings,contestants,contests,kyc,mark-paid,microservices,reports,seasons,suggested-contests,transactions,users}`, `/dashboard/admin/contests/[contestId]/contestants`, `/dashboard/{affiliate-agreement,affiliate-program,affiliates,commissions,contests,favorites,feed,following,founding-member,groups,kyc,leaderboard,messages,my-applications,myhigh5,notifications,profile-setup,search,settings,sponsored,top-high5,vote-history,wallet}`, nested contestant/user/application/feed/group/wallet routes, auth routes, profile routes, referral routes, and three overlapping mobile/static-page trees under `/pages_mobile` and `/about/pages_mobile`.

Twenty Next route handlers implement upload, moderation, link previews, TikTok resolution, referral/share HTML, and translation. `frontend/middleware.ts:8-31` only canonicalizes URLs/share paths; it does not enforce authentication. Page protection is client-side through auth context/hooks.

There are at least three overlapping API clients (`frontend/lib/api.ts`, `frontend/lib/api-service.ts`, service-local `fetch` clients), which produce inconsistent prefix handling and endpoint drift. Production builds explicitly ignore TypeScript and ESLint errors in `frontend/next.config.js`.

## 5. Database Architecture

### Active production database

Live `GET /api/v1/health/db-schema` returned PostgreSQL dialect, DB `kalutasociety_db`, DB user `kalutasociety_user`, and `missing_users_columns=[]`. This confirms the configured application target, but the endpoint cannot answer the requested catalog audit. Direct SSH was rejected and no local Docker client exists.

| Requested fact | Active production result |
|---|---|
| PostgreSQL version | **UNCONFIRMED** |
| Database/user | `kalutasociety_db` / `kalutasociety_user` — **production-confirmed** |
| Database size | **UNCONFIRMED** |
| Public table/index count | **UNCONFIRMED** |
| Schemas/extensions | **UNCONFIRMED** |
| Exact row counts/constraints | **UNCONFIRMED** |
| `alembic_version` | **UNCONFIRMED** |

### Reference database (read-only, never used as active)

| Fact | Reference result |
|---|---|
| PostgreSQL | 17.11 |
| Database/user | `neondb` / `neondb_owner` |
| Size | 165 MB |
| Public base tables | 167 |
| Public indexes | 467 |
| Schemas | `information_schema`, `pg_catalog`, `pg_toast`, `public` |
| Extensions | `plpgsql 1.0`, `pg_trgm 1.6` |
| Alembic stamp | `f3merge01` — revision absent from this repository |

All 128 registered ORM tables exist in the reference DB and their column-name sets match exactly. This is useful evidence of lineage, not proof of the active database.

## 6. Database Table Inventory

### Registered ORM tables (128)

`ad_budget_transactions`, `ad_campaigns`, `ad_clicks`, `ad_creatives`, `ad_impressions`, `ad_performance_metrics`, `ad_placements`, `ad_revenue_shares`, `affiliate_cashout_requests`, `affiliate_commissions`, `affiliate_tree`, `affiliation`, `audit_trails`, `categories`, `chart_of_accounts`, `cities`, `club_admins`, `club_content`, `club_content_comments`, `club_content_likes`, `club_memberships`, `club_transactions`, `club_wallets`, `comment`, `commission`, `commission_rates`, `commission_rules`, `contact_messages`, `contest`, `contest_categories`, `contest_comments`, `contest_entry`, `contest_favorites`, `contest_likes`, `contest_season_links`, `contest_seasons`, `contest_stages`, `contest_submissions`, `contest_template`, `contest_types`, `contest_votes`, `contestant_rankings`, `contestant_reactions`, `contestant_seasons`, `contestant_shares`, `contestant_verifications`, `contestant_voting`, `contestants`, `continents`, `conversation_participants`, `countries`, `deposits`, `digital_products`, `digital_purchases`, `dsp_exchange_rates`, `dsp_transactions`, `dsp_wallets`, `fan_clubs`, `feeds`, `financial_reports`, `follow`, `founding_members`, `founding_pool_snapshot_lines`, `founding_pool_snapshots`, `group_invitations`, `group_join_requests`, `group_members`, `group_messages`, `invitations`, `journal_entries`, `journal_lines`, `kyc_audit_logs`, `kyc_documents`, `kyc_verifications`, `like`, `location`, `login_logs`, `media`, `member_fmp_balances`, `member_fmp_ledger`, `message_read_receipts`, `my_favorites`, `newsletter_subscriptions`, `notifications`, `page_views`, `payment_methods`, `permissions`, `post_comment_reactions`, `post_comments`, `post_media`, `post_reactions`, `post_shares`, `posts`, `private_conversations`, `private_message_read_receipts`, `private_messages`, `prize`, `prize_winner`, `product_reviews`, `product_types`, `referral_clicks`, `referral_code`, `referral_links`, `referral_share_clicks`, `referral_share_conversions`, `referral_share_links`, `regions`, `report`, `revenue_shares`, `revenue_transactions`, `role_permissions`, `roles`, `round_contests`, `rounds`, `search_history`, `social_groups`, `suggested_contest`, `tax_configurations`, `transaction_approvals`, `transactions`, `user_encryption_keys`, `user_verifications`, `user_vote_rankings`, `users`, `vote_sessions`, `votes`, `voting_type`, `wallet`.

### Important table detail

Row counts below are **reference-only**. `PK=id` applies unless shown otherwise. ORM fields supply timestamp/status/nullability descriptions; constraints/index claims are reference-catalog-confirmed where noted.

| Table(s) | Purpose and critical structure | Reference rows |
|---|---|---:|
| `users` | Identity/profile/auth; self-FK `sponsor_id`, FKs to role and geography; soft delete, active/verified/status, timestamps; unique personal referral code. Reference catalog did not show unique constraints for email/username. | 239 |
| `roles`, `permissions`, `role_permissions` | RBAC many-to-many; role inheritance; association composite keys. | not materialized here |
| `contest` | Core contest definition, mode/level/status/dates/requirements; FKs category/location/template; trigram name index. | 196 |
| `contest_seasons`, `contest_stages`, `contest_season_links` | Monthly geographic progression and contest-season association; soft delete/status/date fields; reference has partial unique active season index. | 43 / 11 / not materialized |
| `rounds`, `round_contests` | Monthly round/calendar and many-to-many contest association; legacy direct `round.contest_id` also remains. | 17 / not materialized |
| `contestants`, `contestant_seasons` | Nominee/entrant plus per-season state; many status/geo/media timestamps; unique `(contestant_id, season_id)` in reference. | 578 / 6,865 |
| `contest_entry`, `contest_submissions` | Legacy entry and current submission data, statuses and verification/media references. | 0 / not materialized |
| `votes` | Stage/ranked votes (`voter_id`, contestant/stage/position/points); dominant historical store. | 86,345 |
| `contestant_voting` | Current MyHigh5 five-slot voting (`user_id`, contestant, season, position, points); unique only by user/contestant/season. | 0 |
| `contest_votes` | Legacy `contest_entry` score votes used by `/votes/{contest_id}`. | 0 |
| `contestant_rankings`, `user_vote_rankings`, `vote_sessions` | Materialized ranking/user ordering/session artifacts. | 0 / 0 / not materialized |
| `contestant_reactions`, `contest_likes`, `like` | Multiple reaction/like generations with user/content FKs and timestamps. | 52,821 / not materialized |
| `comment`, `contest_comments`, `post_comments` | Multiple comment generations; parent/reply, moderation and soft-delete/status fields. | 5 / 18,975 / not materialized |
| `contestant_shares`, `post_shares` | Share audit/counting by user/channel/time. | 23,522 / not materialized |
| `page_views` | High-volume contestant/contest page views with time/client dimensions. | 504,629 |
| `wallet`, `transactions` | Legacy stored wallet balance/frozen balance and user transaction register; numeric money, currency/status/reference. | 0 / 0 |
| `deposits`, `payment_methods`, `product_types` | Payment source of truth; numeric fiat amount, provider IDs, crypto strings, status/use/validation timestamps; `order_id` unique, external payment ID not unique. | 69 / not materialized |
| `affiliate_tree`, `affiliate_commissions`, `commission_rules`, `commission_rates` | Sponsor hierarchy and 10-level accruals; numeric amounts/rates; deposit FK; status/paid date. No ORM unique constraint on deposit/beneficiary. | 0 / 14 / not materialized |
| `affiliate_cashout_requests` | Payout audit rows; gross/fee/net, wallet snapshot, provider reference, status/timestamps; provider reference not unique. | not materialized |
| `chart_of_accounts`, `journal_entries`, `journal_lines` | Double-entry ledger; unique generated entry number, numeric debit/credit totals/lines, posted status and dates. | not materialized / 38 / 90 |
| `revenue_transactions`, `financial_reports`, `tax_configurations`, `audit_trails` | Reporting/accounting support. | not materialized |
| `kyc_verifications`, `kyc_documents`, `kyc_audit_logs` | Provider session/reference/status, identity/document/face/address flags, documents and audit trail. | 1 / not materialized |
| `ad_campaigns`, `ad_creatives`, `ad_placements` | Ad definition, budget/status/targeting and creative/placement relationships. | 0 / 0 / 0 |
| `ad_impressions`, `ad_clicks`, `ad_performance_metrics`, `ad_budget_transactions`, `ad_revenue_shares` | Ad events, cost, aggregate metrics, budget ledger and revenue allocation. | 0 for sampled event tables |
| `fan_clubs`, `club_admins`, `club_memberships`, `club_wallets`, `club_transactions`, `club_content*` | Premium club ownership/membership/content and stored wallet transaction subsystem. | 0 for sampled club tables |
| `digital_products`, `digital_purchases`, `product_reviews`, `dsp_wallets`, `dsp_transactions`, `dsp_exchange_rates` | Marketplace product/order/review and DSP wallet/exchange system. | 0 for sampled product/purchase tables |
| `posts`, `post_media`, `post_reactions`, `feeds`, `social_groups`, `group_*`, `private_*` | Social feed, groups, encrypted messaging and media. | not materialized |
| `founding_members`, `founding_pool_snapshots`, `founding_pool_snapshot_lines`, `member_fmp_*` | Founding-member entitlement, monthly pool and FMP ledger/balance. | not materialized |

### Reference DB-only tables (39)

`accounting_periods`, `ad_credit_accounts`, `ad_domain_blocklist`, `ad_slot_bookings`, `affiliations`, `alembic_version`, `app_votes`, `cache`, `cache_locks`, `comments`, `contest_entries`, `contest_templates`, `email_outbox`, `failed_jobs`, `follows`, `fx_rates`, `invoice_sequences`, `invoices`, `job_batches`, `jobs`, `likes`, `link_scan_results`, `locations`, `migration_job_runs`, `migrations`, `password_reset_tokens`, `payout_batch_items`, `payout_batches`, `personal_access_tokens`, `prize_winners`, `prizes`, `referral_codes`, `reports`, `revoked_tokens`, `sessions`, `suggested_contests`, `top_high5_leaderboard`, `user_transactions`, `vote_rankings`, `wallets`.

These look like Laravel/legacy/pluralized predecessors of current tables, but without active-host runtime/import/catalog evidence they are classified **LIKELY LEGACY / UNKNOWN — NEEDS INVESTIGATION**, never safe-to-delete.

## 7. ORM ↔ Database Mapping

| Model module | Model → table set | Main relationships | CRUD/service/API/frontend usage |
|---|---|---|---|
| `user.py` | User→`users`; Role→`roles`; Permission→`permissions`; association→`role_permissions` | sponsor/referrals, role, content, wallets, commissions | `crud_user.py`, auth/users/affiliate/RBAC/admin; auth/profile/admin/dashboard pages |
| `contest.py` | Contest→`contest`; ContestTemplate→`contest_template`; Location→`location`; ContestEntry→`contest_entry`; ContestVote→`contest_votes`; plus favorites/verification/voting type/suggestions | category, rounds, entries, votes | `crud_contest.py`, contests/votes/admin; contest pages |
| `contests.py` | ContestType/Category/Season/Stage/Contestant/Submission/Ranking and links → corresponding plural tables | contest-season and contestant-season many-to-many, round, user | contestant, contests, season migration, GraphQL; MyHigh5/TopHigh5/entry pages |
| `voting.py` | Vote→`votes`; ContestantVoting→`contestant_voting`; VoteSession, MyFavorites, ContestComment, ContestLike, PageView | user/contestant/stage/season | contestant endpoints, migration/ranking services; voting/history/detail UI |
| `affiliate.py`, `affiliation.py`, `commission.py`, `referral*.py` | sponsor tree, commissions/rules/rates, links/clicks/conversions/invitations | user→sponsor chain, deposit/product | affiliate CRUD, commission distribution/payout, affiliate/wallet APIs and dashboards |
| `payment.py`, `transaction.py` | Deposit/ProductType/PaymentMethod→payment tables; UserTransaction→`transactions`; Wallet→`wallet` | user/product/payment/contest | NOWPayments, payment accounting, wallet/admin APIs; wallet/KYC/founding-member UI |
| `accounting.py`, `founding_pool.py`, `fmr.py` | COA/journals/revenue/report/tax/audit plus snapshots/FMP | journal→lines→account; snapshot→lines→member | accounting/payment/founding services, admin APIs, public GraphQL; admin accounting/FMR UI |
| `kyc.py`, `verification.py` | KYC verification/document/audit and user verification/media | user, reviewer, document | KYC CRUD/dispatch/providers and verification APIs; KYC/verification UI |
| `advertising.py` | eight `ad_*` tables | advertiser/campaign/creative/placement/events | CRUD and an endpoint module exist, but router is not registered; AnnualAds webhook only posts journals |
| `clubs.py` | `fan_clubs` and seven `club_*` tables plus transaction approvals | owner/member/admin/content/wallet | CRUD and endpoint module exist, but router is not registered; `/clubs` UI is demo data |
| `dsp.py` | DSP wallet/transaction/rate and digital product/purchase/review | user/seller/buyer/product | CRUD/models exist; no registered marketplace router found |
| `social*.py`, `private_message.py`, `feed*.py` | posts/reactions/comments/shares/groups/messages/feeds/keys | authors, membership, conversations | social/feed/message routers and services; feed/groups/messages pages |
| geography/media/search/notifications | named tables | user/content/geography | registered API and UI services |

`backend/app/models/club.py` declares `Club→club`, `PrivateGroup→private_group`, and `ClubJoinRequest→club_join_request`, but it is not imported by `app.models.__init__` and none of those three tables enter runtime metadata. It is **LIKELY LEGACY**, coexisting with active `clubs.py` and `social_group.py` models.

Confirmed mapping mismatches:

- Three active vote representations serve different APIs and algorithms.
- `Contestant.season_id` is treated in multiple places as if it were a contest ID, while the current design uses `contestant_seasons`.
- The reference DB has 39 tables without a registered ORM model; the reference has no registered ORM table missing and no registered ORM column-name mismatch.
- Reference catalog evidence suggests `users.email`/`users.username` lack database uniqueness despite ORM intent and application pre-checks.
- The unregistered ad, club, accounting and marketplace routers mean models/services do not imply reachable public features.

## 8. API Inventory

The inventory was extracted from the instantiated FastAPI application, not inferred from filenames. Count semantics: one route object per registered decorator; the duplicated media-file GET is counted twice. Root `/health`, `/debug/cors`, `/graphql`, documentation routes, and Socket.IO are outside the 377 `/api/v1` total.

| Module (handler file under `backend/app/api/api_v1/endpoints`) | Count | Security and primary stores |
|---|---:|---|
| admin | 63 | Bearer + `check_admin`; all core, KYC, payment and accounting stores |
| affiliate | 27 | Mostly active user; users, referral/affiliate/commission tables |
| contestant | 28 | Mixed public/optional/active user; contestant, seasons, votes, reactions/comments/shares |
| social | 20 | Mixed public reads and owner/member writes; post/group tables |
| kyc | 20 | User/admin plus provider webhooks; KYC, deposits, journals |
| geography | 17 | Public reads; writes require admin dependency; geography tables |
| RBAC roles | 15 | `PermissionChecker`; roles/permissions/users |
| comments | 11 | Public reads, user writes, owner/moderator changes; comment tables |
| favorites | 11 | User-scoped except test/debug behavior; favorites tables |
| private_messages | 11 | Active-user conversation/member checks; private-message tables |
| auth | 10 | Public register/login/reset/verify; active user for me/change-password |
| feed_groups | 10 | Active user and membership/role checks; feed group tables |
| contests | 8 | Public reads; authenticated participation; admin mutations |
| payments | 8 | Public currencies; otherwise bearer/ownership; deposits/products; NOWPayments |
| verifications | 8 | User ownership/admin; verification tables |
| rounds | 7 | Public reads; mutation protection is inconsistent |
| categories/media/feed_posts | 6 each | Mixed public reads and authenticated/admin writes |
| suggested_contests/voting_types/wallet/feed_messages | 5 each | User/admin as appropriate |
| notifications/search/season_migration | 4 each | Mixed active-user/public/admin; season migration mutations are admin-protected |
| referral_shortener | 3 | Public redirect/conversion, user creation; referral share tables |
| analytics/build-health/follow/feed_keys/newsletter/scheduler/share | 1–11 | See exact list below |

### Complete registered method/path set

Handler is the decorated function in the named module; exact source lines are the decorator/function pairs in that file. Authentication follows the module rules above and exceptions called out in the issue register.

- **admin (63):** `GET /admin/contests`, `GET /admin/contests/{contest_id}`, `GET /admin/contestants`, `GET /admin/contests/{contest_id}/contestants`, `GET /admin/contestants/{contestant_id}/comments`, `POST /admin/contests`, `PUT|DELETE /admin/contests/{contest_id}`, CRUD `/admin/seasons`, approve/reject/status/bulk-create/update contestant routes, comment moderation routes, user list/detail/role/status/delete, statistics/reports/suggestions, user KYC/payment grant, invoice/transaction exports, transaction list, chart/journal/ledger-health, COA ensure, all accounting reports/backfills, founding-pool prepare/approve/post, KYC settlement, and payout status/TOTP/retry routes.
- **affiliate (27):** `GET /affiliates/tree`, `/referrals`, `/referrals/detailed`, `/referrals/count`, `/referrals/all`, `/sponsor`, `/commissions`, `/commissions/summary`, `/commissions/stats`, `/referral-links`, `/revenue-shares`, `/stats`, `/genealogy/{levels}`, `/founding-member`, `/invitations`, `/invitations/{pending|accepted|stats}`, `/leaderboard`, `/leaderboard/mfm`; `POST /referral-links`, `/join/{referral_code}`, `/track-click/{referral_code}`, `/invitations`, `/invitations/bulk`, `/accept-agreement`; `DELETE /invitations/{invitation_id}`.
- **auth (10):** `GET /auth/health`, `/auth/verify-email`, `/auth/me`; `POST /auth/register`, `/auth/verify-email`, `/auth/login`, `/auth/password-reset-request`, `/auth/password-reset-confirm`, `/auth/validate-token`, `/auth/change-password`.
- **contestant (28):** `GET /contestants/debug/all-contestants`, `/user/{user_id}/entries`, `/user/my-entries`, `/user/my-votes`, `/user/my-votes/history`, `/favorites`, `/leaderboard/contest/{contest_id}`, `/contest/{contest_id}`, `/{contestant_id}`, `/{contestant_id}/{reactions|shares}/`, `/{contestant_id}/{reactions|votes|favorites}/details`; `PUT /user/my-votes/reorder`, `/{contestant_id}`; `POST /{contest_id}`, `/{contestant_id}/view`, `/submission`, `/favorite`, `/vote`, `/vote/replace`, `/reaction`, `/share`, `/report`; `DELETE /{contestant_id}`, `/{contestant_id}/favorite`, `/{contestant_id}/reaction`.
- **contests (8):** `POST|GET /contests/`; `POST /contests/{contest_id}/validate-video-link`, `/participate`; `GET /contests/{contest_id}/rounds`, `/contests/{contest_id}`; `PUT|DELETE /contests/{contest_id}`.
- **comments (11):** `GET|POST /comments/{contestant_id}/comments`; `GET|POST /comments/{contestant_id}/media/{media_type}/{media_id}/comments`; `GET|PUT|DELETE /comments/comment/{comment_id}`; `POST /comments/comment/{comment_id}/like`, `/unlike`; `GET /comments/comment/{comment_id}/replies`, `/comments/{contestant_id}/commenters`.
- **favorites (11):** `POST|DELETE /favorites/contests/{contest_id}`; `GET /favorites/contests`, `/contests/{contest_id}/is-favorite`, `/test`, `/debug/contestants`; `PUT /favorites/contestants/reorder`; `POST|DELETE /favorites/contestants/{contestant_id}`; `GET /favorites/contestants`, `/contestants/{contestant_id}/is-favorite`.
- **feed/social/messages (60):** `GET /feed`; feed group CRUD/member/join/leave routes (10); feed key generate/public (2); feed message send/conversations/read/delete (5); feed post create/media/list/detail/comment/reaction (6); social post CRUD/comments/reactions/shares, group CRUD/join/leave/messages, read, feed (20); `/messages` conversation/direct/message/read/group-invitation routes (11); `/groups` add/join/member/role/remove routes (6).
- **geography (17):** continent/region/country/city get/create hierarchy, `GET /geography/search`, `/hierarchy`, `/continents/with-regions`, and `POST /geography/initialize`.
- **KYC (20):** deployment URL diagnostics; `POST /kyc/initiate`, `/submit`, `/proof-of-address`; user status/submission/verification/document routes; six admin verification/statistics/audit routes; `POST /kyc/webhook/shufti-pro`, `/webhook/kaluta`; `GET /kyc/redirect`.
- **payments/wallet (14):** `GET /payments/verify-user`, `/currencies`, `/deposit/{deposit_id}`, `/check-status/{deposit_id}`, `/invoice/{deposit_id}`; `POST /payments/create`, `/sync/{deposit_id}`, `/check/{deposit_id}`; `POST /webhooks/nowpayments`; wallet balance/transactions/stats/withdraw-preview and withdraw.
- **RBAC (15):** permission CRUD, role CRUD/detail/permission-set/add/remove, assign user role, user permissions, current-user permissions under `/rbac`.
- **rounds/seasons/voting (18):** round list/detail/create/update/delete, `POST /rounds/ensure-january`, `/generate-monthly`; `GET /seasons/top-high5`; migration check/city/promotion; legacy `POST /votes/{contest_id}`, `GET /votes/{contest_id}/my`; voting-type CRUD.
- **media (6):** media file GET (registered twice), upload/list/detail/delete.
- **users (11):** current-user GET/PUT/wallet PATCH+GET, suggestions/search, username/id public profiles, followers/following and list.
- **share/referral (14):** 11 share preview/redirect routes; share-link creation, short-code redirect, conversion.
- **other (34):** categories (6), notifications (4), search (4), suggested contests (5), user verifications (8), newsletter (2), follow (2), analytics dashboard, contact, FMR, build-info, DB-schema health, debug continental, AnnualAds webhook/SSO, scheduler run/tasks.

The precise source-runtime total by module is: admin 63, affiliate 27, analytics 1, api 2, auth 10, categories 6, comments 11, contact 1, contestant 28, contests 8, debug_continental 1, favorites 11, feed 1, feed_groups 10, feed_keys 2, feed_messages 5, feed_posts 6, fmr 1, follow 2, geography 17, groups 6, kyc 20, media 6, newsletter 2, notifications 4, payment_webhooks 1, payments 8, private_messages 11, referral_shortener 3, roles 15, rounds 7, scheduler 2, search 4, search_history 2, season_migration 4, share 11, social 20, sponsor_annualads 2, suggested_contests 5, users 11, verifications 8, votes 2, voting_types 5, wallet 5.

Production smoke probes confirmed `/api/v1/contests/?limit=1`, `/categories`, `/geography/continents`, `/build-info`, and `/health/db-schema`. The local `/debug/continental` route returned 404 in production, proving the dirty local tree and deployed route set are not perfectly identical.

## 9. Frontend ↔ API Mapping

| Frontend feature | Client/component | Backend path/handler | Service/store |
|---|---|---|---|
| Login/register/profile | `lib/api.ts`, auth context, login/register/profile pages | `/auth/*`, `/users/*` | user CRUD; users/roles/login logs/referrals |
| Contest discovery/detail | `services/contest-service.ts`, contest pages | `/contests/*`, `/contestants/*`, `/rounds/*` | contest CRUD; contest/round/season/contestant tables |
| MyHigh5/TopHigh5 | contest service and dashboard pages | contestant vote/history/reorder; `/seasons/top-high5` | `contestant_voting`, season migration/ranking |
| Comments/reactions/shares | comments/reactions/shares services | `/comments/*`, `/contestants/*` | multiple comment/reaction/share tables |
| Affiliate | affiliate dashboard pages | `/affiliates/*`, `/users/me/wallet` | users sponsor chain, affiliate commissions/links |
| Wallet/payment | payment service and wallet pages | `/payments/*`, `/wallet/*`, NOW webhook | deposits/products/commissions/cashouts/journals |
| KYC | `services/kyc-service.ts`, KYC page | `/kyc/*` | KYC providers, KYC/deposit/accounting tables |
| Social/feed/groups/messages | `services/social-service.ts` and feed/group/message pages | `/social`, `/feed`, `/groups`, `/messages` | social/feed/group/private-message tables |
| Admin | dashboard admin pages and `lib/services/contest-service.ts` | `/admin/*`, `/rbac/*` | all operational tables |
| Ads/sponsors | root layout/AnnualAds rotator/sponsored page | AnnualAds SSO/webhook; no registered internal ad router | AnnualAds journals; internal ad models dormant |
| Clubs | `/clubs` | no registered clubs router | demo data; club models/CRUD/router dormant |
| Marketplace | no complete reachable storefront found | no registered marketplace router | DSP/product models only |

Confirmed request/route mismatches:

- `frontend/app/dashboard/affiliate-agreement/page.tsx:46` calls singular `/api/v1/user/me`; source exposes `/api/v1/users/me`.
- `frontend/lib/api.ts:297` calls `/api/v1/auth/logout`; no logout route exists.
- `frontend/services/social-service.ts:461-481` calls `/api/v1/private-messages/*`; backend uses `/api/v1/messages/*` with different shapes.
- `frontend/services/social-service.ts:345,350` calls absent social comment-like and poll-vote routes.
- The dedicated comments client calls `/api/v1/contestants/.../comments`, while registered comment routes are prefixed `/api/v1/comments/...`.
- `frontend/lib/fetch-geography-data.ts` defaults to a localhost Oxilor URL and has no matching registered `/oxilor` FastAPI prefix.

## 10. Contest System Findings

Contest creation is available through the admin router and a general contests POST; participation creates or links a contestant and submission after applying contest dates, verification requirements, and ownership rules. The current geographic progression uses `ContestSeason`, `ContestSeasonLink`, and `ContestantSeason`, while legacy `Contestant.season_id`, direct `Round.contest_id`, and association `round_contests` remain in live queries.

The canonical nomination timeline is month M submissions, country voting M+1, regional M+2, continental M+3, global M+4. `SeasonMigrationService` gets/creates destination seasons, selects candidates, deactivates source links, and activates destination links. PostgreSQL global and per-round/level advisory locks plus a partial unique active-season index make routine reruns broadly convergent and reduce duplicate migration. The execution topology is not proven on the VPS.

Confirmed defects: mixed legacy/current season joins; selection based on the `contestant_voting` store while historical reference votes are in `votes`; pre-capping candidate sets before engagement tie-break; non-strict contest-only fallback that can include prior-period votes; and one older ranking updater that targets `Contestant.season_id` instead of the association table.

## 11. Voting/Ranking Findings

Current `POST /contestants/{id}/vote` resolves an active contestant-season, enforces self-vote/date/geography checks, counts the user's bucket, assigns positions 1–5 and corresponding points, commits, then attempts ranking recomputation and notification. Replacement deletes the fifth vote and inserts the new fifth position in the same DB transaction.

Three vote systems coexist:

1. `votes` (`app.models.voting.Vote`) — 86,345 rows in the reference DB; stage/ranked history.
2. `contestant_voting` — the current MyHigh5 position/points path and migration input; zero rows in the reference DB.
3. `contest_votes` — legacy entry score route `/votes/{contest_id}`; zero rows in the reference DB.

There is no lock or constraint enforcing one position per bucket or at most five votes, so concurrent calls can both pass the count check. The legacy ranking updater performs roughly 2–3 queries per contestant and orders only points/vote totals without a deterministic tie key. Canonical TopHigh5 migration instead orders points, shares, likes, comments, views, then lower contestant ID, producing unique ordinal ranks rather than shared ties. Because candidates are first capped at at least 200 using points/ID only, high-engagement candidates outside the cap can be wrongly excluded when many point totals tie. Rankings are materialized in tables but are not consistently Redis-cached.

## 12. Affiliate Findings

The canonical chain is `users.sponsor_id`, traversed upward to ten levels. Rates come from active `commission_rules`: level 1 direct percentage and levels 2–10 indirect percentage; fallback only covers KYC. `commission_config.py` states 10% direct and 1% indirect. A visited set stops a cycle during distribution, but sponsor assignment itself does not reject longer circular chains; `set_sponsor` rejects direct self-referral only.

Trace:

```text
NOWPayments confirmation/poll
  -> Deposit becomes VALIDATED
  -> process_payment_validation
  -> distribute_commissions (DB pre-check by deposit)
  -> AffiliateCommission PENDING/APPROVED
  -> immediate NOWPayments payout if wallet/config exists
  -> service entitlement activation
  -> payment_accounting journal(s)
  -> transaction commit by webhook/poll caller
```

The order is unsafe: payout can occur before accounting and before the outer transaction commits. Duplicate checks have no supporting unique constraint and are race-prone. Commission status has cancellation, but a validated/refunded deposit never enters reversal logic. Wallet views are computed from commission rows rather than the legacy `wallet.balance`; the ledger and cashout rows are separate representations.

## 13. Financial/Accounting Findings

Accounting uses a double-entry `journal_entries`/`journal_lines` ledger. Entries validate exact Decimal debit=credit and generate UUID-suffixed entry numbers. Reports calculate from ledger lines. Separately, `wallet.balance`, `club_wallets`, DSP wallets, commission status totals, deposits, and transactions are stored balances/registers; there is no single unified financial source of truth.

Money columns are PostgreSQL `NUMERIC`, but many Python annotations are `float` and services convert Decimal to float before ORM/provider calls. That creates avoidable precision boundaries. Journal creation can participate in an outer transaction with `commit=False`, but many paths commit internally. No durable outbox, payment-event table, provider-id unique constraint, or payout idempotency key was found.

Manual withdrawal sends the external payout before locking/reserving commission rows. It then marks complete whole FIFO commission rows until the requested gross is crossed; a $100 withdrawal can mark a single $150 commission fully paid. Auto-payout similarly calls NOWPayments before marking/committing. These are the highest financial integrity risks.

## 14. Payment Findings

NOWPayments checkout is live/sandbox selectable via `NOWPAYMENTS_SANDBOX`; the default is live (`false`). `/payments/create` authenticates the user, loads the product by code, stores a pending deposit, calls `/v1/payment`, and stores provider details. HMAC-SHA512 IPN verification is correctly fail-closed when the secret/signature is absent. Polling endpoints enforce deposit ownership/admin.

Critical gaps are not in signature validation but in business integrity: request `amount`/`currency` are trusted instead of the server-side product price/currency; `external_payment_id` is not unique; finalization checks only current status, not an event/idempotency record or row lock; it calls payout-bearing commission logic before the outer commit; and a validated row returns early even if a later signed event says `refunded`. No refund/reversal journal or commission clawback path is called.

AnnualAds verifies HMAC-SHA256 plus a five-minute timestamp. Its replay/idempotency check searches a journal description containing `tx_hash`, but there is no unique transaction key and two concurrent callbacks can both pass. It posts a net deferred-revenue journal and may create missing COA accounts inside the callback.

No direct blockchain transfer code was found in the registered payment flow. BSC appears primarily as the NOWPayments currency/network label; direct-chain scripts/config hooks are dormant/legacy and were not executed.

## 15. KYC Findings

`KYC_PROVIDER` selects Kaluta KYC (default) or legacy Shufti Pro. Initiation checks a validated, unused KYC deposit, reuses a valid provider session, updates attempt state, consumes the deposit, and then calls the provider. Because consumption is committed before provider session creation, a provider error can consume the paid attempt without a usable session.

Kaluta webhooks verify `X-Kaluta-Signature` with the configured secret and fail closed in production if the secret is absent. Shufti has a correct `verify_webhook_signature` helper, but `/kyc/webhook/shufti-pro` never receives raw body/signature and never calls it; a caller who learns/guesses a reference can submit `verification.accepted` and change verification flags. This is P0.

KYC proof-of-address storage limits input to 10 MB and sanitizes filenames. The authenticated deployment-diagnostic routes expose URL/config-presence information and part of the Shufti client identifier, which should remain operator-only.

## 16. Ads Findings

Internal ad models and a 15-route `advertising.py` module cover campaigns, creatives, placements, metrics, tracking, budgets, and revenue shares. `api.py` does not import/register that router, so these APIs are unreachable in the instantiated application. Sample reference tables are empty. AnnualAds is the reachable sponsor integration: authenticated SSO token creation and a signed payment webhook that posts accounting. Google AdSense is injected globally with a fixed publisher identifier in `frontend/app/layout.tsx:196-200`.

## 17. Premium Club Findings

`clubs.py` defines fan club, admin, membership, content, wallet, transaction and approval models; CRUD and 14 endpoint decorators exist. The router is not registered. The public `/clubs` page uses `demoClubs`, not database/API data. A second unregistered legacy model file (`club.py`) declares singular tables and is not in ORM metadata. No production-active premium club workflow is proven.

## 18. Marketplace Findings

DSP/marketplace models cover products, purchases, reviews, DSP wallets, transactions, and exchange rates. No registered marketplace endpoint module or complete frontend storefront was found; sampled reference product/purchase tables are empty. This subsystem is **LIKELY INCOMPLETE/DORMANT**, not safe to delete.

## 19. Celery/Background Job Findings

Celery uses Redis DB 0 as both broker and result backend. Beat schedules three hourly tasks: ensure current-month round, process season migrations, and update contest statuses. Tasks retry up to three times with 120–300 second delays and have 25/30-minute soft/hard limits, prefetch 1, and worker recycling after 50 tasks.

When `USE_CELERY=false`, FastAPI lifespan starts in-process payment, contest-status, season-migration, and monthly-round schedulers after a 10-second warm-up. The checked-in Hostinger compose explicitly sets `USE_CELERY=false` and defines no Celery worker/beat, while the user-supplied production context says Celery is enabled. The actual VPS compose/process list was inaccessible, so which jobs run is **UNCONFIRMED**. Season migration has advisory locks; payment/status/monthly job paths do not share a general distributed scheduler lease. Multiple web workers running in-process schedulers can duplicate execution.

The scheduler run endpoint is protected by fail-closed `CRON_SECRET`; task-name listing is public. Numerous root-level one-off schema/fix/reset scripts exist but are not imported by runtime; they must never be scheduled or executed blindly.

## 20. External API Inventory

No secret values were printed or copied. “Active” below means the code calls or embeds the provider when configured; production credential presence/mode is otherwise unconfirmed.

| # | Provider/service | Purpose; source/API | Configuration | Status/risk |
|---:|---|---|---|---|
| 1 | NOWPayments | Pay-in `/v1/payment`, status, IPN; payout auth/payout/verify in `nowpayments_service.py` | `NOWPAYMENTS_*` | Implemented; live by default; P0 transaction/idempotency risks. |
| 2 | Kaluta KYC | Session/status/webhook at `kalutakyc.com/v1`; `kaluta_kyc.py` | `KYC_PROVIDER`, `KALUTA_*` | Default provider; signature verification present. |
| 3 | Shufti Pro | Legacy KYC hosted verification/status at `api.shuftipro.com`; `shufti_pro.py` | `SHUFTI_*` | Implemented; webhook fails to call signature verifier. |
| 4 | Sightengine | Image/video/face moderation in backend and Next handlers | `SIGHTENGINE_*` and misspelled frontend `SLIGTHENGINE_*` | Implemented; failures allow content. |
| 5 | OpenAI-compatible API | Relevance and translation chat completions | `OPENAI_API_KEY`, `AI_API_*` | Implemented; synchronous latency/cost/data handling. |
| 6 | AssemblyAI | Audio/video transcription in frontend server library | `ASSEMBLYAI_API_KEY` | Implemented; polling can be slow/costly. |
| 7 | Resend | Transactional email | `RESEND_API_KEY`, `EMAIL_FROM*` | Implemented; calls are triggered from request/business flow. |
| 8 | SMTP | Email fallback | `SMTP_*` | Implemented fallback; production use unconfirmed. |
| 9 | AWS S3 | Media/feed object storage | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, bucket/region | Implemented optional backend. |
| 10 | UploadThing | Next upload handlers/delete API | `UPLOADTHING_SECRET`, public upload URL | Implemented; multiple handlers and fail-open moderation. |
| 11 | AnnualAds | iframe SSO and sponsor-payment webhook | `ANNUALADS_*`, `NEXT_PUBLIC_ANNUALADS_*` | Implemented; webhook signature/replay-window present, unique idempotency absent. |
| 12 | ipapi.co | Login/device geolocation | none/provider URL | Implemented synchronous HTTP. |
| 13 | ip-api.com | Geolocation fallback over plain HTTP | none/provider URL | Implemented; confidentiality/integrity downgrade. |
| 14 | GeoNames | Country/city lookup | `NEXT_PUBLIC_GEONAMES_USERNAME` | Client integration; default username `demo`. |
| 15 | REST Countries | Geography data | none | Client fetch. |
| 16 | YouTube | oEmbed/link preview/video embed | none | Server fetch/embed; URL validation required. |
| 17 | TikTok | oEmbed/resolution/embed | none | Server fetch/embed. |
| 18 | Vimeo | Video embed | none | Client embed. |
| 19 | Facebook | Video plugin embed | none | Client embed. |
| 20 | Google AdSense | Global advertising script | fixed publisher ID | Always injected by layout when page runs. |

Configured/dormant hooks not counted in 20: `EDEN_API` has no caller; Oxilor clients target an absent backend prefix; Reown/WalletConnect packages have no source initialization; direct BSC/Web3 references are scripts/config residue rather than the registered transaction path.

## 21. Alembic Migration Findings

- `backend/migrations/versions` contains 81 files.
- Repository graph has **three heads**: `c9d0e1f2a3b4`, `s3t4u5v6w7x8`, `u4v5w6x7y8z9`.
- Two branches split from `r2...`; another branch continues from `b4...`; no merge revision joins the current heads.
- The reference DB is stamped `f3merge01`, which is not present in the repository.
- Active `kalutasociety_db.alembic_version` is **UNCONFIRMED**.
- `env.py` imports many but not all runtime models and unconditionally uses `settings.DATABASE_URL`.

Running `alembic upgrade head` today would fail before applying a migration because multiple heads exist and Alembic requires a branch/head target. If someone instead ran `upgrade heads`, behavior depends on the active stamp; a foreign stamp like the reference `f3merge01` would fail with “Can't locate revision.” Even with a recognized stamp, multiple handwritten/idempotent revisions require SQL-by-SQL review. No migration command that changes schema was run.

## 22. Performance Findings

Highest-risk paths:

1. `crud_contest.update_contestant_rankings` issues count/sum/upsert queries per contestant (roughly 3N) after a vote.
2. Wallet transaction building queries each level-1 commission's source user and each deposit's product (N+1).
3. GraphQL mapping repeatedly queries author/ranking/season/round data per nested contest/contestant and can return 100 participants per contest.
4. Contest listing/detail includes compatibility OR queries over legacy and association paths, repeated counts/sums, and Python-side filtering.
5. `page_views` is already high volume (504,629 reference rows); tracking writes occur on request paths.
6. Payment/KYC/moderation/geolocation/email work can run synchronously inside user requests with 15–60 second provider timeouts.
7. Several list/search/detail paths use `.all()` or large limits; some frontend services issue overlapping requests through different clients.
8. Redis cache is fail-soft and scarcely applied to the heaviest ranking/list paths. Pattern invalidation uses `KEYS`, which blocks Redis at scale.
9. The DB pool permits only 30 concurrent connections per process and fails after a 10-second wait; slow sync requests can surface as 504s.
10. The moderated Next upload reads the entire body and base64-encodes it before upload without an endpoint-level byte ceiling.

## 23. Security Findings

- Password hashing uses bcrypt; JWT verification fixes the configured algorithm and looks up the current user. Tokens default to seven days and no active revocation check exists in the current model path.
- Browser tokens are stored in `localStorage`; no Content-Security-Policy was found. Any XSS can exfiltrate the bearer token.
- CORS allows credentials for any `*.vercel.app`, `*.vercel.dev`, `*.onrender.com`, and any IPv4 origin, plus stale domains.
- Rate limiting is in-process, non-distributed, and trusts `X-Forwarded-For`; it can be bypassed across workers or by spoofed headers unless the proxy overwrites them.
- Admin and RBAC endpoints generally enforce checks. Object ownership checks exist on payment, messaging, media and mutation paths, but public voter-detail endpoints expose user identity/history.
- The Shufti webhook is the confirmed critical callback-authentication failure. NOWPayments and Kaluta signature checks are fail-closed; AnnualAds verifies HMAC/timestamp but lacks race-safe uniqueness.
- Upload filenames are sanitized in backend storage and KYC proof size/type is checked. The generic Next moderated upload trusts MIME prefixes, buffers unbounded input, and moderation/face matching fails open.
- Link preview code validates protocols and blocks obvious private/local addresses, but DNS rebinding/redirect targets require hardening and egress policy.
- Public DB-schema health discloses database/user names. Local source also contains public debug/test endpoints.

## 24. Duplicate/Legacy Code Findings

| Classification | Evidence |
|---|---|
| DUPLICATE BUT ACTIVE | Three voting tables/paths; legacy and association round/season joins; several API clients; two CORS layers; local/S3/UploadThing storage paths. |
| LIKELY LEGACY | `models/club.py`; 39 DB-only reference tables; GraphQL comments about missing columns; Render/Kaluta Foundation compose files; root schema-fix scripts. |
| CONFIRMED UNUSED AT RUNTIME REGISTRATION | `advertising.router`, `clubs.router`, `accounting.router`; none is included by `api.py`. This does not prove safe deletion. |
| UNKNOWN — NEEDS INVESTIGATION | `backend/api` alternate entry, microservice-feed, data dumps/backups, deployment directories, direct-chain scripts, which compose file is actually on the VPS. |

The repository contains destructive-looking utilities (`reset_rounds_and_contestants.py`, manual SQL fixes, direct migration scripts). They are not runtime imports, but their presence raises operator-error risk. No such script was run.

## 25. Hardcoded/Mock Data Findings

Confirmed UI/mock count is **6 source locations**:

1. `frontend/app/clubs/page.tsx:26,124` — all clubs come from `demoClubs`.
2. `frontend/app/dashboard/vote-history/page.tsx:45` — real API is bypassed and fake vote history is returned.
3. `frontend/services/analytics-service.ts:97` — default/mock dashboard response on failure/no data.
4. `frontend/app/about/page.tsx:27-30` — hardcoded 1M users, 200 countries, 50K contests, 10M votes.
5. `frontend/app/pages_mobile/about/page.tsx:21-24` — duplicate hardcoded claims.
6. `frontend/app/about/pages_mobile/about/page.tsx:21-24` — another duplicate.

Two additional hardcoded integration fallbacks are tracked separately: old production default `https://myhigh5.com` in `frontend/lib/config.ts:8,53`, and localhost/Oxilor fallback in `frontend/lib/fetch-geography-data.ts`. Configuration constants and test fixtures are not counted as mock production data.

## 26. Database vs Code Mismatches

| Mismatch | Status |
|---|---|
| Active catalog vs ORM | **UNCONFIRMED**; direct active DB access blocked. |
| Reference 128 ORM tables/columns | Exact table and column-name match. |
| Reference extra tables | 39 DB-only, mostly legacy/pluralized/Laravel-shaped. |
| Models without runtime metadata | Three models in `models/club.py`; corresponding singular tables not in reference. |
| User identity uniqueness | ORM/application expects unique email/username; reference catalog did not expose matching unique constraints. |
| Vote data | Historical data is in `votes`; current migration logic reads `contestant_voting`. |
| Alembic | Three repo heads; reference stamp absent from repo; active stamp unknown. |
| Deployment config | Checked-in compose lacks PostgreSQL/Celery and names another domain, unlike supplied active topology. |

## 27. Critical Production Risks and Issue Register

Each row includes evidence, exact source/table/API scope, impact, recommendation, fix risk and dependencies. “Source-confirmed” does not assert that an uncommitted local change is deployed.

| ID / severity | Description and evidence | Files / tables / APIs | Business impact | Recommended solution; fix risk; dependencies |
|---|---|---|---|---|
| AUD-001 P0 | Shufti webhook accepts typed JSON and mutates KYC without signature verification; existing verifier is unused. | `kyc.py:1113-1169`, `shufti_pro.py:527-539`; `kyc_verifications`, `users`; `POST /kyc/webhook/shufti-pro` | Forged identity approval/rejection. | Verify raw bytes and provider signature before parsing/state change. Risk: callback compatibility; depends on provider header/canonicalization and replay tests. |
| AUD-002 P0 | Checkout trusts client `amount`/`currency`; product price is loaded but never enforced except EFM minimum. | `payments.py:38-49,103-146`; `product_types`, `deposits`; `POST /payments/create` | Buy KYC/membership for less than configured price. | Derive amount/currency server-side and validate allowed product. Risk: clients relying on variable amounts; depends on product pricing rules. |
| AUD-003 P0 | Immediate payout is called while payment/commission/accounting transaction is still uncommitted; later rollback cannot undo provider transfer. | `commission_distribution.py:207-227,238-340`, `nowpayments_service.py:195-216`; commissions/deposits/journals | Paid externally with no durable local record; retry can pay again. | Transactional outbox; commit accrual first, worker sends with idempotency key. Risk: payout migration/reconciliation; depends on provider idempotency and audit. |
| AUD-004 P0 | Auto/manual payout uses check-then-send without row lock/reservation/idempotency; provider call precedes PAID mark. | `commission_payout_service.py:57-138,182-267`; `affiliate_commissions`, `affiliate_cashout_requests`; `/wallet/withdraw`, admin retry | Concurrent requests/workers can double-pay. | Lock/reserve rows, unique payout request/key, explicit state machine, reconciliation. High fix risk; depends on provider/API guarantees. |
| AUD-005 P0 | Validated deposit returns early before processing signed `refunded`; no entitlement/commission/journal reversal path. | `nowpayments_service.py:31-35,195-220`; deposits/commissions/journals/users; NOW webhook/sync | Refund leaves paid access and commissions; direct loss. | Append-only payment events and compensating reversals. High risk; requires finance policy and historical reconciliation. |
| AUD-006 P1 | Manual partial withdrawal marks whole FIFO rows until request is crossed. | `commission_payout_service.py:232-252`; commissions/cashouts; `/wallet/withdraw` | Underpays member or overstates paid commission. | Split residual or require exact selected sum. Risk: legacy cashout reconciliation; depends on AUD-004. |
| AUD-007 P1 | Commission duplicate checks have no DB unique constraint and race. | `commission_distribution.py:106-118,151-169`; `affiliate_commissions` | Duplicate accrual/accounting/payout. | Unique `(deposit_id,user_id[,type/level])` plus conflict-safe insert. Risk: existing duplicates; data audit first. |
| AUD-008 P1 | Three vote stores drive different APIs/algorithms; reference history and current promotion source diverge. | `models/voting.py`, `models/contest.py`, contestant/votes/migration services; three vote tables | Incorrect TopHigh5/winners; historical votes ignored. | Declare canonical vote ledger and migration/read compatibility. High risk; depends on active DB profiling. |
| AUD-009 P1 | Five-vote limit/position assignment is check-then-insert without lock/constraint. | contestant vote handlers; `contestant_voting`; `POST /contestants/{id}/vote` | More than five votes or duplicate positions under concurrency. | Bucket transaction lock and unique position constraint. Risk: existing invalid buckets. |
| AUD-010 P1 | Legacy ranking updater queries `Contestant.season_id` and tie order lacks deterministic key. | `crud_contest.py` ranking function; contestants/rankings | Missing/wrong ranks and unstable ties after vote. | Use association and canonical comparator. Risk: ranking changes; dependency AUD-008. |
| AUD-011 P1 | Candidate set is capped before full engagement tie-break. | `season_migration_service.py` TopHigh5 selection; votes/reactions/comments/views | Valid winner outside cap can be excluded. | Apply complete SQL ordering before limit. Risk: winner changes; replay simulations required. |
| AUD-012 P1 | Non-strict ranking fallback uses contest-only votes when season points absent. | `season_migration_service.py`; `contestant_voting` | Prior months can affect a new month. | Remove fallback for production selection or explicitly scope legacy data. Risk: empty historical seasons. |
| AUD-013 P1 | Public `POST /rounds/ensure-january` mutates round state without auth. | `rounds.py`; rounds; endpoint named | Unauthorized production state mutation/DoS. | Admin/cron-secret protection and idempotent constraints. Low code risk; deployment callers must update. |
| AUD-014 P1 | KYC deposit is marked used and committed before external session succeeds. | `kyc.py:327-390`; deposits/KYC; `POST /kyc/initiate` | Paid attempt consumed on provider failure. | Reserve then finalize consumption after session creation; recovery state. Medium risk; provider retry semantics. |
| AUD-015 P1 | GraphQL exposes chart of accounts and journal entries without admin check. Production reachability unconfirmed. | `graphql/schema.py:922-977`; COA/journals; root `/graphql` | Financial ledger disclosure if proxy exposes route. | Require admin context or remove financial fields from public schema. Low code risk; GraphQL clients inventory. |
| AUD-016 P1 | Alembic has three heads; active stamp unknown; reference stamp absent. | `alembic.ini`, `migrations/env.py`, 81 version files; `alembic_version` | Deploy migration failure or wrong schema change. | Obtain active stamp/catalog, reconcile graph, rehearse clone. High operational risk; active read access required. |
| AUD-017 P1 | Checked-in deployment topology/domain contradicts supplied production Docker topology. | `deploy/hostinger/docker-compose.yml`, `backend/docker-compose.yml`, VPS compose unavailable | Wrong DB, missing workers, wrong URLs during deployment. | Audit actual compose/env read-only and establish authoritative config. Risk: do not replace live config blindly. |
| AUD-018 P1 | AnnualAds idempotency is a non-unique description lookup; concurrent signed callbacks can double-post. | `sponsor_annualads.py:218-255`; journals; webhook | Duplicate sponsor revenue journal. | Dedicated event table/unique provider tx hash and conflict-safe transaction. Medium risk; backfill duplicate check. |
| AUD-019 P1 | Reference catalog lacks DB unique constraints for email/username despite app pre-checks. Active state unconfirmed. | `user.py`, `crud_user.py:62-77`; users; register/login | Concurrent duplicate identities/auth ambiguity. | Active duplicate/catalog query, clean then add case-normalized uniqueness. High data risk. |
| AUD-020 P1 | Bearer tokens live in localStorage and no CSP is set. | `frontend/lib/api.ts`, auth context, `next.config.js`, `main.py` | XSS becomes account takeover for seven days. | Strong CSP, XSS review, consider secure HttpOnly session/short tokens. High architectural compatibility risk. |
| AUD-021 P1 | Content moderation and face comparison explicitly fail open. | UploadThing core `:229-245`, moderated route `:185-195,292-319`; media | Prohibited/impersonating content accepted during outage. | Quarantine/pending-review fail-closed for sensitive uploads. Product/availability tradeoff. |
| AUD-022 P1 | Actual Celery vs in-process scheduler topology is unknown; non-season jobs lack distributed singleton protection. | `main.py` lifespan, `celery_app.py`, scheduler manager, compose | Duplicate jobs/emails/status transitions or no jobs. | Verify process list/config, select one runner, distributed locks. Deployment access required. |
| AUD-023 P2 | Public vote/favorite/reaction detail returns voter identity/history. | contestant detail handlers; vote/reaction tables | Privacy enumeration/harassment risk. | Aggregate public data; authorize identifiable detail. API/UI contract risk. |
| AUD-024 P2 | Confirmed frontend routes do not exist or use wrong prefixes. | affiliate agreement, `lib/api.ts`, social/comments services | Broken logout, agreement, messaging, comments/polls. | Contract tests/generated client; correct consumers. Low–medium risk. |
| AUD-025 P2 | Ads/clubs/accounting/marketplace code exists but routes/features are not registered. | `api.py`, endpoint/model modules, `/clubs` UI | Advertised features are mock/dormant. | Product decision then register safely or label unavailable; migration/auth review first. |
| AUD-026 P2 | Ranking, wallet and GraphQL N+1 query patterns. | `crud_contest.py`, `wallet.py:145-270`, `graphql/schema.py` | Slow API/504 and DB load. | Aggregate/eager-load/bulk upsert after correctness fixes. Query-plan validation required. |
| AUD-027 P2 | Redis is fail-soft and not used on highest-load paths; invalidation uses blocking `KEYS`. | `core/cache.py`; contest/ranking services | Cache provides little protection; Redis stalls at scale. | Explicit cache use/invalidation with `SCAN`; correctness dependency. |
| AUD-028 P2 | Credentialed CORS regex trusts arbitrary hosted subdomains and IP origins. | `main.py:133-219` | Enlarged cross-origin attack surface. | Exact production allowlist; remove duplicate middleware. Risk: preview/dev domains. |
| AUD-029 P2 | Rate limit is process-local and trusts forwarded IP. | rate middleware in `main.py` | Bypass across workers/restarts/spoofing. | Redis-backed limiter and trusted-proxy parsing. Depends on proxy topology. |
| AUD-030 P2 | Next middleware does not protect dashboard/admin routes server-side. | `frontend/middleware.ts:8-35` | Protected HTML/UI may flash/load before client redirect; APIs remain primary control. | Server guard/cookie-compatible auth. Architecture risk with localStorage. |
| AUD-031 P2 | Numeric DB values repeatedly cross through float. | payment/accounting/affiliate models and services | Rounding drift/reconciliation noise. | Decimal end-to-end, quantized currency policy. Medium migration/serialization risk. |
| AUD-032 P2 | Provider calls/email/geolocation run in request/payment finalization paths. | payment, KYC, moderation, email, device-location services | Slow requests/504; partial external side effects. | Outbox/background tasks with bounded timeout/circuit breaker. Depends on worker reliability. |
| AUD-033 P2 | Moderated Next upload buffers/base64s the full body without route byte cap. | `app/api/upload/moderated/route.ts:55-76` | Memory exhaustion/DoS. | Enforce content length/streaming/provider limits. Low compatibility risk. |
| AUD-034 P2 | Six confirmed mock/hardcoded UI locations. | section 25 files | Misleading metrics and nonfunctional clubs/history. | Connect live APIs or label demo; preserve fallback telemetry. Product input needed. |
| AUD-035 P2 | Old domains and localhost/Oxilor fallbacks remain. | `frontend/lib/config.ts`, `fetch-geography-data.ts`, CORS/comments | Cross-environment data access or broken production calls. | Required production env and startup/build validation. Deployment coordination. |
| AUD-036 P2 | 39 reference DB-only tables and multiple conceptual duplicates. | section 6; reference DB | Schema confusion, accidental reads/migrations. | Active dependency/query-log analysis; never delete from this audit. High cleanup risk. |
| AUD-037 P2 | Wallet `available_balance` sums already PAID (already sent) commissions; if payout config absent it relabels pending as available. | `wallet.py:27-71`; commissions | Users see misleading withdrawable balance. | Define earned/accrued/withdrawable/paid separately. UI/accounting semantics dependency. |
| AUD-038 P2 | Provider external payment and payout references are nullable/non-unique. | `payment.py:143-148`, affiliate models | Ambiguous reconciliation/idempotency. | Partial unique indexes per provider plus event table. Existing duplicate audit required. |
| AUD-039 P3 | Same media file route is registered twice. | `api.py`/media registration; `GET /media/file/{user_id}/{filename}` | Confusing OpenAPI/routing maintenance. | Keep one registration after route tests. Low risk. |
| AUD-040 P3 | Debug/test routes remain in source; continental debug is not live in probe. | contestant/favorites/debug modules | Information disclosure/noise if deployed later. | Admin/debug flag gating. Low risk. |
| AUD-041 P3 | Static mobile pages are duplicated under two trees. | `app/pages_mobile`, `app/about/pages_mobile` | Copy drift and inconsistent content. | Shared components/canonical routes. SEO regression risk. |
| AUD-042 P3 | Many manual schema/fix/reset scripts live at backend root. | `backend/*.py`, `backend/*.sql` | Operator error and unclear migration authority. | Inventory, checksum/archive with runbooks; do not execute/delete yet. |
| AUD-043 P3 | Stale comments/fallbacks claim DB columns may be missing although reference matches; unregistered legacy model remains. | GraphQL schema comments, `models/club.py` | Maintainer confusion. | Verify active schema, update documentation, then deprecate deliberately. |
| AUD-044 P3 | Public health reveals DB name/user. | live `/api/v1/health/db-schema`, API module | Low-grade reconnaissance. | Return only health boolean publicly; protect detail. Monitoring dependency. |

## 28. Recommended Fix Order

1. Disable or authenticate the Shufti webhook immediately; verify whether Shufti is still selected anywhere and audit recent KYC approvals.
2. Stop client-controlled payment pricing; compare all pending/validated deposits against immutable server-side product price/currency.
3. Suspend automatic/manual payout retries until provider payouts and local commission/cashout records are reconciled for duplicates.
4. Design a durable payout/payment event state machine with outbox, idempotency keys, row reservation and reconciliation before re-enabling unattended payouts.
5. Add refund/reversal handling for entitlements, commissions, cashouts and double-entry journals.
6. Obtain read-only active DB/VPS access; capture catalog, active Alembic stamp, constraints, duplicates, row counts, job processes and actual compose/env variable names.
7. Reconcile the three voting stores against active data and formally choose the canonical ledger before changing ranking or migrations.
8. Correct vote concurrency, season scoping, candidate ordering and ranking tie rules; replay historical months in a cloned database before production changes.
9. Resolve the three-head Alembic graph and foreign/missing revision lineage in a clone; never run `upgrade head` on production as-is.
10. Establish one authoritative deployment topology and exactly one periodic-job runner, with distributed singleton locks where needed.
11. Protect/disable financial GraphQL fields and public mutation/debug/detail endpoints; tighten CORS, rate limiting and CSP/token handling.
12. Repair frontend/backend route contracts and label/remove mock presentation only after live replacements are verified.
13. Optimize N+1/query plans and add targeted Redis caching after correctness and integrity work.
14. Classify dormant ads/clubs/marketplace and legacy tables from runtime/query evidence; do not delete by appearance.

### Top 10 risks to fix first

1. Forged Shufti KYC approvals (AUD-001).
2. Underpriced paid products and entitlements (AUD-002).
3. Payout before durable commit (AUD-003).
4. Concurrent duplicate payout (AUD-004).
5. Refunds not reversing benefits/commissions (AUD-005).
6. Manual withdrawal over-marking commissions (AUD-006).
7. Duplicate affiliate accrual without unique enforcement (AUD-007).
8. Conflicting vote stores and historical/current winner divergence (AUD-008).
9. Vote-limit concurrency and wrong ranking/promotion selection (AUD-009 through AUD-012).
10. Unknown active schema/Alembic/job/deployment state (AUD-016, AUD-017, AUD-022).

## Blockers Before Prompt 2

It is not safe to proceed to database migrations, payout/payment changes, vote data migration, legacy-table cleanup, or scheduler/deployment changes until all of the following are obtained read-only:

- SSH access or a restricted PostgreSQL read-only role/tunnel to Docker `kalutasociety_db`.
- The actual VPS `/opt/projects/kalutasociety/.env` variable **names/config state** (values may remain redacted), root compose file, image/commit IDs, and process/container list.
- Active outputs for PostgreSQL version/database size/schemas/extensions/tables/indexes, all PK/FK/unique/check/index definitions, exact important-table counts, duplicate financial/vote keys, and `alembic_version`.
- NOWPayments payout/event reconciliation data and confirmation of sandbox/live mode without exposing credentials.
- Confirmation whether Shufti is still active and the expected callback signature header/canonicalization.
- A product decision on canonical voting data and tie/month rules.

Frontend-only contract/mock fixes can be planned separately, but Prompt 2 must not assume this reference database represents production.

## Audit Method and Safety Record

- Enumerated source with ripgrep and read files at actual import/registration/call sites.
- Instantiated FastAPI with an in-memory SQLite URL and no lifespan to inspect registration only; no job or external action ran.
- Queried the reference PostgreSQL in a read-only transaction with a statement timeout; no write SQL was issued.
- Used safe HTTPS GET smoke probes against production. No authenticated mutation, POST to a provider, email, KYC initiation, payment, payout, upload, migration or blockchain call was made.
- Attempted batch-mode SSH only; authentication failed before any remote command ran.
- Preserved all pre-existing dirty-worktree changes. The only persistent audit artifact added is this report.

## Final Audit Status

The codebase audit is complete for the available checkout and the reference comparison is complete. The **active production database portion is incomplete by evidence**, because direct read-only access was unavailable. All affected conclusions are explicitly marked UNCONFIRMED rather than inferred from filenames, comments or the reference copy.

## Production Verification Addendum

**Verification date:** 2026-09-08 (Asia/Dhaka)  
**Scope:** Prompt 1B read-only production-blocker verification only. No migration, database mutation, container restart, provider call, payment, payout, KYC session, email, blockchain transaction, webhook, or environment change was performed.

### Access result and evidence boundary

- Live `GET /api/v1/build-info` returned build ID and Git SHA label `myhigh5-active-all-levels-20260818`.
- Live `GET /api/v1/health/db-schema` returned `ok=true`, database `kalutasociety_db`, user `kalutasociety_user`, and no missing `users` columns. This reconfirms application database identity only.
- Live `GET /api/v1/seasons/top-high5` reached the deployed ranking handler and returned its semantic 400 response requiring a country, confirming that this route is deployed.
- Read-only SSH to the documented VPS endpoint reached the SSH service but failed authentication: `Permission denied (publickey,password)`. The audit workstation has no Docker client and no accepted production SSH credential.
- Consequently, no command could be run inside `kalutasociety_postgres` or `kalutasociety_backend`. Facts requiring Docker, the active PostgreSQL catalogs, the live compose file, live process/container inspection, or live environment variables remain **UNCONFIRMED**. Reference database `mh5` results were not substituted.

### 1. Active database access and catalog

| Requested fact | Production result |
|---|---|
| `current_database(), current_user` | `kalutasociety_db`, `kalutasociety_user` — reconfirmed through the live health handler, **not** a direct Docker SQL session |
| PostgreSQL version | **UNCONFIRMED — Docker/SQL authentication unavailable** |
| Database size | **UNCONFIRMED — Docker/SQL authentication unavailable** |
| Total public tables | **UNCONFIRMED — Docker/SQL authentication unavailable** |
| Total indexes | **UNCONFIRMED — Docker/SQL authentication unavailable** |
| Extensions | **UNCONFIRMED — Docker/SQL authentication unavailable** |
| Schemas | **UNCONFIRMED — Docker/SQL authentication unavailable** |

### 2. Active database counts

No active row count or table-existence check could be executed. None of the following may be labelled present, empty, or `MISSING` from the available evidence:

| Table | Active result |
|---|---|
| `contest` | **UNCONFIRMED** |
| `contestants` | **UNCONFIRMED** |
| `contest_seasons` | **UNCONFIRMED** |
| `contest_stages` | **UNCONFIRMED** |
| `contest_entries` | **UNCONFIRMED**; note that the checkout's ORM name is singular `contest_entry`, but the active catalog was not inspected |
| `users` | Existence indirectly supported by the health schema check; row count **UNCONFIRMED** |
| `votes` | **UNCONFIRMED** |
| `page_views` | **UNCONFIRMED** |
| `contest_likes` | **UNCONFIRMED** |
| `contest_comments` | **UNCONFIRMED** |
| `contestant_reactions` | **UNCONFIRMED** |
| `contestant_shares` | **UNCONFIRMED** |
| `wallets` | **UNCONFIRMED**; note that the checkout's ORM name is singular `wallet`, but the active catalog was not inspected |
| `transactions` | **UNCONFIRMED** |
| `journal_entries` | **UNCONFIRMED** |

### 3. Active constraints and duplicate protection

Primary keys, unique constraints, foreign keys, checks, and indexes on votes, affiliate commissions, wallets, transactions, deposits/payment records, webhook/idempotency records, contest periods, rankings, and payouts are all **UNCONFIRMED in the active database**.

Repository declarations are not proof of deployed constraints. They show intended uniqueness for `contestant_voting(user_id, contestant_id, season_id)`, `transactions.reference`, `wallet.user_id`, `deposits.order_id`, and `user_vote_rankings(user_id, round_id, contestant_id)`. One unmerged repository head (`u4v5w6x7y8z9`) intends commission uniqueness by deposit and beneficiary. The repository does not declare uniqueness for NOWPayments external payment IDs or affiliate cashout payout references, and the MyHigh5 declaration does not enforce one position per bucket or a maximum of five rows. Because the active catalog and duplicate groups could not be queried, database-level protection against duplicate votes, commissions, payment/webhook processing, and payouts remains **UNCONFIRMED**.

### 4. Active Alembic state

```text
ACTIVE DB REVISION: UNCONFIRMED
REPOSITORY HEADS: c9d0e1f2a3b4, s3t4u5v6w7x8, u4v5w6x7y8z9
MISSING REVISIONS: UNCONFIRMED (active revision could not be read)
SAFE TO UPGRADE: NO
```

The repository heads were reconfirmed with read-only `alembic heads`. No Alembic upgrade or other migration command was run. Upgrade safety is `NO` because the repository still has three heads and the active stamp/catalog are unknown.

### 5. Running container topology

The status, image, health, and restart policy of `kalutasociety_backend`, `kalutasociety_frontend`, `kalutasociety_postgres`, `kalutasociety_redis`, any Celery worker, any Celery beat process, and any scheduler/worker container are **UNCONFIRMED** because Docker access was unavailable.

The checked-in `deploy/hostinger/docker-compose.yml` is not authoritative for the named production topology: it defines `kalutafoundation_*`, has no PostgreSQL service, sets `USE_CELERY=false`, and defines no Celery worker/beat. It therefore proves only that this repository compose file does not deploy Celery; it cannot prove what is running under `/opt/projects/kalutasociety`.

```text
CELERY WORKER RUNNING: UNCONFIRMED
CELERY BEAT/SCHEDULER RUNNING: UNCONFIRMED
```

### 6. Backend runtime environment

| Non-secret setting | Production result |
|---|---|
| Database host | **UNCONFIRMED** |
| Database name | `kalutasociety_db` — live-health confirmed |
| `ENVIRONMENT` | **UNCONFIRMED** |
| `DEBUG` | **UNCONFIRMED** |
| `USE_CELERY` | **UNCONFIRMED** |
| Redis host/port | **UNCONFIRMED** |
| `KYC_PROVIDER` | **UNCONFIRMED** |
| `NOWPAYMENTS_SANDBOX` | **UNCONFIRMED** |
| Frontend URL environment value | **UNCONFIRMED**; observed public site is `https://kalutasociety.com` |
| Backend public URL environment value | **UNCONFIRMED**; observed public API prefix is `https://kalutasociety.com/api/v1` |

No secret or secret-presence value was printed.

### 7. Payment mode and payout implementation

- **NOWPayments mode:** **UNCONFIRMED**. The checkout defaults `NOWPAYMENTS_SANDBOX=false` (live), but the running container value could not be read and the default is not production evidence.
- The payout API is implemented in `backend/app/services/nowpayments_service.py`: `send_payout_sync`, `send_payout`, `verify_payout_sync`, `verify_payout`, `send_single_payout_sync`, and `send_single_payout` call the provider's auth, payout, and verify endpoints. No provider function was invoked.
- Payout-initiating application paths in the checkout are:
  - automatic commission payout: `distribute_commissions` -> `process_commission_payouts_sync` -> `trigger_commission_payout_sync` -> `send_single_payout_sync`;
  - authenticated user withdrawal: `POST /api/v1/wallet/withdraw` -> `process_manual_withdrawal_sync`;
  - authenticated wallet save retry: `PATCH /api/v1/users/me/wallet` -> `pay_pending_commissions_for_user_sync`;
  - administrator retry: `POST /api/v1/admin/affiliate/retry-payouts` -> `retry_failed_payouts_sync`.
- Commit ordering is mixed and unsafe. The manual withdrawal, wallet-save retry, and admin retry call NOWPayments before committing payout state. The ordinary `commit=True` commission-distribution path commits commission accrual before the external payout, then commits paid status afterward. However, NOWPayments webhook/sync and admin validation use `defer_commit=True`, so their commission payout can occur before the outer transaction commits the deposit, commission, entitlement, and journal state.

### 8. Shufti and Kaluta KYC status

- **Shufti status:** **UNCONFIRMED in production**. Its repository role is **LEGACY**, selected only when `KYC_PROVIDER` normalizes to `shufti_pro`; its service is imported and `/api/v1/kyc/webhook/shufti-pro` remains registered regardless of selection.
- **Kaluta KYC status:** **UNCONFIRMED in production**. It is the repository default/primary provider, its service and `/api/v1/kyc/webhook/kaluta` are registered, and the frontend renders the Kaluta embed unless the initiation/status response identifies `shufti_pro`.
- Both webhook routes and both services exist in code. Current provider selection and credential/configuration presence cannot be established without the backend's non-secret runtime environment. No KYC session or callback was created.

### 9. Canonical voting dataset

The three stores are:

| Store/model | File | Registered/current API use | Frontend use | Reads/writes | Active rows and relationships |
|---|---|---|---|---|---|
| `votes` / `Vote` | `backend/app/models/voting.py` | Read by `/api/v1/analytics/dashboard` and some contestant/list statistics. Its CRUD write endpoints are in `endpoints/voting.py`, but that router is not registered in `api.py`. | No active vote submission page calls the unregistered voting router; the dashboard consumes derived analytics/list data. | Runtime reads exist; no registered new-vote write path was proven. | Active rows **UNCONFIRMED**. Links voter -> contestant -> contest stage; no direct contest/season/period key. |
| `contest_votes` / `ContestVote` | `backend/app/models/contest.py` | Registered `POST /api/v1/votes/{contest_id}` writes it; `GET /api/v1/votes/{contest_id}/my` reads it; legacy entry totals read it. | No live frontend caller was found; `vote-history` contains only a commented, nonmatching `/votes/my-history` call. | Registered API reads and writes exist, so direct API clients can create new rows. | Active rows **UNCONFIRMED**. Links user -> `contest_entry`; optional `round_id`; contest is indirect through the entry. |
| `contestant_voting` / `ContestantVoting` | `backend/app/models/voting.py` | Registered contestant vote/replace, MyHigh5 read/history/reorder, vote detail, contestant ranking/list, and `/api/v1/seasons/top-high5` paths use it. | Contest entry/detail/list cards submit votes; `/dashboard/myhigh5` reads/reorders; `/dashboard/top-high5` reads rankings. | Main current UI reads and writes it. | Active rows **UNCONFIRMED**. Direct user, contestant, contest, season, bucket, position, and points relationships. |

Strict runtime conclusions:

```text
A. NEW PRODUCTION VOTES: main web UI -> contestant_voting; registered legacy /votes API -> contest_votes
B. RANKING APIS: not singular; current contestant/TopHigh5 paths primarily use contestant_voting, while some analytics/list reads still use votes and legacy entry totals use contest_votes
C. TOPHIGH5: contestant_voting points plus contestant engagement metrics in the checked-out implementation
D. MYHIGH5: contestant_voting
E. LEGACY: votes is stage-history/legacy; contest_votes is a separate legacy entry-score API still registered
F. CROSS-STORE DUPLICATION: UNCONFIRMED; code does not deliberately dual-write a vote, but independent registered paths can represent overlapping logical votes
CANONICAL VOTE STORE = UNCONFIRMED
```

No single canonical production ledger can be proven because two registered endpoints can still accept new votes into different tables, ranking/analytics readers are split, active row counts and overlap queries are unavailable, and the exact deployed source cannot be inspected inside the running container. `contestant_voting` is the main UI and TopHigh5/MyHigh5 source in the checkout, but that does not by itself make the other registered write store non-production.

### 10. Implemented ranking rules

Repository behavior, not active-data validation:

- Main MyHigh5 votes are bucketed by contest category/type and season, with positions 1-5 worth 5-1 points. The API count check enforces five in application code, but the active database enforcement is unknown.
- TopHigh5 accepts a country, optional calendar `round_id`, and geography level. It resolves contests/seasons for that round/level and aggregates `contestant_voting.points` for the relevant season/bucket. A legacy contest-only vote fallback exists when strict season data is absent.
- Category separation uses `vote_bucket_key`, with compatibility matching for older null bucket keys.
- Candidate selection is capped before the full engagement ordering. Final ordering is points, shares, likes, comments, views, then lower contestant ID; this assigns deterministic ordinal positions rather than shared ranks for ties.
- The top five after that ordering are returned/materialized for the relevant contest/geography slice.
- Other leaderboard/list code is not fully aligned: some paths rank/count `contestant_voting`, some historical list/analytics paths count `votes`, and legacy entry totals use `contest_votes`.

### Prompt 2 gate after verification attempt

**PROMPT 2 REMAINS BLOCKED.** Required production evidence still missing:

1. Accepted read-only SSH/Docker access (or a restricted PostgreSQL role/tunnel) to `kalutasociety_postgres`.
2. Direct active catalog identity/version/size/schema/extension/table/index results and all requested table counts.
3. Active PK/FK/unique/check/index definitions plus duplicate-group checks for votes, commissions, payments/webhooks, and payouts.
4. Active `alembic_version`, allowing exact missing-revision comparison against the three repository heads.
5. Actual `/opt/projects/kalutasociety/docker-compose.yml`, container/process status, health, and restart policies, including Celery worker/beat or in-process scheduler topology.
6. Redacted non-secret backend runtime settings needed to establish Celery, Redis, NOWPayments live/sandbox mode, public URLs, and the selected KYC provider.
7. Active vote-store row counts and cross-store overlap profiling needed to declare and migrate a canonical voting ledger.

The failed authentication is an access blocker, not evidence that any table, constraint, container, worker, provider mode, or dataset is absent.
