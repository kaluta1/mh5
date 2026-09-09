# Performance & 504 Repair Report

Date: 2026-09-09  
Scope: Prompt 5 only; code, local tests, configuration inspection, and low-impact production reads  
Status: **PARTIAL**  
Production deployment/data/schema changes: **none**

The code-level causes and database plans behind the highest-risk timeouts were found and repaired. The status remains PARTIAL because production proxy/application logs and VPS CPU/RAM metrics were not available, several filtered contest-card paths still require data-dependent enrichment, and the recommended production indexes cannot be applied while the Alembic graph is divergent.

## 1. Performance baseline

Application thresholds used:

| Class | Server response | SQL/select behavior |
|---|---:|---|
| FAST | <150 ms | small constant query count |
| ACCEPTABLE | 150–500 ms | bounded/indexed work |
| SLOW | 500–2,000 ms | repeated round trips or material scans |
| CRITICAL | >2,000 ms or timeout | N+1, unbounded response, full high-volume scan, or external wait |

Production was inspected only with catalog/statistics SELECTs and `EXPLAIN (FORMAT JSON)`—never `EXPLAIN ANALYZE`. Reliable production endpoint latency was not measured because issuing repeated requests would violate the low-impact requirement. PostgreSQL `pg_stat_user_tables` confirmed the important scale, including 504,629 `page_views` rows (93 MB), 86,345 `votes` rows (23 MB), 78,533 `contest_likes`, 52,821 reactions, 23,522 shares, and 18,975 legacy comments. Catalog live-row estimates for some small tables differed from the supplied exact inventory and are not treated as authoritative counts.

| Active path | Baseline classification | Main reason | Post-repair assessment |
|---|---|---|---|
| Homepage / public contest list | CRITICAL | 2 count queries plus full enrichment per contest | ACCEPTABLE for the default, unfiltered path; 4 SELECTs measured for 12 cards |
| Round/contest listing | SLOW | nested contest payload and formerly unbounded limits | bounded at round and nested-contest levels |
| Contest detail | SLOW/data-dependent | complex roster/context resolution | unchanged where correctness-sensitive; bounded contestant pagination already present |
| Contestants | ACCEPTABLE | active routes already capped at 100 | preserved |
| Ranking | CRITICAL | historical scan plus repeated engagement scans | aggregation remains canonical; engagement is one SQL round trip; indexes still required |
| TopHigh5 | CRITICAL | per-contest link N+1, duplicate ranking work, 5-second polling | major N+1/dead work removed; browser polling reduced/coalesced |
| MyHigh5 | ACCEPTABLE | scoped write/read queries | canonical service preserved; no alternate ranking engine |
| Profile | ACCEPTABLE/data-dependent | bounded lists; relationship loading varies | no contract change |
| Media | SLOW on missing S3 objects | fresh clients and unbounded provider waits | shared bounded S3 client; blocking upload work offloaded |
| Categories | FAST | small stable table but repeatedly fetched | 5-minute Redis cache with explicit mutation invalidation |
| Search | ACCEPTABLE today / SLOW at scale | `%term%` scans and relationship N+1 | eager loading repaired; index recommendation retained |
| Admin dashboard | SLOW/CRITICAL | unbounded lists, async routes with sync ORM, reports/users N+1 | list caps, threadpool routing, and batched counts/lookups added |

Response-size timing was not fabricated. The contest-list response contract and fields are unchanged, so its response size is materially unchanged; its database work is what improved.

## 2. 504 root causes

No historical Nginx/Apache error log was present in the workspace, so a specific past 504 request ID cannot be attributed. The following causes are directly confirmed by source inspection and PostgreSQL plans:

1. TopHigh5 performed up to four contest-season link queries per contest, then ran a legacy points/engagement ranking pass that was immediately overwritten by `VotingRankingService` output.
2. Public contest cards ran at least two count queries per contest and then called the full data-dependent enrichment routine per contest. For 12 cards, the batch section alone required at least 26 SELECTs before enrichment.
3. Engagement ranking queried six large tables separately. The production `page_views` plan was a parallel sequential scan of all 504,629 rows with estimated cost 14,920.
4. Historical ranking scanned all 86,345 `votes` rows because the available single-column indexes do not match stage/status/contestant aggregation; estimated plan cost was 2,868.
5. Production inspection found two client sessions `idle in transaction`, waiting on `ClientRead`, aged about 1,057 and 1,402 seconds. Their originating process could not be proven from safe metadata, but they can retain pooled connections/snapshots.
6. Many admin handlers were declared async while doing synchronous ORM/CPU work, allowing event-loop blockage on the single Uvicorn worker.
7. TopHigh5 polling generated 12 expensive calls/minute/open tab and focus/visibility could overlap requests. Identical concurrent requests also recomputed the same leaderboard independently.
8. Redis and S3 clients lacked sufficiently tight connect/read bounds; Redis invalidation used blocking `KEYS`.

Proxy timeouts are symptoms, not the repair: Nginx and Apache allow 120 seconds, far beyond the frontend TopHigh5 8-second bound and database 20-second statement bound.

## 3. Slow endpoint inventory

- Critical: `GET /api/v1/seasons/top-high5`, public contest list before repair, ranking paths touching historical votes/engagement, admin all-users/contestants/reports before repair.
- Slow/data-dependent: geographically filtered contest cards, contest detail/roster resolution, wildcard search, admin statistics and export routes.
- Acceptable/bounded: MyHigh5 writes/history, comments, favorites, public contestants, media list, users/search subroutes.
- Fast: liveness `/health`, build-info, cached category list.

## 4. SQL query analysis

- Production contest-list SQL itself uses an ID index and LIMIT; its problem was application-generated follow-up queries.
- Current contextual ranking currently has little/no production data but is indexed on season and contestant; a future composite index is documented below.
- Historical ranking uses a sequential scan over `votes`; `contest_stages` also lacks a season index.
- Page-view period aggregation uses a parallel sequential scan over the 93 MB table.
- Contest wildcard search still uses a sequential scan because only name has a trigram index and the OR includes unindexed description.
- No heavy production `EXPLAIN ANALYZE`, load test, COUNT benchmark, or write statement was run.

## 5. N+1 findings

Repaired:

- TopHigh5 contest-season links are fetched once and indexed in memory by `(contest, level, active)`.
- TopHigh5 category and contestant-user relationships are eager-loaded.
- Dead pre-ranking points and six-table engagement calls were removed from both the endpoint and the location-ranking service.
- Default contest-card counts are grouped for all requested contests rather than counted twice per contest; authenticated entry-round lookup reuses the batched contestant fetch.
- Search eagerly loads contest location and contestant user.
- Admin report contestant/author/reporter/contest lookups are batched.
- Admin user participation and contest-entry counts are grouped instead of two counts/user.

Remaining: geography/round-filtered contest cards retain correctness-heavy per-contest roster enrichment. This needs a dedicated batched roster API before it can safely be removed.

## 6. Ranking performance

`VotingRankingService`/`aggregate_rankings` remains the only canonical ranking engine. PostgreSQL still performs SUM/COUNT/GROUP BY; raw vote ledgers are not loaded into Python. Deterministic order, category bucket, season/stage isolation, exact historical attribution, and fail-closed ambiguous history are unchanged. TopHigh5 now removes at least ten redundant queries per rendered contest/group in common paths, before counting avoided lazy-user loads. Recommended indexes are still needed for production-scale historical aggregation.

Identical TopHigh5 requests within one backend process now use a short-lived single-flight entry keyed by round, normalized country, and level. Followers reuse the leader's result, receive the same no-cache response headers, and fail open after 12 seconds if the leader stalls. This coalesces work without storing ranking data or making correctness depend on Redis.

## 7. Engagement performance

Six grouped queries (shares, likes, positive reactions, legacy comments, current comments, views) were replaced with one `UNION ALL` aggregate. A new test proves all metrics and exactly one SQL SELECT. Time-window fail-closed behavior remains: without an explicit validated period, engagement is neutral rather than lifetime-contaminated.

## 8. Pagination

Added/strengthened bounds:

- Public contests: default 12, max 100; CRUD defense-in-depth also max 100.
- Rounds: default 24, max 100; nested contests max 100.
- Media, voting history, stage leaderboard, and users: max 100.
- Admin reports/suggestions/transactions: max 100.
- Admin contests/users: capped at 500 to preserve the current array contract; contestants capped at 1,000 to preserve the current production-scale admin view.
- Search and comments were already capped at 100.

Admin endpoints continue returning arrays for compatibility. Long-term cursor pagination is recommended for admin screens and histories; current OFFSET pagination remains acceptable at present scale but is not ideal for deep pages.

## 9. Response payload optimization

The public contest list already returns a lightweight card dictionary and omits vote histories/top contestants. This contract was preserved. No active frontend field was removed without usage proof. The largest remaining payload risk is the legacy admin “all” array contract and nested round payloads; both now have hard caps.

## 10. DB connection analysis

Application engine: `pool_size=10`, `max_overflow=20`, `pool_timeout=10s`, `pool_recycle=300s`, `pool_pre_ping=true`, connect timeout 10s, statement timeout 20s. `get_db()` closes in `finally`. With the configured one worker, theoretical maximum is 30 database connections.

Neon pooled endpoints can reject libpq startup `options`; statement timeout is now installed in the connect event and the setup transaction is committed before pooling. A real read-only connection through the application engine succeeded and returned `statement_timeout=20s`.

Two long idle transactions were observed in production. No terminating action was taken. Source identity remains a deployment/observability follow-up.

## 11. Sync/async findings

- Read-heavy admin endpoints that use synchronous SQLAlchemy/CPU work are now ordinary `def` routes, so FastAPI executes them in its worker threadpool.
- Image validation and S3 uploads in async media routes use `run_in_threadpool`.
- Payment-provider waits no longer retain a SQLAlchemy read transaction; deposits are reloaded/locked only for local finalization.
- A full architecture conversion was deliberately avoided.

## 12. External API timeout analysis

- NOWPayments: existing calls remain bounded (15–60s depending on operation); transaction boundary repaired.
- Kaluta KYC/device-location: existing httpx bounds retained (5–30s).
- Shufti: 5s connect, 20s socket read, 30s total.
- Sightengine/content relevance: explicit `(connect, read)` request timeouts, 5/15–30s.
- S3: 3s connect, 10s read, two attempts, shared 10-connection pool.
- Next server routes: link preview/oEmbed 6–8s, moderation 30s, upload auth 10s, translation 30s, scheduler proxy 55s; TikTok already had 6–12s bounds.
- Redis: 1s connect/read, no timeout retry loop.
- No paid provider, payment, payout, KYC, blockchain, or production email call was made.

## 13. Cache strategy

Redis remains optional and fail-soft. Categories use a scoped `active` key, 300-second TTL, and explicit create/update/delete invalidation. Ranking correctness does not depend on cache. Blocking `KEYS` invalidation was replaced with SCAN and delete batches of 200. Frontend TopHigh5 uses a 30-second view cache and request single-flight; vote-change still triggers refresh. The backend adds process-local single-flight for identical simultaneous ranking requests but deliberately does not cache a stale leaderboard. Redis-unavailable fallback, hit behavior, mutation invalidation, bounded scan batches, and concurrent backend coalescing are tested.

## 14. Frontend performance

- Concurrent identical TopHigh5 calls share one in-flight promise.
- The cache-busting timestamp was removed, allowing request coalescing.
- Background polling changed from 5 seconds to 15 seconds and skips focus/visibility refreshes inside the same 15-second freshness window: 12 to 4 scheduled requests/minute/tab (66.7% fewer).
- Main Axios clients remain bounded at 30 seconds; the formerly documented zero-timeout config is now 30 seconds.
- Production build: 88 pages generated. `/dashboard/top-high5` is 8.13 kB route code / 181 kB first load; `/contests` is 13.7 kB / 248 kB. The admin root remains large at 124 kB / 277 kB and is a future bundle-splitting candidate.

## 15. Media performance

S3 clients are reused instead of recreated for every head/get/put, with bounded connect/read time and retries. Async uploads offload synchronous validation/S3 I/O. Local files retain 24-hour cache headers. No historical media rewrite or remote cleanup occurred. Missing legacy S3 objects now fail within bounded provider time rather than waiting on botocore defaults.

## 16. Search performance

Search result counts are bounded and related location/user rows are eager-loaded. `%term%` search remains database-side. Production has a trigram index on contest name and user names but the contest `name OR description` plan still sequential-scans the small 196-row table. At current scale this is acceptable; a description trigram index is optional if the table grows.

## 17. Index recommendations

No index was applied.

| Priority | Proposed index | Query helped / current plan | Expected benefit | Write/size consideration |
|---|---|---|---|---|
| REQUIRED | `page_views(contestant_id, viewed_at)` | period engagement; parallel seq scan of 504,629 rows, cost ~14,920 | selective contestant/time scans and faster GROUP BY | extra index write per view; likely tens of MB on 93 MB table |
| REQUIRED | partial `votes(stage_id, contestant_id) INCLUDE (points) WHERE status='ACTIVE'` | historical ranking scans 86,345 rows, cost ~2,868 | stage-scoped index(-only) aggregation | vote insert/status write cost; several MB |
| REQUIRED | `contest_stages(season_id, id)` | season-to-stage join currently scans stage table | direct stage lookup for ranking | very small index/write cost |
| RECOMMENDED | `contest_likes(contestant_id, created_at)` | timed likes aggregation lacks contestant index | selective aggregation | modest size/write cost |
| RECOMMENDED | partial reaction index `(contestant_id, created_at) WHERE reaction_type IN ('like','love','wow')` | positive reaction ranking | avoids scanning negative/unrelated reactions | predicate maintenance; modest size |
| RECOMMENDED | `contestant_shares(contestant_id, created_at)` | timed share aggregation lacks index | selective aggregation | modest size/write cost |
| RECOMMENDED | `contest_comments(contestant_id, created_at)` | existing contestant-only index cannot fully serve period | time-bound aggregation | modest extra index |
| RECOMMENDED | partial `comment(contestant_id, created_at) WHERE NOT is_hidden AND NOT is_deleted` | visible current comments | filtered period aggregation | currently tiny; low cost |
| RECOMMENDED | `contestant_voting(season_id, contest_id, contestant_id) INCLUDE(points, vote_bucket_key)` or workload-refined equivalent | future contextual ranking growth | fewer bitmap/index joins | do not add until real row distribution is reviewed |
| RECOMMENDED | `contest_season_links(contest_id, is_active, season_id)` | frequent active link resolution; 651k historical index scans | narrower active lookup | table/index small |
| OPTIONAL | trigram `contest(description)` | wildcard contest search OR forces seq scan | useful only as contest table grows | GIN write/storage cost |

## 18. Transaction analysis

NOWPayments create/sync paths now release local read transactions before external awaits. The provider result is applied in a fresh transaction, using row locking for sync finalization. Voting/financial atomicity was not weakened. Production still showed two anonymous long idle transactions; determine their client/source before deployment and add transaction-age alerting.

## 19. Nginx findings

Nginx: connect 10s, read/send 120s, next-upstream total 15s/two tries. Apache: 120s for API/media/GraphQL/frontend. Proxy buffering is enabled for frontend, immutable caching exists for `/_next`, HTTP/1.1 keepalive headers are configured. No timeout was increased. Compression is not explicitly configured in the supplied snippet and should be verified at the host-level configuration. Retrying non-idempotent API requests on timeout is a risk; split GET retry policy from mutation routes in a later deployment change.

## 20. Container findings

Hostinger compose uses restart policies and cheap backend/Redis health checks. Backend health is a constant in-process liveness response and performs no DB/external calls. Frontend has no explicit healthcheck. Production Dockerfile starts one Uvicorn worker without an explicit concurrency cap; this avoids multiplying the 30-connection pool but is a single-process availability bottleneck. VPS CPU/RAM metrics were unavailable, so worker count was not changed. Before increasing workers, reduce each worker’s pool or establish the Neon connection budget.

## 21. Before/after benchmarks

| Path | Before | After | Improvement |
|---|---|---|---|
| Public 12-contest default list | at least 26 SELECTs before full enrichment | exactly 4 SELECTs in isolated endpoint test | at least 84.6% fewer queries |
| Engagement for one candidate set | 6 SQL round trips | exactly 1 | 83.3% fewer round trips |
| TopHigh5 | at least 10 redundant queries per rendered contest/group plus lazy users | those redundant queries removed; link lookup is one per round | data-dependent; no fabricated wall time |
| Concurrent identical TopHigh5 calls in one backend process | one full calculation per caller | one leader calculation shared by followers | burst-dependent; exact one-call behavior proven by a two-thread test |
| Admin reports | 1 + up to 4N SELECTs | at most 4 data SELECTs for a page | O(N) to O(1) query count |
| TopHigh5 scheduled browser calls | 12/minute/tab | 4/minute/tab | 66.7% fewer |

Wall-clock before/after on production was intentionally not measured. Local test-process duration includes application startup and is not an endpoint benchmark.

## 22. Files changed

Prompt 5 changes:

- `backend/app/api/api_v1/endpoints/admin.py`
- `backend/app/api/api_v1/endpoints/categories.py`
- `backend/app/api/api_v1/endpoints/contests.py`
- `backend/app/api/api_v1/endpoints/media.py`
- `backend/app/api/api_v1/endpoints/payments.py`
- `backend/app/api/api_v1/endpoints/rounds.py`
- `backend/app/api/api_v1/endpoints/search.py`
- `backend/app/api/api_v1/endpoints/season_migration.py`
- `backend/app/api/api_v1/endpoints/users.py`
- `backend/app/api/api_v1/endpoints/voting.py`
- `backend/app/core/cache.py`
- `backend/app/core/storage.py`
- `backend/app/crud/crud_contest.py`
- `backend/app/db/session.py`
- `backend/app/services/content_moderation.py`
- `backend/app/services/content_relevance.py`
- `backend/app/services/feed_aws_s3.py`
- `backend/app/services/nowpayments_service.py`
- `backend/app/services/season_migration.py`
- `backend/app/services/shufti_pro.py`
- `backend/app/services/voting_ranking.py`
- `backend/scripts/analyze_performance_production_readonly.py`
- `backend/tests/unit/test_performance_guards.py`
- `backend/tests/unit/test_voting_ranking.py`
- `frontend/app/api/cron/[task]/route.ts`
- `frontend/app/api/i18n/translate/route.ts`
- `frontend/app/api/link-preview/route.ts`
- `frontend/app/api/upload/moderated/route.ts`
- `frontend/app/api/uploadthing/core.ts`
- `frontend/app/dashboard/top-high5/page.tsx`
- `frontend/lib/config.ts`
- `frontend/services/contest-service.performance.test.ts`
- `frontend/services/contest-service.ts`
- `PERFORMANCE_504_REPAIR_REPORT.md`
- `worktree_checkpoints/prompt5-prechange-20260909.zip`

The worktree also contains unapproved Prompt 2–4 changes; they were preserved and not deployed.

## 23. Tests

- Backend: **239 passed, 2 skipped**. The skips require explicitly enabled live-PostgreSQL accounting tests; no failure.
- Frontend: **64 passed** across 15 files.
- New guards cover constant contest-list query count, one-query engagement aggregation, pagination rejection, Redis unavailable fallback, bounded SCAN batching, category cache hit/invalidation, concurrent frontend request coalescing, and concurrent backend single-flight behavior including follower response headers.
- Prompt 2 voting/ranking regression: PASS.
- Prompt 3 contest-context/lifecycle regression: PASS.
- Prompt 4 category/media regression: PASS.
- Next production build: PASS, 88/88 pages generated.
- Standalone `tsc`: not a valid gate in this checkout because installed TypeScript 5.9 rejects the pre-existing TS6-era `ignoreDeprecations` value. Next’s configured production build passes and explicitly skips type validation.

## 24. Schema recommendations

The indexes in section 17 are schema changes and therefore require a later, reviewed migration after Alembic reconciliation. No migration file, DDL, Alembic command, or stamp was created/run here.

## 25. Remaining performance risks

1. Required high-volume indexes are absent; page-view and historical-vote scans remain production risks.
2. Two long idle-in-transaction sessions require source attribution and monitoring.
3. Geography/round-filtered contest card counts still use per-contest contextual resolution.
4. TopHigh5 remains a broad all-category response and should eventually support category pagination/selection without changing ranking semantics. Its single-flight protection is process-local; multiple Uvicorn workers would require a carefully scoped distributed lock to coalesce across processes.
5. Admin array endpoints are capped but not cursor-paginated; UI pagination is future work.
6. One backend worker is both a bottleneck and a protection against multiplying DB pools; resource metrics are needed before changing it.
7. Host-level compression/resource limits and actual Nginx/Apache error logs were unavailable.
8. Direct browser `fetch` calls outside the main Axios client are not yet uniformly routed through one shared timeout helper.
9. Backend distributed ranking-cache stampede prevention was not added because cross-worker correctness/invalidation was not sufficiently established; frontend in-tab single-flight is implemented.
10. Prompt 2–4 changes remain unapproved, Alembic remains divergent, and historical contest attribution remains fail-closed/ambiguous as required.

## 26. Deployment recommendation

**NO.** Do not deploy this work independently while Prompts 2–4 are unapproved and the migration graph is divergent. Before a controlled deployment: review the combined diff, reconcile Alembic separately, apply approved indexes through a safe migration window, identify idle transaction clients, capture real proxy slow-request logs, and validate the candidate build on staging with production-like data. No production service was restarted.
