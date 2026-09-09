# Voting and Ranking Repair Report

Date: 2026-09-08  
Repository: `kalutafoundation`  
Production database inspected read-only: Neon PostgreSQL `neondb`

## 1. Pre-change architecture

The deployed application had three mutually inconsistent voting flows.

| Frontend / caller | API | Backend path | Pre-change store |
|---|---|---|---|
| contest pages and vote buttons | `POST /api/v1/contestants/{contestant_id}/vote` | `backend/app/api/api_v1/endpoints/contestant.py` | `contestant_voting` |
| replacement confirmation | `POST /api/v1/contestants/{contestant_id}/vote/replace` | `backend/app/api/api_v1/endpoints/contestant.py` | `contestant_voting` |
| MyHigh5 page and panel | `GET /api/v1/contestants/user/my-votes`, `/history`, and `PUT /reorder` | `contestant.py` | `contestant_voting` |
| TopHigh5 page | `GET /api/v1/seasons/top-high5` | `endpoints/season_migration.py` and `services/season_migration.py` | `contestant_voting` |
| old contest-entry client/API | `POST /api/v1/votes/{contest_id}` | `endpoints/votes.py` | `contest_votes` |
| unregistered stage-voting API | `/voting/cast`, update, delete, leaderboards | `endpoints/voting.py`, `crud/crud_voting.py` | `votes`, but against fields that do not match the live model |
| contestant lists and analytics | several contestant/analytics endpoints | `crud_contestant.py`, `analytics.py` | a mixture of `votes` and `contestant_voting` |

The live result was that current UI writes went to an empty new table while the only substantial production history, 86,345 rows in `votes`, was invisible to important ranking readers.

## 2. All voting stores

Read-only production counts were taken both before and after the implementation.

| Store | Rows | Classification | Runtime decision |
|---|---:|---|---|
| `votes` | 86,345 | ACTIVE, immutable historical stage ledger | Preserved and included in ranking through `stage_id -> contest_stages.season_id` |
| `contestant_voting` | 0 | ACTIVE current MyHigh5 ledger / unfinished replacement in production | Sole destination for new contextual MyHigh5 writes; not treated as the historical authority |
| `contest_votes` | 0 | LEGACY | Router unregistered; handlers fail closed with HTTP 410 if registered accidentally |
| `app_votes` | 1 | UNKNOWN/LEGACY external data | No active voting/ranking ORM path found; unchanged |
| `contestant_rankings` | 0 | DERIVED/UNUSED | Dynamic ranking is preferred; table unchanged |
| `user_vote_rankings` | 0 | UNFINISHED/UNUSED | Unchanged |
| `vote_rankings` | 0 | UNKNOWN/UNUSED | Unchanged |
| `vote_sessions` | 0 | LEGACY/UNUSED | Unregistered broken stage flow; unchanged |
| `voting_type` | 1 | ACTIVE configuration | Unchanged |

No table was deleted, truncated, copied, backfilled, or rewritten.

## 3. Canonical source decision

The canonical application boundary is now `backend/app/services/voting_ranking.py`.

- `votes` remains the authoritative historical vote ledger.
- `contestant_voting` is the authoritative current MyHigh5 write ledger because it is the only existing model with `contest_id`, `season_id`, `vote_bucket_key`, `position`, and `points`.
- All repaired ranking consumers call one compatibility aggregate that reads both generations. New writes are never duplicated across stores.

This is deliberately a logical canonical source, not a claim that the empty table supersedes the historical ledger. A single physical table cannot safely be achieved without a tested schema/data reconciliation because historical `votes` lacks contest/category context.

## 4. Evidence for the decision

Production verification established:

- `votes` has 86,345 ACTIVE rows; `contestant_voting` has zero.
- All historical rows have valid voter, contestant, stage, and season references.
- The historical data belongs to two populated stages/seasons (6,291 and 80,054 votes).
- Every populated historical season is linked to many contests (97-104), so a historical row cannot be assigned to one contest from `stage_id` alone.
- `contestants.season_id` is a real foreign key to `contest_seasons.id`; code/comments treating it as a contest ID are not reliable.
- `contest_entries` has no `contestant_id`, so it cannot bridge historical votes to a contest.
- All 470 historical voter/stage groups contain more than five rows, and only 4,449 historical rows match the modern 1..5 / 5..1 point pattern. Reinterpreting these rows as MyHigh5 selections would corrupt their meaning.
- There are zero duplicate ACTIVE groups under the production unique rule `(voter_id, contestant_id, stage_id)`.

## 5. Legacy table classification

The old `contest_votes` API is no longer registered. Its two handlers also return HTTP 410 before any query or mutation. `endpoints/voting.py` was already unregistered and remains unused because its CRUD code expects non-existent `Vote` fields such as `is_valid`.

Derived ranking tables remain in place for compatibility but are not updated by the repaired vote path. No legacy store is populated simply to satisfy an old reader.

## 6. Vote write flow

The active flow is:

`contest page / VoteButton -> contestService.voteForContestant -> POST /api/v1/contestants/{id}/vote -> contestant endpoint context and eligibility checks -> voting_ranking.cast_myhigh5_vote -> contestant_voting -> commit -> best-effort notification -> scoped cache invalidation`.

Replacement and reorder call the same core service. The endpoint resolves and validates the contestant, contest, round, season, voting window, self-vote rule, and geography. The core service owns position and point calculation and never accepts client-provided points, totals, contest ownership, or vote dates. Reorder requires the complete exact scoped set.

## 7. Ranking calculation

`aggregate_rankings` reads historical and current facts in one query boundary and emits one `RankingRow` per supplied candidate. The implemented deterministic order is:

1. total points descending;
2. shares descending;
3. likes/positive reactions descending;
4. comments descending;
5. views descending;
6. contestant ID ascending.

Ranks are unique ordinal positions. Exact metric ties therefore resolve to the lower stable contestant ID; database natural order is never used. Total vote count is returned for display but is not a tie-breaker, preserving the pre-existing documented TopHigh5 business order.

Contest roster responses, TopHigh5, prior-stage ranking, and promotion selection now use this service. Candidate pre-capping before full ordering was removed from the winner path.

## 8. Period, season, and stage filtering

Historical votes are filtered by stored `votes.stage_id -> contest_stages.season_id`; their out-of-window `vote_date` values are not used to relocate them to another month. Current votes are filtered by persisted `season_id`, `contest_id`, and `vote_bucket_key`.

MyHigh5 mutations require an explicit season, contest, and category bucket. Category buckets span multiple contest pages for the same season, so a user cannot obtain five additional slots merely by switching to another page for the same category. There is no current-date fallback in the canonical service.

Known hard boundary: historical rows cannot be proven to belong to one of the 91-104 contests linked to their season. The service can safely rank a caller-supplied contestant roster at stage/season level, but production contest-specific historical attribution still requires a trustworthy roster relation or schema field. Deployment must be replayed against a production clone before historical contest winners are accepted.

## 9. TopHigh5 implementation

`GET /api/v1/seasons/top-high5` now delegates final points, vote totals, engagement values, and ordering to `aggregate_rankings`. The limit is applied only after complete deterministic sorting, and one row per nominator is retained. The same ranking helper is used by the season migration service.

Status: PARTIAL pending production-clone replay, because the live schema cannot prove contest membership for historical vote rows. The code preserves those rows and does not silently switch to the empty table.

## 10. MyHigh5 implementation

The product meaning remains the user's ordered, maximum-five nominee selection for one season/category, with positions 1..5 worth 5..1 points. Current MyHigh5 reads and history remain on `contestant_voting`; historical `votes` are not fabricated into MyHigh5 rows because production evidence proves they follow a different 1..10 pattern and contain much larger voter/stage groups.

Cast, fifth-place replacement, and reorder now share transactional service methods. The existing frontend APIs already match these endpoints, so no UI redesign or production frontend data-path change was necessary.

## 11. Top-five and winner selection

Top-five selection uses the same comparator as TopHigh5 and applies the five-row limit after full ranking. Re-running ranking is deterministic. Existing promotion code checks for an existing `ContestantSeason` link, reactivates where appropriate, and converges stale target links toward the selected set rather than blindly inserting duplicates.

Status: PARTIAL until winner replay on a restored production database confirms contest rosters for the historical seasons.

## 12. Concurrency protection

All active MyHigh5 mutations lock the authenticated voter's `users` row with `SELECT ... FOR UPDATE` before duplicate, nominator, and five-slot checks. This serializes different concurrent contestant requests for the same user on PostgreSQL.

The existing database unique constraint `(user_id, contestant_id, season_id)` on `contestant_voting` remains the final authority for exact duplicate contestants. Inserts run inside a savepoint; `IntegrityError` becomes a stable HTTP 409 conflict and the caller rolls back. The historical partial unique index `uq_votes_active_voter_contestant_stage` is unchanged.

No schema constraint currently expresses “at most five rows per season/category”; correctness for that rule relies on the PostgreSQL voter-row lock plus the fact that every active writer now uses the core service.

## 13. Cache behavior

Ranking results are computed synchronously from PostgreSQL. Correctness does not require Celery or Redis (`USE_CELERY=false` in production). Successful cast, replace, and reorder operations attempt scoped invalidation using season and contest IDs. Redis failure does not roll back a durable vote. TopHigh5 continues to send no-cache semantics, and the frontend refreshes on its existing `vote-changed` event.

## 14. Files changed

Prompt 2 repair files:

- `backend/app/services/voting_ranking.py`
- `backend/app/api/api_v1/api.py`
- `backend/app/api/api_v1/endpoints/contestant.py`
- `backend/app/api/api_v1/endpoints/votes.py`
- `backend/app/api/api_v1/endpoints/season_migration.py`
- `backend/app/api/api_v1/endpoints/analytics.py`
- `backend/app/services/season_migration.py`
- `backend/app/crud/crud_contest.py`
- `backend/app/crud/crud_contestant.py`
- `backend/scripts/validate_voting_production_readonly.py`
- `backend/tests/unit/test_voting_ranking.py`
- `VOTING_RANKING_REPAIR_REPORT.md`

Before editing, the pre-existing dirty worktree was recorded and copied to `worktree_checkpoints/prompt2-prechange-20260908.zip`. No unrelated dirty change was overwritten.

## 15. Tests added

The new focused suite covers valid writes, duplicate conflicts, database uniqueness, serialized five-slot enforcement, same-nominator prevention, server point calculation, invalid positions, missing voters, atomic fifth replacement, reorder integrity, deterministic ranks/ties, TopHigh5 limit ordering, repeatability, historical compatibility, mixed-generation aggregation, season isolation, stage isolation, current-period isolation, contest/category isolation, cache invalidation, authentication, and legacy-route removal.

Existing endpoint logic continues to cover contestant/contest/round membership and closed voting-window rejection. No payment, payout, KYC, email-delivery test, webhook, or blockchain call was made.

## 16. Test results

- Backend full suite: **180 passed, 2 skipped**. The two skips are opt-in PostgreSQL accounting tests unrelated to voting.
- Frontend Vitest: **29 passed in 10 files**.
- Frontend production build: **passed**, 88 static pages generated.
- Python compilation of changed modules: **passed**.
- Standalone TypeScript check: **blocked before source checking** by the pre-existing mismatch between installed TypeScript 5.9.2 and `tsconfig.json` value `ignoreDeprecations: "6.0"`. Next's configured build explicitly skips type validation and succeeded.

## 17. Production validation

The validation script creates a separate SQLAlchemy engine, removes the unsupported Neon URL startup option, begins an explicit read-only transaction, and runs aggregate/catalog `SELECT` statements only.

- BEFORE `votes`: **86,345**
- AFTER `votes`: **86,345**
- BEFORE `contestant_voting`: **0**
- AFTER `contestant_voting`: **0**
- Historical duplicate ACTIVE groups: **0**
- Historical orphan voters/contestants/stages/seasons: **0 / 0 / 0 / 0**

No production row or schema object was changed.

## 18. Remaining risks

1. Historical contest/category attribution is not provable from the live schema. This blocks certifying old contest-specific TopHigh5/winner results without a clone replay and a business-approved mapping.
2. The existing production database has Alembic revision `f3merge01` while the repository has three heads. No migration can be applied safely until that graph is reconciled and tested on a restored copy.
3. The current table has no database check/constraint for unique positions or a maximum of five per bucket. The row-lock design is safe while all writers use the service, but a future out-of-band writer could violate it.
4. Engagement tie-break data is not directly keyed to season/stage in the current schema. It preserves the documented business comparator but should be replay-tested for historical leaderboards.
5. Production PostgreSQL concurrency behavior was not exercised with writes; tests used the isolated SQLite test database and verified the DB unique final authority separately.
6. The standalone frontend type-check configuration is currently invalid for the installed TypeScript version.

## 19. Schema changes required

No schema change is required to deploy the compatibility repair for new MyHigh5 writes and stage/season rankings. A future schema reconciliation is required to reach a single physical event store and certify contest-specific historical results. At minimum, it needs an explicit, validated contest/category association for historical votes and should consider database constraints for `(user, season, bucket, position)` and the five-slot invariant.

No migration was created or applied. Alembic state was not readjusted, stamped, or upgraded.

## 20. Deployment instructions

Deployment is required for the backend code to take effect, but was not performed by this implementation session.

1. Review the Prompt 2 diff separately from the pre-existing dirty files and create a normal source-control commit.
2. Restore a recent Neon snapshot into an isolated staging database.
3. Point a staging backend at that restored database and run `backend/scripts/validate_voting_production_readonly.py`; retain the JSON output.
4. Replay representative historical stage/season and contest TopHigh5 requests. Do not approve historical contest winners until roster attribution is confirmed.
5. Run the full backend suite and frontend build from the committed revision.
6. From `/opt/projects/kalutafoundation/app/deploy/hostinger`, build only the backend service: `docker compose build backend`.
7. Deploy only that service: `docker compose up -d --no-deps backend`.
8. Do **not** run `alembic upgrade head`, `alembic stamp`, or any migration command.
9. Verify backend health/build info, authenticated MyHigh5 read/reorder behavior in staging, and TopHigh5 read responses. Do not submit a real production vote as a smoke test.
10. Run the production validation script read-only again and confirm the historical count has not decreased.

Production rollout should remain blocked until step 4 resolves the historical contest-roster ambiguity or product explicitly accepts stage/season-only historical ranking.
