# Winner Selection and Migration Guide (MyHigh5)

This guide explains, in plain English, how winners are selected and how contestants move between levels.
It uses names as examples so non-technical teams can validate results easily.

## 1) What decides the winner?

For contestants in the same comparison group, ranking is decided in this exact order:

1. **Total voting points (stars)** - higher wins
2. **Total shares** - if points tie
3. **Total likes** - if shares tie
4. **Total comments** - if likes tie
5. **Total views** - if comments tie
6. **Earlier submission** - if everything ties, the entry submitted first wins

Rules confirmed by management on 2026-10-02:

- A voter ranks up to five entries. Position 1 earns 5 points, position 2 earns 4, then 3, 2 and 1. Ranking uses total **points**, never the number of votes.
- Points are **cumulative across phases**. The score an entry competes with at a stage is everything it earned in the earlier stages of the same cohort plus the points earned in that stage (Country 120 + Regional 40 = 160 at Regional). Votes are never copied: each vote stays in the stage it was cast in and the total is calculated from them.
- Shares, likes, comments and views only break ties. They are never converted into points.
- **No vote is required.** If nobody in a group has points, the tie-breakers decide.
- If two entries are equal on everything including the submission time, the lower internal id is used only to keep the order stable.

---

## 2) Example using names (not IDs)

Contest: **Bongo Star Search**

Contestants and stats:

- **Aisha**: 100 stars, 20 shares, 50 likes, 14 comments, 1000 views
- **Brian**: 100 stars, 22 shares, 40 likes, 20 comments, 1100 views
- **Clara**: 100 stars, 22 shares, 40 likes, 20 comments, 900 views
- **David**: 98 stars, 30 shares, 70 likes, 25 comments, 1500 views

Ranking result:

1. **Brian** (ties on stars with Aisha/Clara, wins on shares)
2. **Clara** (ties with Brian on stars/shares/likes/comments, loses on views)
3. **Aisha** (same stars, but fewer shares)
4. **David** (fewer stars, so ranked below all 100-star contestants even with strong engagement)

---

## 3) How migration works by level

The system promotes contestants step-by-step:

- **CITY -> COUNTRY**
- **COUNTRY -> REGIONAL**
- **REGIONAL -> CONTINENT**
- **CONTINENT -> GLOBAL**

### Promotion limits

- Every step uses the same ranking and takes the **top 5 of each group**: per city (City -> Country), per country (Country -> Regional) and per regional bloc (Regional -> Continental).
- **Continental -> Global** is one worldwide pool per contest: the top 5 of the whole continental stage advance, whatever their continent.
- Fewer than 5 entries in a group: all of them advance. Exactly one entry: it advances automatically.
- One nominator can hold only one of a group's winner slots (their best-ranked entry).

### Important behavior

- A stage with no votes still promotes its top 5, ranked by carried points and the tie-breakers.
- Non-selected contestants in that source season are marked as not qualified.
- Selected contestants are linked to the destination season and the contest season link is moved forward.
- A winner whose country has no configured regional bloc cannot be placed. That entry is left untouched (still qualified, still in its Country stage) and logged as `PROGRESSION_UNPLACED`, so it can be recovered once a bloc is configured.
- A winner on a child-safety hold is not promoted and nobody is promoted in their place.
- Running the promotion again changes nothing: no duplicate memberships, seasons or Top High5 rows, and no rewritten timestamps.

### Checking before promoting (read-only)

```bash
PYTHONPATH=. python scripts/progression_recovery_dry_run.py --round 28 --csv entries.csv
```

Lists every due transition with each entry's previous-stage points, current-stage points, cumulative points, tie-breakers, rank and whether it would advance. It writes nothing.

---

## 4) Migration example with names

Assume these contestants are in **Country Season**:

- Aisha (best overall)
- Brian
- Clara
- David
- Eva
- Faisal

When promoting **COUNTRY -> REGIONAL** with limit 5 (per country grouping):

- Promoted: **Aisha, Brian, Clara, David, Eva**
- Not promoted: **Faisal**

Then for **CONTINENT -> GLOBAL**: the top 5 of the contest's whole continental stage advance, ranked on the points they have accumulated since their first stage.

If Brian and Clara are tied on points, shares, likes and comments, then views decides.
If views also tie, the entry submitted earlier wins.

---

## 5) How to run validation tests

From backend root:

```bash
source venv/bin/activate
export PYTHONPATH=/root/mh5/backend
python scripts/test_winner_migration_flow.py
python scripts/test_winner_full_chain.py
```

Expected success lines:

- `PASS: winner tie-break + migration promotion order matches business rules.`
- `PASS: full chain + tie-break rules validated.`
- `Rollback complete (non-persistent mode).`

---

## 6) Make this file downloadable as PDF

### Option A (easy, from browser/editor)

1. Open this file: `docs/WINNER_AND_MIGRATION_GUIDE.md`
2. Print / Export as PDF
3. Save as `Winner_and_Migration_Guide.pdf`

### Option B (CLI with pandoc)

If `pandoc` is installed:

```bash
pandoc docs/WINNER_AND_MIGRATION_GUIDE.md -o docs/Winner_and_Migration_Guide.pdf
```

---

## 7) One-line business summary

**Winner ranking = cumulative voting points first, then engagement tie-breaks (shares -> likes -> comments -> views), then the earlier submission; the top 5 of each group move level-by-level, with or without votes, until global winners are determined.**
