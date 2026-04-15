# Winner Selection and Migration Guide (MyHigh5)

This guide explains, in plain English, how winners are selected and how contestants move between levels.
It uses names as examples so non-technical teams can validate results easily.

## 1) What decides the winner?

For contestants in the same comparison group, ranking is decided in this exact order:

1. **Total stars (points)** - higher wins
2. **Total shares** - if stars tie
3. **Total likes** - if shares tie
4. **Total comments** - if likes tie
5. **Total views** - if comments tie
6. **First contestant** - if everything ties, the earlier contestant wins (system uses lower internal id)

If two contestants are equal on all engagement metrics, the one who entered first in the system is ranked higher.

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

- For **CITY/COUNTRY/REGIONAL/CONTINENT** steps: top contestants are selected **per location group** (for example per city, per country, per region, depending on step).
- For **GLOBAL**: top contestants are selected from the full source season (overall ranking).

### Important behavior

- If there are no fresh votes in a later season, contestants are still ranked using:
  stars (possibly zero) -> shares -> likes -> comments -> views -> first contestant.
- Non-selected contestants in that source season are marked as not qualified.
- Selected contestants are linked to the destination season and the contest season link is moved forward.

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

Then for **CONTINENT -> GLOBAL** with limit 3:

- Final winners: **Aisha, Brian, Clara**

If Brian and Clara are tied on stars, shares, likes, comments, then views decides.
If views also tie, earlier contestant wins.

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

**Winner ranking = stars first, then engagement tie-breaks (shares -> likes -> comments -> views), then first contestant; migration moves top-ranked contestants level-by-level until global winners are determined.**
