# Native Advertising Platform Repair Report

Date: 2026-09-09  
Project: MyHigh5 / Kaluta Foundation  
Scope: Prompt 7, code changes plus low-impact read-only production analysis  
Implementation status: **PARTIAL**  
Deployment recommendation: **NO**

No deployment, container restart, Alembic command, schema mutation, production data write, provider payment, payout, refund, paid moderation call, impression, or click was performed.

## 1. Advertising architecture

Two materially different systems exist:

1. **AnnualAds (active integration):** `/dashboard/sponsored` embeds the provider campaign UI. `/api/v1/sponsor-embed/sso-token` issues an authenticated one-hour SSO JWT. The site-wide AnnualAds rotator loads provider inventory. `/api/v1/webhooks/sponsor-payment` verifies provider HMAC and posts confirmed net sponsor receipts to the Prompt 6 ledger.
2. **Internal native-ad domain (dormant):** SQLAlchemy models and production tables cover campaigns, creatives, placements, impressions, clicks, metrics, budget transactions, revenue shares, ad credits, blocklisted domains, and slot bookings. Its endpoint module was never registered, imports a nonexistent `crud_advertising`, and had incompatible request/model fields. It is not an active API.

Google AdSense is a third display-ad script in the root layout. It is not the native campaign source of truth and has no application-side campaign/event tables.

## 2. Active vs legacy systems

| System | Classification | Evidence |
|---|---|---|
| AnnualAds iframe/SSO/rotator | ACTIVE / CANONICAL for sponsor campaign operations | Registered backend SSO/webhook routes and active `/dashboard/sponsored` frontend |
| Prompt 6 journals | CANONICAL for AnnualAds receipts covered locally | Signed provider event posts balanced Dr 1030 / Cr 2310 |
| Internal `ad_*` schema | UNFINISHED / DORMANT | 11 domain tables exist, but all transactional tables are empty and router is unregistered |
| `ad_placements` | SERVER CONFIGURATION for dormant system | Eight populated price/placement rows |
| `ad_performance_metrics` | DERIVED, currently empty | Aggregate table with no active writer |
| `ad_revenue_shares` | UNFINISHED, currently empty | No canonical distribution/posting service |
| Google AdSense | ACTIVE THIRD-PARTY DISPLAY INTEGRATION | Script in root layout; no local financial/event source of truth |
| Static feed `Advertisement` component | UI PLACEHOLDER | It renders defaults and does not call an advertising API |

The dormant native router remains deliberately unregistered. Registering its previous client-priced budget/event endpoints would create a security and accounting regression.

## 3. Business/pricing model

Production configuration proves three intended native price models:

- CPC: server floor $0.02 for tier 1, $0.005 for tier 2, $0.002 worldwide on home/contest in-feed placements.
- CPM: server floor $0.25 for tier 1, $0.10 for tier 2, $0.05 worldwide on home/contest sidebars and profile recommended content.
- Fixed home header: $3 daily, $15 weekly, or $50 monthly.

All values are USD NUMERIC configuration. The active `ad_credit` product is variable-price (`price=0.00`) and has 10% direct plus 1% levels 2–10 commission rules. Because no order item, campaign-funding reference, quantity/unit-price record, minimum, or maximum exists, Prompt 6 correctly rejects this variable-price product. No one-to-one USD/ad-credit conversion was invented.

The new shared integrity code calculates CPC/CPM costs only from a server rate and Decimal units. CPA remains rejected because no authoritative CPA conversion definition exists.

## 4. Campaign lifecycle

The existing states are DRAFT, PENDING_APPROVAL, ACTIVE, PAUSED, COMPLETED, CANCELLED, plus production enum additions REJECTED and REMOVED. Shared lifecycle validation now permits only:

- DRAFT → PENDING_APPROVAL or CANCELLED;
- PENDING_APPROVAL → ACTIVE, REJECTED, or CANCELLED;
- ACTIVE → PAUSED, COMPLETED, CANCELLED, or REMOVED;
- PAUSED → ACTIVE, COMPLETED, CANCELLED, or REMOVED;
- terminal states do not reactivate.

Serving rules require ACTIVE, active and approved creative, schedule eligibility, and positive remaining budget. The dormant router is not activated because it has no authoritative payment gate or transition audit record.

## 5. Ownership/security

The original draft routes generally checked `campaign.advertiser_id`, but accepted raw dictionaries for budget, placement, impression, and click input. The repaired DTOs do not allow clients to set advertiser, status, spend, remaining balance, campaign ID on a creative, or event cost. Destination URL validation is centralized.

The active AnnualAds SSO endpoint requires an active authenticated user. Its response is now `Cache-Control: no-store, private` plus `Pragma: no-cache`. The embed does not expose internal campaign records. Native IDOR endpoints remain unreachable pending a complete CRUD/auth test surface.

## 6. Creative/media model

The dormant schema supports six enum formats: in-feed, native video, promoted trending, interactive, recommended content, and sponsored post. It stores title, description, content URL, CTA, landing URL, dimensions, file size, duration, policy state, policy result, rejection reasons, and link-scan time.

No internal creative upload endpoint is active. The previous draft accepted arbitrary URLs and did not reuse Prompt 4 media ownership/signature validation. It remains fail-closed. Before activation, `content_url` must reference Prompt 4 canonical owned media, with image/video signature, size, provider, and moderation validation; arbitrary HTML or JavaScript creatives must never be accepted.

The AnnualAds iframe is now sandboxed to forms/scripts/same-origin/popups and uses strict-origin-when-cross-origin referrers.

## 7. Placements

Production contains exactly eight active rows:

- contest/in_feed CPC;
- contest/sidebar CPM;
- home/header fixed daily, weekly, monthly;
- home/in_feed CPC;
- home/sidebar CPM;
- profile/recommended_content CPM.

No current MyHigh5 component calls a native serving endpoint, so there are no frontend identifier mismatches to reconcile. The AnnualAds rotator controls its own placement behavior externally.

## 8. Targeting

The dormant schema has generic, geographic, demographic, country, and geo-tier JSON/text fields. No registered API or frontend proves a supported targeting contract. It is classified UNFINISHED. Client-side qualification is not trusted. Audience/device/language targeting must not be advertised until server query semantics and privacy requirements are defined.

## 9. Scheduling

Native campaigns have start/end timestamps and fixed-slot bookings have explicit start/end timestamps. Shared validation rejects start greater than or equal to end, normalizes comparisons to UTC, and serving uses a half-open interval (`start <= now < end`). Production has zero invalid campaign dates because it has zero campaigns. Existing columns are timestamp-without-time-zone; `TIMESTAMPTZ` is recommended before activation.

## 10. Budget model

Campaigns store total budget, remaining budget, spend, optional daily budget, daily spend/date, and geographic bid tiers. Ad-credit accounts store balance/deposited/spent. Production has zero accounts and zero balance. All mapped monetary values and DTOs were changed from Python float annotations/defaults to Decimal.

The schema lacks CHECK constraints and a canonical link from funding to a validated payment/journal. Therefore native budget mutation and serving remain disabled. A future event writer must reserve spend with one conditional atomic UPDATE/row lock in the same transaction as the idempotent event, not SELECT-before-UPDATE.

## 11. Payment integration

AnnualAds owns its campaign checkout. A signed confirmed-payment event records only the net MyHigh5 receipt as deferred sponsor revenue via the Prompt 6 accounting service; no wallet field is mutated and no provider is called by the webhook.

Internal `ad_credit` cannot use the canonical fixed-price checkout because its server product price is zero and there is no authoritative order/quantity model. It remains unavailable. Activation must eventually require: durable canonical payment intent → validated deposit → balanced ledger post → ad-credit funding reference → campaign reservation/activation.

## 12. Affiliate integration

Production confirms `ad_credit` is commissionable at 10% direct and 1% for levels 2–10. No ad-credit deposits, accounts, commissions, or AnnualAds journals exist. No new commission engine was created. A future internal purchase must call Prompt 6 `commission_distribution` exactly once from a validated deposit and use its existing `(deposit_id,user_id)` duplicate protection. Provider campaign delivery revenue sharing is not equivalent to purchase commission and must not be inferred.

## 13. Impression tracking

The dormant table records campaign, creative, placement, optional user, page URL/type, IP address, user agent, cost, country, geo tier, and timestamp. Production contains zero impressions. The prior raw endpoint trusted creative/placement/user/metadata, had no delivery token, eligibility recheck, duplicate policy, or atomic spend reservation. It remains unavailable. A future implementation should store a short-lived signed delivery token and a unique event key, minimize IP data (prefer keyed short-retention hash), classify duplicate/suspicious/invalid events, and calculate CPM from server placement price.

## 14. Click tracking

Clicks are one-to-one with impressions at the database level (`UNIQUE(impression_id)`), which prevents more than one billable click per impression. Production contains zero clicks. The draft click endpoint did not receive an impression ID, could not safely correlate the served creative, and offered no safe redirect contract. It remains unavailable. Future clicks must consume a valid impression/delivery token and return or redirect only to the already validated creative destination.

## 15. Fraud/duplicate protection

Implemented now: URL SSRF/open-redirect scheme/host guard, blocklist support in the shared validator, one-click-per-impression production constraint, HMAC compare-digest, five-minute AnnualAds timestamp window, tenant matching when supplied, per-provider-transaction PostgreSQL advisory lock, sequential replay lookup, no-cache SSO token, and consent gating.

Still required before native activation: unique impression/click provider event keys, signed delivery tokens, bounded replay window, rate limiting, IP/user/session duplicate classification, and atomic event/spend transaction. No invasive fingerprinting was added.

## 16. Spend calculation

Shared server-side CPC and CPM calculations use Decimal. CPC is rate × validated clicks. CPM is rate × validated impressions / 1000. CPA fails closed. Fixed pricing comes directly from placement rows. Frontend-supplied cost, spend, commission, and remaining balance were removed from input DTOs. No production spend was calculated or changed.

## 17. Concurrency

AnnualAds identical confirmed events are serialized with a PostgreSQL advisory transaction lock before the existing-entry check/post. Sequential replay returns `already_recorded`. A dedicated unique provider-event constraint is still required for final enforcement and cross-event lifecycle tracking.

Native concurrent delivery remains blocked rather than relying on unsafe application checks. Required transaction semantics are conditional budget decrement plus event insert under one idempotency key. Production already has useful impression `(creative_id,timestamp)` and `(ip_address,timestamp)` indexes, but no unique delivery event.

## 18. Campaign completion

The deterministic terminal rules are defined and tested: end time, zero balance, or an authorized terminal action makes a campaign non-servable; terminal states cannot resume. No active writer currently advances dormant campaign state, so scheduled completion infrastructure remains required before activation.

## 19. Refund/cancellation

No verified AnnualAds refund event contract exists. Previously any unknown event, including refund-like events, was acknowledged as successful and silently ignored. Refund/reversal/cancellation/chargeback event names now fail closed with HTTP 409 so they are not falsely recorded as applied. Once provider payload semantics are documented, the handler must invoke Prompt 6 compensating journal/commission reversal behavior and retain immutable history.

Native cancellation/refund eligibility is not defined and was not invented. Internal campaign payment remains disabled.

## 20. Ad serving

AnnualAds serves through its remote rotator. It now loads only after explicit advertising consent. The provider URL must be a safe HTTPS URL in production, and `postMessage` targets the actual iframe origin rather than an unrelated configurable wildcard/origin.

The internal selector remains unavailable. Shared eligibility rules are ready, but a production selector must filter in SQL by status, moderation, schedule, budget, exact placement, and supported targeting; bound the result; and use a documented provider/product rotation policy. No random/weighted commercial policy was invented.

## 21. Reporting

AnnualAds campaign reporting is provider-owned inside the embed and was not available for passive database verification. Locally, only balanced sponsor receipt journals exist as the accounting authority. Production contains zero such receipts. The empty internal `ad_performance_metrics` table is derived/non-authoritative; future reporting must aggregate canonical events and budget transactions in SQL, paginate history, and calculate CTR as validated clicks / validated impressions.

## 22. Admin controls

There are no registered MyHigh5 native-ad admin routes or screens. AnnualAds moderation/admin operations are provider-owned. No state-changing GET route was added. A native rollout requires admin-only approve/reject/remove/pause actions with actor, reason, old/new state, timestamp, creative policy result, and immutable audit reference.

## 23. Performance

The active third-party scripts remain lazy, and now do not download at all without advertising consent. The SSO endpoint performs no DB aggregation or external call. The webhook performs indexed account/description lookups and one small journal post. Production native event tables are empty.

Future native serving should be one bounded indexed eligibility query, not load-all/Python filtering. Reporting should aggregate in PostgreSQL with date bounds and pagination. Recommended indexes are listed below; none were applied.

## 24. Production data audit

The read-only tool enforced PostgreSQL, `SET TRANSACTION READ ONLY`, 8-second statement timeout, 1-second lock timeout, SELECT/catalog queries only, and unconditional rollback.

- `ad_campaigns`: 0; active/pending/completed/rejected: 0; owner/pricing/creative/date/overspend anomalies: 0.
- `ad_creatives`: 0; invalid URL/owner anomalies: 0.
- `ad_placements`: 8 active; all mapped to the six page/position combinations documented above.
- `ad_impressions`, `ad_clicks`, `ad_performance_metrics`: 0; duplicate/orphan groups: 0.
- `ad_credit_accounts`: 0, $0 balance/deposited/spent, 0 reconciliation mismatches.
- `ad_budget_transactions`, `ad_slot_bookings`, `ad_revenue_shares`, `ad_domain_blocklist`: 0.
- AnnualAds journal entries: 0, amount $0, duplicate transaction descriptions: 0.
- The production native enum types contain duplicate uppercase/lowercase labels from historical schema evolution. No rows currently exercise the ambiguity.

## 25. Files changed

Prompt 7 files:

- `backend/app/api/api_v1/endpoints/sponsor_annualads.py`
- `backend/app/models/advertising.py`
- `backend/app/schemas/advertising.py`
- `backend/app/services/advertising_integrity.py` (new)
- `backend/scripts/analyze_advertising_production_readonly.py` (new)
- `backend/tests/unit/test_advertising_integrity.py` (new)
- `backend/tests/unit/test_financial_integrity.py`
- `frontend/app/dashboard/sponsored/page.tsx`
- `frontend/app/layout.tsx`
- `frontend/components/annualads-partner-rotator.tsx`
- `frontend/components/annualads-partner-rotator.test.tsx` (new)
- `frontend/components/ui/cookie-consent.tsx`
- `frontend/lib/config.ts`
- `NATIVE_ADVERTISING_REPAIR_REPORT.md` (new)

All other dirty worktree changes belong to Prompts 2–6 and were preserved.

## 26. Tests

- Focused backend advertising/financial verification: 34 passed, 0 failed.
- Full backend: 278 passed, 0 failed, 2 skipped. Skips are the existing opt-in live-PostgreSQL accounting tests; they were not run against production.
- Full frontend: 66 passed, 0 failed across 16 files.
- Next.js production build: PASS; compiled and generated 88/88 static pages. The project build configuration explicitly skips type validation and linting.
- Prompt 2 voting/ranking regression suite: PASS.
- Prompt 3 lifecycle/historical attribution regression suite: PASS.
- Prompt 4 category/media regression suite: PASS.
- Prompt 5 performance regression suite: PASS.
- Prompt 6 financial regression suite: PASS.

Coverage includes ownership field exclusion, fail-closed router registration, lifecycle, dates, Decimal pricing, serving gates, unsafe URL classes, domain blocking, consent gating, SSO authentication/cache control, HMAC, stale/signature/tenant failures, replay, amount/network validation, and unsupported reversal behavior. Provider operations were mocked or not called.

## 27. Schema recommendations

**REQUIRED FOR CORRECTNESS (do not apply until Alembic reconciliation):**

1. Provider event table with `UNIQUE(provider,event_id)` or normalized provider transaction/event type, payload hash, received/applied state, and journal/reversal links.
2. Native funding/order relation tying campaign/ad-credit funding to canonical `deposits`, order item, currency, quantity, server unit price, and journal entry; unique idempotency key.
3. Native billable-event/delivery token with unique event key; atomic event insertion and budget reservation.
4. CHECK constraints for total/daily/remaining/spent nonnegative values and coherent budget equation; currency/asset columns on ad credit and budget records.
5. Moderation/transition audit records with actor, reason, old/new state, timestamps, and creative version.

**RECOMMENDED:**

1. Normalize historical duplicate uppercase/lowercase PostgreSQL enum labels after row/value audit.
2. `TIMESTAMPTZ` for campaign, booking, event, moderation, and accounting boundaries.
3. Unique placement identity `(page_type,position,cost_model,flat_period)` where business rules confirm uniqueness.
4. Indexes for serving on campaign `(status,start_date,end_date)` with remaining-budget predicate; creative `(campaign_id,is_active,policy_status)`; booking `(placement_id,is_active,starts_at,ends_at)`; impressions `(campaign_id,timestamp)`; clicks `(timestamp)`; budget transaction `(campaign_id,created_at)` and unique non-null funding reference.
5. Canonical category-target relation to `categories.id` rather than unverifiable JSON/legacy labels.

**OPTIONAL HARDENING:** short-retention keyed event hashes, aggregate rollup partitioning after real volume justifies it, and cached placement configuration with explicit invalidation. Correctness must never depend on cache availability.

## 28. Remaining risks

1. AnnualAds provider campaign lifecycle, pricing, moderation, impression/click fraud, placement selection, reporting, cancellation, and refund contracts cannot be verified from the MyHigh5 repository or empty local mirror.
2. Provider reversal events have no documented payload mapping; they now fail closed but are not applied.
3. The internal native engine has no canonical funding relation, order items, unique event keys, transition audit, or complete Prompt 4 media integration and therefore remains disabled.
4. The populated server placement pricing and `ad_credit` commission rule are ahead of the repository Alembic graph and must be reconciled later.
5. Application advisory locking plus description lookup protects AnnualAds replay operationally but is not a substitute for a database unique provider-event key.
6. AdSense and AnnualAds consent gating is application-side; legal/privacy policy review and provider consent-mode configuration remain external requirements.
7. The unresolved Prompt 6 plural-wallet $2,441 provenance and $2 commission/payable gap remain untouched and must not be used to fund ads.

## 29. Deployment recommendation

**NO.** The integration hardening and tests are suitable for review, but the overall Prompt 7 objective is PARTIAL. Deploy only after Prompts 2–7 are approved together, the AnnualAds reversal/reporting/moderation contract is verified, required event/payment schema is reconciled safely, and a product decision is made whether the empty internal native platform should be completed or formally retired. Do not enable `advertising.router` in its current generation.
