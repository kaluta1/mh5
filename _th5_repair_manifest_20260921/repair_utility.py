#!/usr/bin/env python3
"""
One-time repair utility for the Top High5 cross-round duplicate-freeze
defect (see KALUTASOCIETY_TOP_HIGH5_SYSTEMIC_DUPLICATE_FREEZE_AUDIT and
KALUTASOCIETY_TOP_HIGH5_REPAIR_MANIFEST_PHASE1).

DEFAULT MODE IS PREVIEW. No database write happens unless --execute is
passed AND every precondition below passes.

This utility NEVER dynamically discovers repair targets. It reads only
the immutable delete_manifest.csv (plus preserve_manifest.csv and
exclusion_manifest.csv for cross-verification, and rollback_artifact.json
for snapshot comparison) produced by the manifest-building phase. If the
live database no longer matches what those files describe, this utility
aborts rather than improvising.

Usage:
    PYTHONPATH=<backend release dir> <release venv python> repair_utility.py \
        --manifest-dir /path/to/_th5_repair_manifest_20260921 \
        --release-dir /opt/kalutasociety/releases/<current release> \
        [--execute]

Without --execute: PREVIEW only, zero writes, always safe to run.
With --execute: performs the DELETE, but only after every invariant in
PHASE_CHECKS passes; aborts (no write) on the first failure.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Hard-coded safety invariants (Step 5). These are NOT read from any
# runtime-mutable source -- they are the approved, human-reviewed contract
# for this specific repair. Changing the underlying data changes these
# numbers, which is exactly why they are hard-coded checks, not assumptions.
# ---------------------------------------------------------------------------
EXPECTED_BACKEND_SHA = "c45d79d8f2f3810a691766411132dd1e1c2d03a2"
EXPECTED_TOPHIGH5_BEFORE = 1940
EXPECTED_DELETE_COUNT = 733
EXPECTED_PRESERVE_COUNT = 368
EXPECTED_EXCLUSION_COUNT = 287
EXPECTED_TOPHIGH5_AFTER = 1207
EXPECTED_CONTESTANT_VOTING = 1203
EXPECTED_CONTESTANTS = 1073

EXPECTED_HASHES = {
    "delete_manifest.csv": "3031c9317da1a37d4566fee9e162f9d9ab776f4e9a14ddb0b7bfed9125dde29b",
    "preserve_manifest.csv": "26090cfd79d095078b623ee5c1f9e26cff93ecff2171a9d0359eef609aba3734",
    "exclusion_manifest.csv": "553b1dc6f14ea377a8edf12e5316ac3a77dc6f02a983e44944608046ff2b4e2c",
    "rollback_artifact.json": "38411a124dc46707aec993d89e2f4704f2f711fd915130b86ae8ccbcfa52c25c",
}

PROTECTED_CONTESTANTS = [776, 873, 648, 664, 475, 519, 615, 617]
KNOWN_FIVE = [190, 564, 552, 140, 238]

# Columns compared between the live row and its rollback snapshot -- every
# business-meaningful column except pure bookkeeping timestamps.
COMPARE_COLUMNS = [
    "contestant_id", "contest_id", "category_id", "level", "jurisdiction",
    "round_id", "rank", "total_points", "total_votes", "shares", "likes",
    "comments", "views", "migrated", "from_season_id", "to_season_id",
]


class AbortRepair(Exception):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        raise AbortRepair(f"{label}: {detail}")


def get_git_head(release_dir: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(release_dir), capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-dir", required=True, type=Path)
    parser.add_argument("--release-dir", required=True, type=Path, help="Backend release dir (for git SHA check)")
    parser.add_argument("--execute", action="store_true", help="Perform the DELETE. Default is preview-only.")
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "PREVIEW"
    print(f"=== Top High5 cross-round duplicate repair -- MODE: {mode} ===\n")

    try:
        # ---- Step 1/Phase check: artifact hashes (full 64-char digest) ----
        print("--- Artifact integrity ---")
        manifest_files = {
            "delete_manifest.csv": args.manifest_dir / "delete_manifest.csv",
            "preserve_manifest.csv": args.manifest_dir / "preserve_manifest.csv",
            "exclusion_manifest.csv": args.manifest_dir / "exclusion_manifest.csv",
            "rollback_artifact.json": args.manifest_dir / "rollback_artifact.json",
        }
        for name, path in manifest_files.items():
            check(f"{name} exists", path.exists(), str(path))
            actual_hash = sha256_of(path)
            check(
                f"{name} SHA256 matches approved manifest",
                actual_hash == EXPECTED_HASHES[name],
                f"expected {EXPECTED_HASHES[name]}, got {actual_hash}",
            )

        delete_rows = load_csv(manifest_files["delete_manifest.csv"])
        preserve_rows = load_csv(manifest_files["preserve_manifest.csv"])
        exclusion_rows = load_csv(manifest_files["exclusion_manifest.csv"])
        with open(manifest_files["rollback_artifact.json"], encoding="utf-8") as f:
            rollback = json.load(f)

        # ---- Step 2: structural validation ----
        print("\n--- Structural validation ---")
        check("delete manifest row count", len(delete_rows) == EXPECTED_DELETE_COUNT, str(len(delete_rows)))
        check("preserve manifest row count", len(preserve_rows) == EXPECTED_PRESERVE_COUNT, str(len(preserve_rows)))
        check("exclusion manifest row count", len(exclusion_rows) == EXPECTED_EXCLUSION_COUNT, str(len(exclusion_rows)))

        delete_ids = [r["top_high5_result_id"] for r in delete_rows]
        check("delete ids all non-blank", all(i.strip() for i in delete_ids))
        check("delete ids unique", len(set(delete_ids)) == len(delete_ids))
        check("delete reasons all CROSS_ROUND_DUPLICATE_FREEZE", all(r["reason"] == "CROSS_ROUND_DUPLICATE_FREEZE" for r in delete_rows))

        preserve_ids = [r["top_high5_result_id"] for r in preserve_rows]
        check("preserve ids unique", len(set(preserve_ids)) == len(preserve_ids))
        check("preserve reasons all AUTHORITATIVE_COHORT_RESULT", all(r["reason"] == "AUTHORITATIVE_COHORT_RESULT" for r in preserve_rows))

        exclusion_ids = [r["top_high5_result_id"] for r in exclusion_rows]
        check("exclusion ids unique", len(set(exclusion_ids)) == len(exclusion_ids))
        approved_exclusion_reasons = {"EXCLUDED_ZERO_MATCH", "EXCLUDED_INSUFFICIENT_EVIDENCE", "EXCLUDED_OTHER_DEFECT_CLASS"}
        check("exclusion reasons all approved categories", all(r["reason"] in approved_exclusion_reasons for r in exclusion_rows))

        d_set, p_set, e_set = set(delete_ids), set(preserve_ids), set(exclusion_ids)
        check("DELETE and PRESERVE disjoint", d_set.isdisjoint(p_set))
        check("DELETE and EXCLUSION disjoint", d_set.isdisjoint(e_set))

        # ---- Step 3: rollback artifact validation ----
        print("\n--- Rollback artifact validation ---")
        rollback_ids = set(str(r["th5_id"]) for r in rollback["rows"])
        check("rollback ids == delete ids exactly", rollback_ids == d_set)
        rollback_by_id = {str(r["th5_id"]): r for r in rollback["rows"]}

        # ---- Baseline SHA / DB checks ----
        print("\n--- Environment preconditions ---")
        actual_sha = get_git_head(args.release_dir)
        check("release backend SHA matches approved commit", actual_sha == EXPECTED_BACKEND_SHA, actual_sha)

        sys.path.insert(0, str(args.release_dir))
        from app.core.config import settings  # noqa: E402
        import psycopg2  # noqa: E402

        conn = psycopg2.connect(settings.SQLALCHEMY_DATABASE_URI)
        if not args.execute:
            conn.set_session(readonly=True, autocommit=True)
        else:
            conn.autocommit = False
        cur = conn.cursor()

        def scalar(sql, params=None):
            cur.execute(sql, params or ())
            return cur.fetchone()[0]

        before_count = scalar("SELECT count(*) FROM top_high5_results")
        voting_count = scalar("SELECT count(*) FROM contestant_voting")
        contestants_count = scalar("SELECT count(*) FROM contestants")
        check("top_high5_results baseline", before_count == EXPECTED_TOPHIGH5_BEFORE, str(before_count))
        check("contestant_voting baseline", voting_count == EXPECTED_CONTESTANT_VOTING, str(voting_count))
        check("contestants baseline", contestants_count == EXPECTED_CONTESTANTS, str(contestants_count))

        # ---- Step 6: live target row snapshot match ----
        print("\n--- Live target row snapshot match (Step 6) ---")
        delete_id_ints = [int(i) for i in delete_ids]
        cur.execute(
            f"SELECT id, {', '.join(COMPARE_COLUMNS)} FROM top_high5_results WHERE id = ANY(%s)",
            (delete_id_ints,),
        )
        cols = ["id"] + COMPARE_COLUMNS
        live_rows = {str(row[0]): dict(zip(cols, row)) for row in cur.fetchall()}
        check("all delete-manifest ids found live", set(live_rows.keys()) == d_set,
              f"missing={sorted(d_set - set(live_rows.keys()))[:10]}")

        mismatches = []
        for th5_id, live in live_rows.items():
            snap = rollback_by_id[th5_id]
            for col in COMPARE_COLUMNS:
                live_val = live[col]
                snap_val = snap.get(col)
                # level is an enum in the DB, a plain string in the JSON snapshot
                if str(live_val) != str(snap_val):
                    mismatches.append((th5_id, col, live_val, snap_val))
        check("every target row matches its rollback snapshot", not mismatches,
              f"{len(mismatches)} mismatches, sample={mismatches[:5]}")

        # ---- Step 7: preserve assertions ----
        print("\n--- Preserve row assertions (Step 7) ---")
        preserve_id_ints = [int(i) for i in preserve_ids]
        cur.execute(
            f"SELECT id, {', '.join(COMPARE_COLUMNS)} FROM top_high5_results WHERE id = ANY(%s)",
            (preserve_id_ints,),
        )
        live_preserve = {str(row[0]): dict(zip(cols, row)) for row in cur.fetchall()}
        check("all preserve-manifest ids found live", set(live_preserve.keys()) == p_set,
              f"missing={sorted(p_set - set(live_preserve.keys()))[:10]}")
        preserve_mismatches = []
        for r in preserve_rows:
            th5_id = r["top_high5_result_id"]
            live = live_preserve.get(th5_id)
            if live is None:
                continue
            expected = {
                "contestant_id": r["contestant_id"], "level": r["level"], "round_id": r["round_id"],
                "jurisdiction": r["jurisdiction"], "rank": r["rank"], "migrated": r["migrated"],
            }
            for col, exp_val in expected.items():
                if str(live[col]) != str(exp_val):
                    preserve_mismatches.append((th5_id, col, live[col], exp_val))
        check("no preserve row targeted for delete", d_set.isdisjoint(p_set))
        check("preserve rows match manifest expectations", not preserve_mismatches,
              f"{len(preserve_mismatches)} mismatches, sample={preserve_mismatches[:5]}")

        for cid in PROTECTED_CONTESTANTS:
            cid_preserve = [r["top_high5_result_id"] for r in preserve_rows if r["contestant_id"] == str(cid)]
            cid_delete = [r["top_high5_result_id"] for r in delete_rows if r["contestant_id"] == str(cid)]
            print(f"  protected contestant {cid}: preserve={cid_preserve} delete={cid_delete}")

        # ---- Step 8: exclusion assertions ----
        print("\n--- Exclusion row assertions (Step 8) ---")
        exclusion_id_ints = [int(i) for i in exclusion_ids]
        cur.execute("SELECT id FROM top_high5_results WHERE id = ANY(%s)", (exclusion_id_ints,))
        live_exclusion_ids = {str(row[0]) for row in cur.fetchall()}
        check("all exclusion-manifest ids still exist live", live_exclusion_ids == e_set,
              f"missing={sorted(e_set - live_exclusion_ids)[:10]}")
        check("no exclusion row in delete set", d_set.isdisjoint(e_set))

        # ---- Step 9: known-five human-readable preview ----
        print("\n--- Known-five review (Step 9) ---")
        for cid in KNOWN_FIVE:
            pres = [r["top_high5_result_id"] for r in preserve_rows if r["contestant_id"] == str(cid)]
            dele = [r["top_high5_result_id"] for r in delete_rows if r["contestant_id"] == str(cid)]
            own_round = next((r["authoritative_round_id"] for r in delete_rows if r["contestant_id"] == str(cid)), None)
            foreign_rounds = sorted({r["bad_round_id"] for r in delete_rows if r["contestant_id"] == str(cid)})
            print(f"  contestant {cid}: authoritative_round={own_round} preserve={pres} delete={dele} foreign_rounds={foreign_rounds}")

        # ---- Step 11/12: preview target select + simulated result ----
        print("\n--- Target selection + projection ---")
        cur.execute("SELECT count(*) FROM top_high5_results WHERE id = ANY(%s)", (delete_id_ints,))
        target_selected = cur.fetchone()[0]
        check("live target SELECT count == delete manifest count", target_selected == EXPECTED_DELETE_COUNT, str(target_selected))
        print(f"  PROJECTED top_high5_results after repair: {before_count} - {len(delete_id_ints)} = {before_count - len(delete_id_ints)}")
        check("projection matches approved EXPECTED_TOPHIGH5_AFTER", before_count - len(delete_id_ints) == EXPECTED_TOPHIGH5_AFTER)

        print(f"\n=== ALL PRECONDITIONS PASSED ({mode} mode) ===")

        if not args.execute:
            print("PREVIEW ONLY -- zero database writes performed. Re-run with --execute for the real operation.")
            conn.close()
            return 0

        # ---- Step 13: transaction design for --execute ----
        print("\n--- EXECUTING DELETE (transaction) ---")
        try:
            cur.execute("DELETE FROM top_high5_results WHERE id = ANY(%s)", (delete_id_ints,))
            deleted_count = cur.rowcount
            check("deleted row count == manifest count", deleted_count == EXPECTED_DELETE_COUNT, str(deleted_count))

            after_count = scalar("SELECT count(*) FROM top_high5_results")
            check("post-delete top_high5_results count", after_count == EXPECTED_TOPHIGH5_AFTER, str(after_count))

            after_voting = scalar("SELECT count(*) FROM contestant_voting")
            check("contestant_voting unchanged", after_voting == EXPECTED_CONTESTANT_VOTING, str(after_voting))
            after_contestants = scalar("SELECT count(*) FROM contestants")
            check("contestants unchanged", after_contestants == EXPECTED_CONTESTANTS, str(after_contestants))

            cur.execute("SELECT count(*) FROM top_high5_results WHERE id = ANY(%s)", (preserve_id_ints,))
            check("all preserve rows still present post-delete", cur.fetchone()[0] == len(preserve_id_ints))
            cur.execute("SELECT count(*) FROM top_high5_results WHERE id = ANY(%s)", (exclusion_id_ints,))
            check("all exclusion rows still present post-delete", cur.fetchone()[0] == len(exclusion_id_ints))
            cur.execute("SELECT count(*) FROM top_high5_results WHERE id = ANY(%s)", (delete_id_ints,))
            check("no target ids remain", cur.fetchone()[0] == 0)

        except AbortRepair:
            conn.rollback()
            print("\n*** ABORTED: an invariant failed after DELETE -- transaction ROLLED BACK, zero net change. ***")
            conn.close()
            return 1

        conn.commit()
        print("\n=== COMMITTED. Repair executed successfully. ===")
        conn.close()
        return 0

    except AbortRepair as exc:
        print(f"\n*** ABORTED before any write: {exc} ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
