# Contest Category, Media, and Content Integrity Repair Report

**Audit and implementation:** 2026-09-08 to 2026-09-09  
**Repository:** `kalutafoundation` at `a134b6c` plus the preserved Prompt 2/3 and pre-existing worktree changes  
**Production database inspected:** Neon PostgreSQL `neondb`, read-only  
**Implementation status:** **PARTIAL**  

Prompt 4 established a canonical category identity, removed category-name filtering from active paths where a category foreign key exists, standardized new backend media uploads and frontend media rendering, tightened upload/video validation, and enforced media ownership for post attachment and deletion. It did not mutate production data, delete production media, or touch Alembic.

The status remains PARTIAL because production still contains categoryless contests, a malformed canonical slug, duplicate active contest definitions, historically ambiguous contestant/category membership, and localhost media references whose underlying objects and `/storage/...` serving path cannot be proven available. Direct UploadThing routes also continue to rely on UploadThing's type/size enforcement rather than locally inspecting every uploaded object's bytes.

## 1. Category architecture

The live contest taxonomy is:

```text
categories.id
    -> contest.category_id
        -> ContestContext.category_key
        -> VotingRankingService bucket/category scope
        -> contestant roster only when the contest relationship is provable
```

`contest.contest_type` remains a compatibility/display label. For rows with `category_id`, it is synchronized from `categories.slug`; it is not the authoritative identity. A legacy fallback may use normalized `contest_type` only for contests whose `category_id` is null.

Contestants do not have a category foreign key. Their category is derived through a fully resolved contest/season/round context. Prompt 3's fail-closed historical attribution remains authoritative; category inference is not used to assign the 86,345 historical votes to contests.

## 2. Canonical category model

`categories` is canonical.

| Field/relationship | Production meaning |
|---|---|
| `id` | Stable canonical identifier and primary key |
| `name` | Display name; exact-value unique constraint |
| `slug` | Public/API lookup identifier; exact-value unique constraint |
| `description` | Optional display metadata |
| `image_url` | Optional category media reference; production column already existed and is now represented in ORM/schema/admin UI |
| `is_active` | Soft deactivation/status flag |
| `created_at` | Creation timestamp |
| `Category.contests` / `contest.category_id` | One category to many contests; production FK exists |

The table has no parent identifier, explicit ordering column, `updated_at`, or delete timestamp. Production therefore does not support an active subcategory hierarchy through this model.

API behavior now resolves a category deterministically by numeric ID or case-insensitive canonical slug, defaults public reads to active rows, orders lists by name then ID, trims names, canonicalizes slugs to lowercase, rejects malformed slugs/image URLs, and rejects normalized name/slug conflicts. Hard deletion remains possible only for an unused category; a category referenced by any contest must be deactivated instead.

## 3. Category table classification

| System | Production rows | Classification | Evidence |
|---|---:|---|---|
| `categories` | 118, all active | **ACTIVE / canonical** | `contest.category_id` FK, registered `/api/v1/categories` API, admin UI, contest payloads and filters |
| `contest.category_id` | 189 assigned, 7 null | **ACTIVE** | Canonical relationship used by current contest and ranking paths |
| `contest.contest_type` | 196 values | **DERIVED / compatibility** | Legacy label retained for older clients and null-category fallback; two values disagree with their linked category |
| `contest_types` | 8, all active | **LEGACY / unfinished** | Populated configuration taxonomy, but no FK from `contest`, no registered router, and three types do not match any legacy contest label |
| `contest_categories` | 0 | **UNFINISHED / unused** | Child of `contest_types`; no production rows and no connection to live contests |
| `ContestContextService` category key | derived | **ACTIVE / derived** | Uses the resolved contest and canonical category ID without inventing historical attribution |
| `contestant_voting.vote_bucket_key` | derived/stored | **ACTIVE / derived** | Current MyHigh5 scope; category ID is preferred over compatibility type |
| `Contestant` category | none | **DERIVED only when provable** | No category FK; season memberships alone are not sufficient when a season contains many contests |

No separate active genre, topic, industry, country-category, or media-category table was found.

## 4. Production integrity findings

The production analyzer opened an explicit transaction, executed `SET TRANSACTION READ ONLY`, ran only `SELECT`/catalog queries, and rolled back.

| Check | Result |
|---|---:|
| Canonical categories | 118 |
| Active / inactive | 118 / 0 |
| Empty names / slugs | 0 / 0 |
| Normalized duplicate-name groups | 0 |
| Normalized duplicate-slug groups | 0 |
| Malformed slugs | 1: category 12, `beauty-` |
| Categories referenced by no contest | 21 |
| Contests | 196 |
| Contests with null category | 7, all active/non-deleted |
| Contests referencing a missing category | 0 |
| Active contests using a disabled category | 0 |
| Legacy `contest_type` differing from linked category | 2 |
| Duplicate active `(category, legacy type, mode)` contest groups | 7 |

The duplicate groups are duplicate contest definitions inside valid categories, not duplicate rows in `categories`; they were reported and left untouched.

Contestant/category derivation remains structurally ambiguous in production: 506 contestants resolve to multiple category/contest candidates through shared season links and 72 resolve to none; zero resolve to exactly one by that relationship alone. This is consistent with Prompt 3 and is not repaired by guessing.

Production constraints include PKs on all four taxonomy tables; unique constraints on `categories.name`, `categories.slug`, `contest_types.name`, and `contest_types.slug`; `contest.category_id -> categories.id`; and `contest_categories.contest_type_id -> contest_types.id`. The exact unique indexes are case-sensitive and do not enforce `lower(trim(...))` uniqueness.

## 5. Category routing

The registered canonical API is `/api/v1/categories`:

- `GET /api/v1/categories` lists categories deterministically and is active-only by default.
- `GET /api/v1/categories/{identifier}` accepts a numeric ID or canonical slug and is active-only by default.
- Create, update, and delete require an authenticated admin.
- Renaming a display name does not change ID-based contest assignment.
- Slug edits remain possible for administrators and can affect slug-based public links; the current active frontend contest routes are contest-ID based, so no forced SEO route break was introduced.

The `myfav_contests` type/category router is not registered, so `contest_types -> contest_categories` is not a second active public route system.

## 6. Category filtering

Category filtering now follows these rules:

1. Use `contest.category_id` when it exists.
2. Use normalized `contest_type` only when `category_id IS NULL`.
3. Never allow a matching compatibility label to pull in a contest assigned to a different category ID.

The rule is applied in contest queries, category scope keys, nomination rosters, current MyHigh5 writes/reorders, ranking aggregation, TopHigh5 selection, and the frontend contest tabs. The frontend receives `categoryId`, `categoryName`, and `categorySlug` and filters by ID rather than translated/display labels.

## 7. Media architecture

New backend-owned uploads use one path:

```text
authenticated UploadFile
  -> byte/filename/MIME/extension validation
  -> local storage or S3 under uploads/{user_id}/{uuid.ext}
  -> media row owned by user_id with size/dimensions
  -> /api/v1/media/file/{user_id}/{filename}
  -> normalizeMediaUrl / MediaImage
```

`Media` is the canonical owned media record for backend uploads. Post uploads were repaired to create `media` plus `post_media` transactionally; the old path tried to write nonexistent `post_media.media_url/media_type` fields and bypassed the shared validator through a separate S3 service.

Direct UploadThing uploads remain a second provider path used by profile, contestant, verification, category-admin, and moderated frontend flows. They return provider HTTPS URLs rather than `media` rows. This is active compatibility architecture, not yet a single physical store.

## 8. Storage providers

| Backend/provider | Status | Notes |
|---|---|---|
| Backend local filesystem | **ACTIVE/configured** | UUID names beneath owner directories; lookup checks configured and legacy local roots |
| AWS S3 via `app.core.storage` | **ACTIVE/configured** | Owner-keyed objects; API streams private objects; production S3 failure now fails closed instead of silently switching to ephemeral local storage |
| UploadThing | **ACTIVE** | Next.js routes and UI upload components; authenticated middleware, endpoint limits, and moderation callbacks |
| `feed_aws_s3` service | **LEGACY** | Module remains, but the active post-media endpoint no longer bypasses canonical `store_media` |
| External HTTPS URLs | **ACTIVE compatibility** | Contest images, avatars, and provider video URLs |
| Cloudinary | **NOT FOUND as an active implementation** | No active storage flow |
| Azure storage | **UNFINISHED configuration hint** | Accepted as a configuration label but no complete media implementation was found |

The checked-in Apache configuration proxies `/api/` and `/media/` to the backend, but not `/storage/`. This matters for old localhost `/storage/...` data.

## 9. Media ownership model

| Reference | Owner and cardinality | Integrity status |
|---|---|---|
| `media.user_id` | Required owning user, one-to-many | 72/72 production rows have a valid owner |
| `contest_entries.media_id` | Optional single entry media reference | All 72 media rows are referenced here; no missing targets |
| Legacy `contest_entry.media_id` | Required single media on legacy entry table | Table has 0 rows; no missing targets |
| `post_media(post_id, media_id, order)` | Ordered many-to-many join | 0 production rows; new writes validate author ownership |
| Comments/likes/private messages/group content `media_id` | Optional media FK | Present as auxiliary consumers; direct ownership is inherited from the media row and endpoint authorization |
| `contest.image_url`, `contest.cover_image_url` | Optional single URL, contest-owned by association | URL reference, not a media FK |
| `categories.image_url` | Optional single URL, admin-managed | URL reference, not a media FK |
| `users.avatar_url` | Optional single URL, profile-owned | URL reference, not a media FK |
| `contestants.image_media_ids` | Optional serialized collection | 137 JSON-array-like, 72 other legacy values, 369 empty |
| `contestants.video_media_ids` | Optional serialized collection | 136 JSON-array-like, 442 empty |
| `contest_submissions.file_url/external_url` | Optional file/external URL | 0 production rows; currently unused |

Media read/delete requires owner or admin. Post attachment now rejects missing, duplicate, or another user's media IDs before creating a post. Replacing/removing a category image changes only the reference and deliberately does not delete a possibly shared provider object.

## 10. URL normalization strategy

New backend URLs are stored host-agnostically as `/api/v1/media/file/{numeric-owner}/{safe-filename}`. The frontend `normalizeMediaUrl` is the single rendering compatibility helper for contest images, contestant images, avatars, category images, and generic `MediaImage`:

- canonicalizes `/media/{owner}/{file}` and S3 `/uploads/{owner}/{file}` references to the API route;
- rebinds old localhost references to the current public origin rather than the visitor's machine;
- preserves HTTPS external assets;
- upgrades ordinary external HTTP URLs to HTTPS;
- allows only raster `data:` preview types and browser-local `blob:` values;
- rejects credentials in URLs, protocol-relative URLs, filesystem paths, control characters, unsafe schemes, malformed URLs, and encoded filename traversal;
- removes query strings when converting backend-owned file paths to their portable stored form.

Historical database values were not rewritten. `MediaImage` and `UserAvatar` now fail safely to an intentional fallback or remove the failed image node.

## 11. Broken-media analysis

No remote media URL was fetched, so network reachability is classified conservatively.

| Source | Classification | Count |
|---|---|---:|
| `categories.image_url` | empty | 118 |
| `contest.cover_image_url` | empty | 192 |
| `contest.cover_image_url` | localhost `/storage/...` | 4 |
| `contest.image_url` | absolute HTTPS | 190 |
| `contest.image_url` | empty | 6 |
| `media.url` | localhost `/storage/contests/entries/...` | 72 |
| `media.path` | localhost `/storage/contests/entries/...` | 72 |
| `users.avatar_url` | absolute HTTPS | 92 |
| `users.avatar_url` | localhost `/storage/avatars/...` | 5 |
| `users.avatar_url` | empty | 142 |

The 153 localhost field references are **LEGACY DOMAIN / POTENTIALLY MISSING**. They no longer target a visitor's loopback address after normalization, but the checked-in proxy does not expose `/storage/` and the referenced files were not present in the checkout. Their actual object availability is therefore unproven. Rendering now degrades safely; recovering them requires an operator to locate/import the original objects or approve replacement assets.

All 72 production `media` rows are images with file sizes populated and dimensions missing. The missing dimensions are historical metadata gaps, not proof the objects are absent. No media row has a missing owner or missing `contest_entries` target.

## 12. Upload security

The canonical backend upload endpoint now requires authentication and validates:

- filename basename, NUL, slash/backslash, and traversal;
- a bounded read before persistence;
- 8 MB maximum for images and 32 MB for videos;
- allowed raster/video signatures (JPEG, PNG, GIF, WebP, MP4/MOV, WebM);
- extension, declared MIME, and detected bytes must agree;
- image decode/verification and a 50-million-pixel limit;
- UUID server filenames, preventing overwrite and browser-filename trust;
- owner-keyed local/S3 paths;
- production S3 failure without unsafe local fallback.

The moderated Next.js proxy validates filename, size, MIME/extension, and byte signature before base64/moderation/upload. When moderation is configured, provider failure now fails closed. UploadThing route middleware requires a valid application user and applies provider file-count/type/size rules. A remaining hardening item is independent byte-signature verification for every direct-to-UploadThing route after provider upload.

SVG is not accepted by the canonical media validators, avoiding active-content/script upload risk.

## 13. Image handling

Existing dimensions/aspect ratios were preserved. No historical image was recompressed, resized, or rewritten. New canonical uploads record file size and raster dimensions after successful decode. Generic rendering now uses one compatibility helper and controlled fallbacks; contest cards, contestant cards, category previews, and avatars no longer expose raw unvalidated URL handling.

Thumbnail generation was not introduced because the active architecture contains no established thumbnail contract. The database does not contain a canonical thumbnail field for these entities.

## 14. Video handling

Uploaded video support is MP4/MOV/WebM on the backend and UploadThing video routes. External video parsing supports exact/subdomain matches for YouTube, TikTok, Vimeo, Facebook, and HTTPS direct-video references where the active component permits them.

Provider detection no longer uses substring matching, so hosts such as `youtube.com.evil.example` fail. URLs with unsafe schemes or embedded credentials fail. YouTube IDs and Vimeo IDs must parse correctly before an embed URL is returned. The renderer no longer injects TikTok oEmbed HTML with `innerHTML` or falls back to arbitrary iframe URLs; TikTok uses a safe external link, and invalid YouTube/Vimeo inputs render nothing.

## 15. Admin workflows

Category create/edit/activate/deactivate/delete and assignment are admin-protected. Category create/update normalizes values and checks conflicts; contest create/update rejects missing or inactive category IDs and synchronizes the compatibility `contest_type` label. Categories referenced by contests cannot be hard-deleted.

The admin category page now includes the existing production `image_url` field, UploadThing image selection, safe preview, replacement, and reference removal. It does not delete shared storage objects. Contest and contestant media continue through their existing forms with aligned limits and safe rendering.

## 16. Frontend integration

The frontend now consumes category ID/name/slug from contest responses, uses stable ID filtering, and falls back to a legacy label only for null-category rows. `normalizeMediaUrl` and `MediaImage` replace ad hoc origin/localhost handling on the changed contest, contestant, avatar, and category surfaces. Intentional emoji/initial/placeholder fallbacks remain; the visual design was not changed.

No confirmed live backend image was replaced with mock content. The localhost seed/demo references were retained for compatibility and classified as potentially missing rather than silently rewritten in production.

## 17. Prompt 2 integration

`VotingRankingService` continues to be the only ranking engine. Category bucket keys now prefer `category_id`. Contest sets for ranking use that FK, with legacy-label fallback limited to null-category contests. MyHigh5 reorder validates explicit contest/season context, validates every contestant against the same category scope, and fails closed for mixed-category input. TopHigh5 retains the Prompt 2 deterministic ranking behavior.

Prompt 2 regression status: **PASS**.

## 18. Prompt 3 integration

`ContestContextService` remains the contest/round/season/stage/category resolver. Prompt 4 uses its established category output and the Prompt 3 roster helpers; it does not introduce a competing context service. Shared-season rosters are category-scoped only when a contest relationship is provable.

Historical vote count before and after the production read-only checks remained **86,345**. All 86,345 remain contest/category ambiguous and were not modified or reattributed.

Prompt 3 regression status: **PASS**.

## 19. Files changed

Prompt 4 changed or added:

- `backend/main.py`
- `backend/app/api/api_v1/endpoints/admin.py`
- `backend/app/api/api_v1/endpoints/categories.py`
- `backend/app/api/api_v1/endpoints/contestant.py`
- `backend/app/api/api_v1/endpoints/contests.py`
- `backend/app/api/api_v1/endpoints/feed_posts.py`
- `backend/app/api/api_v1/endpoints/media.py`
- `backend/app/core/storage.py`
- `backend/app/crud/crud_contest.py`
- `backend/app/crud/crud_social.py`
- `backend/app/models/category.py`
- `backend/app/models/post.py`
- `backend/app/schemas/category.py`
- `backend/app/services/contest_category_integrity.py`
- `backend/app/services/voting_ranking.py`
- `backend/scripts/analyze_category_media_production_readonly.py`
- `backend/tests/unit/test_category_media_integrity.py`
- `frontend/app/api/upload/moderated/route.ts`
- `frontend/app/api/uploadthing/core.ts`
- `frontend/app/contests/page.tsx`
- `frontend/app/dashboard/admin/categories/page.tsx`
- `frontend/components/dashboard/contest-card.tsx`
- `frontend/components/dashboard/contestant-card.tsx`
- `frontend/components/ui/media-image.tsx`
- `frontend/components/ui/media-image.test.tsx`
- `frontend/components/ui/upload-button.tsx`
- `frontend/components/ui/video-embed.tsx`
- `frontend/components/user/user-avatar.tsx`
- `frontend/lib/media-url.ts`
- `frontend/lib/media-url.test.ts`
- `frontend/lib/upload-validation.ts`
- `frontend/lib/upload-validation.test.ts`
- `frontend/lib/utils/video-platforms.ts`
- `frontend/lib/video-platforms.test.ts`
- `frontend/services/contest-service.ts`
- `CONTEST_CATEGORY_MEDIA_REPAIR_REPORT.md`

The pre-Prompt-4 checkpoint is `worktree_checkpoints/prompt4-prechange-20260908.zip`. Prompt 2/3 and unrelated pre-existing dirty changes were preserved.

## 20. Tests added

Prompt 4 coverage includes category listing and deterministic ID/slug lookup, disabled rows, normalized duplicates, malformed slugs, category assignment, category deletion safeguards, canonical scope priority, cross-category list/ranking/reorder isolation, media URL compatibility and unsafe URL rejection, missing-image fallbacks, unauthorized upload/delete, file signatures, MIME/extension mismatches, oversize files, path traversal, metadata capture, S3 fail-closed behavior, post media ownership, safe provider-video parsing/rendering, and single media-route registration.

The existing Prompt 2 and Prompt 3 test suites are included in the full backend run.

## 21. Test results

- Focused Prompt 4 backend suite after final route cleanup: **33 passed**.
- Final full backend suite after route deduplication: **232 passed, 0 failed, 2 skipped**. The two skips are opt-in PostgreSQL accounting tests unrelated to Prompt 4.
- Frontend Vitest: **63 passed, 0 failed** across 14 files.
- Frontend production build: **passed**, 88 pages generated; the repository build configuration explicitly skips type validation and linting.
- Standalone TypeScript validation: **blocked by pre-existing project errors and a TypeScript 5.9.2 / `ignoreDeprecations: "6.0"` configuration mismatch**. No reported error was in a Prompt 4 file.

## 22. Schema recommendations

### REQUIRED FOR COMPLETE DATABASE-LEVEL CORRECTNESS

1. After Alembic graph reconciliation, add case/space-normalized unique indexes for category name and slug, for example unique indexes on `lower(btrim(name))` and `lower(btrim(slug))`. Current exact-value unique indexes do not close a concurrent mixed-case insert race.
2. Reconcile the seven categoryless contests and the malformed `beauty-` slug through an approved data plan before enforcing `contest.category_id NOT NULL` for live contest rows.

### OPTIONAL HARDENING

- Add an index on `contest.category_id` for category-filtered reads; production currently has the FK but no dedicated index in the inspected index set.
- Add normalized uniqueness within `contest_categories(contest_type_id, name/slug)` if that unfinished hierarchy is ever activated.
- Replace serialized `contestants.image_media_ids/video_media_ids` with an owned join model only after a staging migration/replay.
- Add explicit media-purpose/entity association records and object lifecycle state for provider cleanup/reconciliation.
- Backfill image dimensions only after object existence is verified in staging; do not infer values.

No migration was created or applied. The repository still has three heads while production is stamped `f3merge01`.

## 23. Production risks

1. Seven active contests have no canonical category; their compatibility fallback remains necessary.
2. Seven duplicate active contest/category/mode groups can still create duplicate catalogue behavior.
3. One malformed slug and two category/legacy-label disagreements require an approved data correction.
4. Twenty-one active categories are unused; they may be intentional future catalogue entries and were not deleted.
5. Contestant/category attribution through shared seasons is ambiguous for 506 contestants and unavailable for 72; Prompt 3's fail-closed behavior must remain.
6. The 153 localhost media field references are only compatibility-normalized; actual files/public `/storage/` reachability is unproven.
7. Direct UploadThing routes do not all independently re-read bytes for signature validation.
8. Media replacement removes references safely but does not provide a complete cross-provider garbage-collection/outbox workflow.
9. The divergent Alembic graph prevents safe constraint deployment.
10. Prompt 2/3 historical replay and deployment blockers remain unchanged.

## 24. Deployment recommendation

**Deployment is not recommended.** Do not deploy Prompt 4 independently from review of the combined dirty worktree. First reconcile the categoryless/duplicate contest records and malformed slug in an isolated restored database, locate or replace the localhost media objects, verify `/storage/` versus canonical media serving in staging, decide whether direct UploadThing signature verification is required, rerun the full suites from a clean commit, and preserve all Prompt 2/3 fail-closed behavior.

No production data or schema was changed. No production file, UploadThing object, S3 object, historical vote, external service, email, payment, payout, KYC request, webhook, or blockchain action was triggered.
