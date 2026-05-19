# Contest flow verification checklist

Use this document to confirm the product matches the intended flow. Each step lists **expected behavior**, **URL/API**, and **how to verify**.

---

## 1. Entry

| Step | Expected | Verify |
|------|----------|--------|
| Click **Contests** (logged in) | `/dashboard/contests` | Sidebar + header |
| Click **Contests** (logged out) | `/contests` | Public grid |
| Sidebar **MyHigh5** | `/dashboard/myhigh5` | Personal top-5 ballot |
| Sidebar **Top High5** | `/dashboard/top-high5` | Leaderboard / migration preview |

---

## 2. Contests hub (`/dashboard/contests`)

### One contest per category per mode (important)

| Rule | Meaning |
|------|---------|
| Per **category** | At most **one** active `contest_mode=nomination` row |
| Per **category** | At most **one** active `contest_mode=participation` row |
| **Nominate tab** | Only nomination rows (after API dedupe) |
| **Participations tab** | Only participation rows |

If you see **two cards for the same category** on Nominate (e.g. two “Gospel”), the database likely has **two nomination rows** for that category. The city / “participate in your city” copy should be `contest_mode=participation`.

**Audit / repair (backend):**
```bash
cd backend
python scripts/fix_contest_category_duplicates.py          # dry-run
python scripts/fix_contest_category_duplicates.py --apply  # fix DB
```

**Regional vote (Nominate tab):** With the **Vote** pill selected, open level **Regional**. The API uses the vote round (+1 calendar round for migrated pool) and `contestLevel=regional`. Only contests with an active **REGIONAL** season link on that round appear. Duplicates per category are deduped on the list API.

### Why one nominator could appear twice as regional winners (fixed)

| Layer | Old behavior | Correct rule |
|-------|----------------|--------------|
| **Nominate** | One row per `contest_id` only | **One nomination per category per round** (any contest row) |
| **Vote** | One vote per nominator per `cat:{category_id}` bucket | Same |
| **Country → Regional migration** | Ran **once per contest id** on the round | **Once per category**; top 5 per country keeps **one slot per nominator** |

Duplicate **contest** rows (two Gospel nominations) let the same nominator submit twice; migration promoted both to regional. Fix: category-wide nomination guard + migration dedupe by nominator + one promotion per category.

### Tabs
- **Nominate** → only `contest_mode = nomination`
- **Participations** → only `contest_mode = participation`

### Round pills (`computeDisplayRounds`)
- **Submit** → nomination month (submit window)
- **Vote** → live voting round (`isRoundVotingLive`)
- **Submit & Vote** → same round when both overlap

### Country filter (Nominate tab)
- Defaults to user profile country
- Passed to API as `filterCountry` on `GET /rounds/`
- Passed on **View** as `?country=` when country-level contest

### Card actions
| Button | When | Goes to |
|--------|------|---------|
| **Nominate** | No entry yet, submission open | `/dashboard/contests/{id}/apply?roundId&entryType=nomination` |
| **Edit** | `current_user_contesting` true | Same + `edit=true` + **`user_entry_round_id`** (calendar round you nominated in) |
| **View** | Always | `/dashboard/contests/{id}?roundId&entryType&country&viewOnly?` |

### `viewOnly=true`
- Set only when pill is **Submit** (nominate month) — browse nominees, **no voting**
- **Not** set on **Vote** pill — user can cast MyHigh5 votes on detail

### After nominate
- `contestant-submitted` event → hub cache cleared → cards refresh **Edit** state

---

## 3. Nominate flow

### Apply (`/dashboard/contests/{id}/apply`)
1. `GET /contests/{id}?roundId&entryType=nomination`
2. Form: info → video URL → review
3. `POST /api/v1/contests/{id}/participate` with `round_id`, `nominator_city/country`, `entry_type=nomination`
4. Backend stores: `contestants.season_id = contest.id`, `round_id`, `entry_type=nomination`

### Success screen
- **View nominations** → detail with `roundId`, `entryType`, `country` (not bare `/contests/{id}`)
- **Edit** (if submission still open)

### Rules
- KYC/verification **skipped** for nominations
- Nominator country must match user profile country

---

## 4. View nominees (`/dashboard/contests/{id}`)

### Query params
| Param | Role |
|-------|------|
| `roundId` | Calendar round for roster |
| `entryType=nomination` | Nomination rows only |
| `country` | Country scope (must match card filter) |
| `viewOnly=true` | Read-only (submit month browse) |

### API
- `GET /contests/{id}?roundId&entryType&filterCountry`
- Backend `display_round_id` resolves round:
  - Keeps URL round if it has nominations (or **your** nomination in that round)
  - Vote-month URL with empty vote round → switches to round with nominee rows
  - No `roundId` → prefers **your** latest nomination round, then submit month

### Roster rules
- `season_id = contest.id` + `entry_type` nomination (+ legacy NULL)
- Strict `round_id` for nominations
- Country filter **always includes your rows** even if geo fields mismatch

### UI
- Empty list + you nominated → silent refetch once
- **Edit** / **Nominate** on empty state uses `userHasEntry` + `display_round_id`
- Does **not** overwrite explicit `roundId` in URL (only fills when missing)

---

## 5. Vote flow (Vote pill)

1. Open contest **without** `viewOnly`
2. `POST /api/v1/contestants/{id}/vote?contest_id&round_id`
3. Max **5** votes per category bucket (`vote_bucket_key`)
4. Positions 1–5 → points 5–1
5. Replace 5th: `POST .../vote/replace` on 409

### MyHigh5 drawer (detail)
- `GET /api/v1/contestants/user/my-votes?contest_id=`
- Reorder: `PUT .../my-votes/reorder`

---

## 6. MyHigh5 (`/dashboard/myhigh5`)

- `GET /api/v1/contestants/user/my-votes` (+ `level`, optional `roundId`)
- History: `GET .../my-votes/history`
- Archive: `?roundId=` read-only

---

## 7. Top High5 (`/dashboard/top-high5`)

- `GET /api/v1/seasons/top-high5?country&round_id&level`
- Shows who leads / `migrates_next_stage`
- Read-only; refreshes on `vote-changed`

---

## 8. Winner migration (backend, hourly)

Ranking: stars → shares → likes → comments → views → lower id

Promotion: country → regional → continent → global (top 5 per group; global top 3)

Tables: `contestant_voting`, `contestant_seasons`, `contest_season_links`

Test: `python scripts/test_winner_full_chain.py` from `backend/`

---

## 9. Manual QA script (15 min)

1. Log in, set profile **country**.
2. **Contests** → **Nominate** → **Submit** pill → pick country.
3. **Nominate** on a contest → submit video → success → **View nominations**.
4. Confirm nominee visible; count on card ≥ 1.
5. Back to hub → same contest shows **Edit** (not Nominate).
6. **Edit** → form prefilled; save works.
7. Switch to **Vote** pill → **View** → vote enabled (no `viewOnly`).
8. Cast vote → appears in **MyHigh5**.
9. **Top High5** → contestant appears for your country/level.

---

## 10. Known legacy (do not use for new features)

- `vote` / `contest_entry` tables
- `user_vote_rankings` (round-ranked alternate)
- `myfav_contests` router (not mounted)

**Source of truth for MyHigh5:** `contestant_voting`
