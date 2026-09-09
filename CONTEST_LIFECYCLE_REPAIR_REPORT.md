# Contest Lifecycle Repair Report

Date: 2026-09-08  
Repository: `kalutafoundation`  
Production database inspected read-only: Neon PostgreSQL `neondb`

## 1. Current contest architecture

The application has two overlapping contest representations:

| Layer | Runtime path | Stored identity |
|---|---|---|
| Contest catalogue | `frontend/app/dashboard/contests` -> `/api/v1/contests` and `/api/v1/rounds` -> contest/round CRUD | `contest`, `rounds`, `round_contests`, category/type |
| Submission/roster | contest apply page -> `POST /api/v1/contests/{contest_id}/participate` -> contestant CRUD | `contestants`, `contestant_seasons`, and two incompatible entry tables (`contest_entry`, `contest_entries`) |
| MyHigh5 | contest/MyHigh5 pages -> `/api/v1/contestants/.../vote` and `/user/my-votes` -> `voting_ranking.py` | current `contestant_voting`; historical `votes` |
| TopHigh5 | `frontend/app/dashboard/top-high5/page.tsx` -> `contest-service.ts` -> `GET /api/v1/seasons/top-high5` | contest/round/season lookup plus `VotingRankingService` |
| Promotion | admin migration APIs, in-process schedulers, cron proxy, Celery task definitions | `contest_seasons`, `contest_stages`, `contestant_seasons`, `contest_season_links` |

The database relationship proven by foreign keys and production rows is:

`votes.stage_id -> contest_stages.season_id -> contest_seasons.round_id`

and independently:

`contest <-> contest_season_links <-> contest_seasons` and
`contest <-> round_contests <-> rounds`.

`contestants.season_id` has a production foreign key to `contest_seasons.id`; it is **not** a contest ID. `contestants` has no direct contest foreign key. `contestant_seasons` links a contestant only to a season, while a season can be shared by 97-104 contests. The older product documentation and several legacy queries saying `Contestant.season_id == contest.id` therefore conflict with the live schema.

Production contains 8 contest types and 118 categories. The ORM table `contest_entry` and live plural table `contest_entries` are also distinct: the singular table has zero rows, while the plural table has 72 rows but no contestant ID. Sixty are duplicate excess rows by `(contest_id, user_id)`, leaving only 12 unique contest/user pairs.

## 2. Contest identity rules

The safe identities supported by current data are:

- **CONTEST IDENTITY RULE:** `contest.id` identifies a catalogue/category contest, not a monthly occurrence.
- **SEASON IDENTITY RULE:** `(round_id, level)` identifies a progression season. Production currently has no duplicate season groups for that tuple, but the database has no verified unique constraint for it.
- **STAGE IDENTITY RULE:** `(season_id, stage_level, geographic scope, start_date, end_date)` identifies a voting stage; `stage.id` is the stored vote parent.
- **MONTH/PERIOD IDENTITY RULE:** the first day in `rounds.submission_start_date`, excluding cancelled rounds. Names and active/open flags are not identity fields.
- **CATEGORY IDENTITY RULE:** `category_id` when present; otherwise normalized `(contest_type, contest_mode)`.
- **FULL RANKING CONTEXT:** `(contest_id, round_id, season_id, stage_id, category_key)`. A contest-specific ranking must prove all links; it cannot infer one component from a current flag.

`ContestContextService` implements these rules and returns not-found/ambiguity errors instead of choosing `.first()` or the newest row.

## 3. Season and stage rules

A valid context requires:

1. the season belongs to the requested round;
2. the stage belongs to the requested season;
3. the contest is linked to both the season and round;
4. the stage range is valid;
5. the category key comes from the resolved contest.

Current `contestant_voting` rows can isolate contest and season but have no stage ID. Historical `votes` rows isolate stage and season but have no contest ID. Stage isolation for new votes across multiple stages in one season therefore remains a schema limitation.

## 4. Historical vote attribution model

No historical row was modified. Read-time classification uses this hierarchy:

1. Resolve the stored stage, its season, and its round.
2. Intersect contests linked through `contest_season_links` with contests linked through `round_contests`.
3. One candidate is `EXACT`.
4. Multiple candidates can be `STRONG` only if one unique contestant-owner contest entry agrees with any temporal signal, or if a unique contest voting window exists with no entry conflict.
5. Multiple unresolved candidates are `AMBIGUOUS`.
6. Missing stage/season/contest-candidate relationships are `ORPHANED_INVALID`.

A vote is never used as evidence that its contestant belonged to a contest. This avoids circularly manufacturing the roster needed to justify that same vote.

## 5. Attribution statistics

Read-only production result for all 86,345 historical rows:

| Class | Count | Percentage |
|---|---:|---:|
| EXACTLY ATTRIBUTABLE | 0 | 0.000% |
| ATTRIBUTABLE WITH STRONG EVIDENCE | 0 | 0.000% |
| AMBIGUOUS | 86,345 | 100.000% |
| ORPHANED / INVALID | 0 | 0.000% |

Candidate patterns were:

- 80,054 votes: 97 contest candidates, no entry or temporal discriminator.
- 3,185 votes: 104 candidates, three entry candidates, no temporal discriminator.
- 3,106 votes: 104 candidates, two entry candidates, no temporal discriminator.

The stage and season are deterministic for every row. The contest and category are not.

## 6. Historical roster reconstruction

Two stage/season histories can be reconstructed:

| Stage | Season | Round | Stored window | Votes | Contest candidates | Voted contestants |
|---:|---:|---:|---|---:|---:|---:|
| 1 | 3 | 3 | 2026-04-01 through 2026-04-30 | 6,291 | 104 | 72 |
| 3 | 5 | 2 | 2026-03-01 through 2026-03-31 | 80,054 | 97 | 500 |

Roster evidence is incomplete:

- 34,389 votes belong to contestants with a `contestant_seasons` membership for the vote's season.
- 51,956 votes do not have that membership.
- Zero vote contestants have `contestants.season_id` equal to the vote's stage season.
- Zero match `contestants.round_id` to the season round.
- The 72 plural entry rows cannot uniquely resolve any vote; affected owners point to two or three contests.

Consequently, **zero exact historical contest rosters** can be reconstructed. Two stage/season rosters are observable, but treating either as 97/104 identical contest rosters would be fabricated membership.

The compatibility roster resolver accepts only: exact current `contestant_voting(contest_id, season_id)`, a season membership when the season/round has one contest candidate, or a unique contest entry for that contestant owner.

## 7. Temporal validity

Historical vote dates span 2026-05-11 through 2026-06-10. All 86,345 rows occur after, and therefore outside, their referenced stage windows. No contest voting window covers them uniquely. Vote dates cannot safely relocate them because that would contradict their stored stage foreign key and still would not select one contest.

Round month identity is also damaged: production has two non-cancelled records for each of May (IDs 5/6), July (12/13), and August (14/15) 2026. September has one cancelled duplicate and one active record, so it is uniquely resolvable after excluding cancelled rows.

## 8. Current contest resolution

Implemented runtime behavior now:

- resolves a monthly round by exact `submission_start_date` and non-cancelled status;
- maps vote level to an explicit cohort month (`CITY/COUNTRY M-1`, `REGIONAL M-2`, `CONTINENT M-3`, `GLOBAL M-4`);
- validates explicit round IDs and rejects cancelled rounds;
- rejects duplicate contest/round/level season matches;
- returns HTTP 409 with candidate IDs for ambiguous TopHigh5 resolution;
- never silently falls back from an explicit historical round to a current/newer round.

September 2026 submission context is resolvable as round 17. September COUNTRY voting context targets August, which is ambiguous between rounds 14 and 15 and is correctly rejected until an operator determines the authoritative record.

## 9. Ranking integration

Prompt 2's single `VotingRankingService` remains intact. Historical facts are included in a contest-specific aggregate only when a season/round has exactly one contest candidate. Ambiguous history is not assigned merely because a caller supplied candidate IDs. Current contextual votes continue to use `contestant_voting`.

Ranking order is deterministic: points descending, scoped engagement descending when a validated period window is supplied, then contestant ID ascending. `require_votes=True` is used by TopHigh5 and promotion selection so a zero-vote roster cannot become winners by arbitrary ID order.

Because engagement tables have no period key, current TopHigh5/promotion calls do not supply a trusted engagement window; engagement is neutral and the effective safe order is points then contestant ID. This differs from the documented intended tie-break and is a deployment blocker, not a silent approximation.

## 10. Historical TopHigh5 replay

The read-only replay query ranks only `EXACT` and `STRONG` vote attributions. Result:

- Periods replayed: **0**
- Periods fully valid: **0**
- Periods ambiguous: **2 stage/season periods**
- Periods blocked: **2**

No top-five contestant IDs were emitted because every historical vote is contest-ambiguous. Producing results anyway would assign the same pool to dozens of unrelated categories.

## 11. Winner and top-five logic

TopHigh5 and promotion now share `aggregate_rankings`. Candidate rows are filtered to contest-specific roster evidence and vote-backed rankings. Equal metrics resolve by stable contestant ID, and limits are applied after complete ordering. Existing destination membership uses unique `(contestant_id, season_id)` links and reactivates existing links rather than blindly adding duplicates.

The promotion entry point now rejects multiple possible source seasons unless `from_season_id` is explicit. However, legacy migration code still contains broad `Contestant.season_id == contest_id` assumptions and commits inside lower-level operations. Full historical winner certification is therefore **blocked**.

## 12. Monthly migration logic

Documented intent is submission in month M, country voting in M+1, then country-to-regional M+2, regional-to-continent M+3, and continent-to-global M+4. The existing service groups qualifiers by the destination geography and uses five per group, with a separately documented smaller global final.

Implemented safeguards:

- monthly creation uses a PostgreSQL transaction advisory lock keyed by calendar month;
- existing rounds are resolved by exact month rather than name/latest ID;
- both monthly orchestration and the daily season migration path preflight all official month identities before any status, season, or promotion mutation;
- duplicate periods raise instead of automatically cancelling one;
- promotion rejects an ambiguous source season;
- winner selection ignores rows without attributable votes.

On current production data the preflight intentionally stops lifecycle processing because May, July, and August each have duplicate non-cancelled rounds.

## 13. Idempotency strategy

Database uniqueness on `contest_season_links(contest_id, season_id)` and `contestant_seasons(contestant_id, season_id)`, existing-link reactivation, deterministic ordering, and PostgreSQL advisory locks prevent ordinary reruns from inserting the same links concurrently. The fail-before-mutation preflight prevents a run from partially changing flags before discovering duplicate month identity.

This is not yet a complete production proof. There is no unique non-cancelled round-per-month constraint, no durable finalization snapshot/idempotency key, and no staging transition replay. Monthly migration is therefore classified **PARTIAL**, not certified idempotent end to end.

## 14. Engagement attribution

Production ranges are:

| Source | Rows | First | Last |
|---|---:|---|---|
| `page_views` | 504,629 | 2026-05-10 | 2026-06-10 |
| `contest_likes` | 78,533 | 2026-05-16 | 2026-06-10 |
| `contest_comments` | 18,975 | 2026-05-21 | 2026-06-10 |
| `contestant_reactions` | 52,821 | 2026-03-11 | 2026-06-10 |
| `contestant_shares` | 23,522 | 2026-03-10 | 2026-06-10 |

These rows have contestant and timestamp information but no contest, season, or stage foreign key. Timestamp filtering can bound activity only after a valid contest period is known; it cannot select one of 97-104 contest candidates. Lifetime engagement is now excluded from monthly ranking unless an explicit validated window is provided.

## 15. Category isolation

Current MyHigh5 uses `vote_bucket_key` (`cat:{category_id}` or normalized type/mode), plus contest and season. Historical category isolation cannot be proven because historical votes lack contest/category and their seasons are shared across many categories. The ranking layer excludes those ambiguous rows from contest/category results rather than allowing cross-category contamination.

## 16. Scheduler findings

Production reports `USE_CELERY=false`, so no Celery worker or beat performs the work. Backend lifespan code starts an in-process scheduler manager in that mode. It registers payment, contest status, season migration, and monthly round/calendar tasks. A CRON-secret-protected backend endpoint and frontend `/api/cron/[task]` proxy can also invoke these tasks. Celery tasks are configured in code but are not the production execution mechanism.

The repository additionally contains systemd timer/service files and shell scripts for a first-of-month run, but their installation on the verified deployment was not proven. Multiple possible triggers are protected by existing advisory locks; all lifecycle paths that reach the central migration service now encounter the duplicate-month preflight.

## 17. Production data anomalies

Read-only exact counts:

- 86,345 votes outside their referenced stage dates (all after stage end).
- 86,345 contest-ambiguous votes; zero orphan vote foreign keys.
- 51,956 votes without matching contestant-season membership.
- 32 seasons without stages.
- 60 duplicate excess plural contest-entry rows by `(contest_id, user_id)`.
- 195 active contests and 195 voting-open contests out of 196.
- 9 active rounds, 8 voting-open rounds, and 11 stages still marked voting-active.
- 3 duplicate non-cancelled calendar months: May, July, August 2026.
- 0 contests without a season link; 0 seasons without a contest link; 0 stages without a parent.
- 0 duplicate contest-season, contestant-season, or round-contest links.
- 0 duplicate `(round_id, level)` season groups.
- 0 overlapping stage pairs within the same season/level.
- 0 contestants with multiple active seasons for the same round/level.

No anomaly was automatically repaired.

## 18. Code changes

Prompt 3 changes are limited to contest context, ranking integration, monthly safeguards, tests, and read-only analysis:

- `backend/app/services/contest_context.py`
- `backend/app/services/voting_ranking.py`
- `backend/app/services/season_migration.py`
- `backend/app/services/monthly_calendar_ops.py`
- `backend/app/services/monthly_round_scheduler.py`
- `backend/app/scripts/generate_monthly_rounds.py`
- `backend/app/api/api_v1/endpoints/season_migration.py`
- `backend/app/models/contests.py`
- `backend/scripts/analyze_contest_lifecycle_production_readonly.py`
- `backend/tests/unit/test_contest_context.py`
- `backend/tests/unit/test_voting_ranking.py`
- this report.

Prompt 2 files and unrelated pre-existing dirty work were preserved. The pre-change Prompt 3 checkpoint is `worktree_checkpoints/prompt3-prechange-20260908.zip`.

## 19. Tests

Focused Prompt 2/3 lifecycle and ranking suite: **51 passed**. Coverage includes exact and ambiguous current round resolution, cohort month selection, full period validation, duplicate season rejection, exact/strong/ambiguous historical attribution, conservative roster reconstruction, no vote-as-membership inference, no historical mutation, duplicate-month scheduler fail-before-mutation, ambiguous promotion rejection, historical ranking compatibility/isolation, deterministic ties, zero-vote winner exclusion, current vote write/concurrency behavior, TopHigh5, MyHigh5, cache invalidation, authentication, and legacy route removal.

Full backend suite: **199 passed, 0 failed, 2 skipped**. The skips are opt-in PostgreSQL accounting tests unrelated to voting. Frontend Vitest: **29 passed, 0 failed**. Frontend production build: **passed** with 88 pages; that project build configuration explicitly skips type validation and linting.

No payment, payout, KYC, email, blockchain, or webhook action was triggered.

## 20. Staging replay

No restored Neon snapshot/staging database or staging connection is available in this workspace. Production analysis and attribution replay were SELECT-only; migration simulation was limited to isolated test records in the SQLite test database.

- Production historical votes before: **86,345**
- Production historical votes after: **86,345**
- Staging historical reconstruction: **NOT RUN**
- Staging TopHigh5/winner replay: **NOT RUN**
- Staging monthly transition simulation: **NOT RUN**

This alone prevents a COMPLETE status under Prompt 3's success criteria.

## 21. Schema recommendations

### REQUIRED NOW before writable lifecycle deployment

1. A durable contest-period roster/participation mapping keyed by contestant, contest, round, season, and (where applicable) stage, with validity timestamps and uniqueness. Historical mappings must be populated only from external/business evidence; the 86,345 vote rows must not be rewritten.
2. A database invariant allowing at most one non-cancelled official round per submission month. This must be designed and tested after operators reconcile the existing May/July/August duplicates.
3. Reconcile the Alembic graph (`f3merge01` in production versus three repository heads) on a restored copy before preparing or applying either change.

### OPTIONAL HARDENING

- Add stage context to future `contestant_voting` rows.
- Add database enforcement for one position per user/season/category and no more than five slots.
- Add immutable finalization/winner snapshots and a unique promotion idempotency key.
- Add contest/period keys to future engagement events.

### NOT REQUIRED

- Rewriting or adding guessed contest IDs to historical `votes`.
- Copying historical votes into `contestant_voting` or a ranking cache.
- Persisting replay output before attribution is proven.

No migration was created or applied. Alembic files/version state were untouched.

## 22. Remaining risks and deployment recommendation

Deployment is **NOT recommended**.

Blocking reasons:

1. 100% of historical votes remain contest/category ambiguous.
2. No historical contest period can be replayed without inventing roster membership.
3. All historical votes are outside their referenced stage windows.
4. Production has unresolved duplicate monthly round identities, including the current September COUNTRY cohort (August IDs 14/15).
5. Legacy contestant creation/migration code still treats a season foreign key as a contest ID.
6. Engagement tie-breaks cannot be attributed to a contest period; safe runtime behavior is currently points then ID, differing from intended documentation.
7. No restored staging replay has been performed.
8. The Alembic graph remains divergent.

The changes provide a safe compatibility and rejection layer: they preserve Prompt 2, prevent ambiguous history from contaminating rankings, and stop automated lifecycle mutation when identity is ambiguous. They do not manufacture the missing historical facts and therefore cannot resolve Prompt 2's historical deployment blocker without authoritative external mapping and staging validation.
