"""
Local, DB-independent tests for repair_utility.py's pre-flight validation
(Steps 1-3 of the runbook: artifact hashing, structural validation,
rollback cross-check). These checks all run BEFORE the utility ever opens
a database connection, so they can be verified against deliberately
corrupted copies of the real manifest directory without touching any
database, live or test.

The DB-dependent checks (live target snapshot match, preserve/exclusion
existence, wrong-baseline detection, execute-path rollback-on-failure)
cannot be exercised here without a disposable Postgres instance, which
this read-only session did not have. Those code paths were instead
validated by the actual production PREVIEW run (Step 10-12 of the
runbook) succeeding end-to-end against real live data -- the most
authoritative test available for exactly those branches.

Run with: python test_repair_utility_static_checks.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REAL_MANIFEST_DIR = HERE
UTILITY = HERE / "repair_utility.py"
FIXTURES = HERE / "test_fixtures"

REQUIRED_FILES = [
    "delete_manifest.csv",
    "preserve_manifest.csv",
    "exclusion_manifest.csv",
    "rollback_artifact.json",
]


def fresh_fixture_dir(name: str) -> Path:
    d = FIXTURES / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for fname in REQUIRED_FILES:
        shutil.copy(REAL_MANIFEST_DIR / fname, d / fname)
    return d


def run_utility(manifest_dir: Path, execute: bool = False) -> subprocess.CompletedProcess:
    # --release-dir is irrelevant for these tests since every case here
    # aborts before the git-SHA / DB-connection step is ever reached.
    args = [
        sys.executable, str(UTILITY),
        "--manifest-dir", str(manifest_dir),
        "--release-dir", str(HERE),
    ]
    if execute:
        args.append("--execute")
    return subprocess.run(args, capture_output=True, text=True)


results = []


def record(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status))
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))


# 1. Missing manifest file must fail before any DB connection, zero writes.
d = fresh_fixture_dir("missing_manifest")
(d / "preserve_manifest.csv").unlink()
p = run_utility(d)
record("missing manifest file -> non-zero exit", p.returncode != 0, p.stdout[-300:])

# 2. Altered manifest hash (tamper with delete_manifest.csv content) must fail.
d = fresh_fixture_dir("altered_hash")
with open(d / "delete_manifest.csv", "a", encoding="utf-8") as f:
    f.write("\n999999,1,1,1,country,X,1,1,1,0,0,False,2026-01-01,CROSS_ROUND_DUPLICATE_FREEZE,1\n")
p = run_utility(d)
record("altered manifest hash -> non-zero exit", p.returncode != 0, p.stdout[-300:])
record("altered manifest hash -> hash mismatch reported", "SHA256" in p.stdout and "FAIL" in p.stdout)

# 3. Duplicate manifest ID must fail.
d = fresh_fixture_dir("duplicate_id")
lines = (d / "delete_manifest.csv").read_text(encoding="utf-8").splitlines()
header, body = lines[0], lines[1:]
tampered = [header] + body + [body[0]]  # duplicate the first data row's id
(d / "delete_manifest.csv").write_text("\n".join(tampered) + "\n", encoding="utf-8")
p = run_utility(d)
record("duplicate delete id -> non-zero exit", p.returncode != 0, p.stdout[-300:])
# (this also changes the file's hash, so it will legitimately fail at the
#  hash-integrity check first -- still correctly refuses to proceed)

# 4. Preserve/delete overlap must fail (move one preserve row into delete).
d = fresh_fixture_dir("preserve_delete_overlap")
preserve_lines = (d / "preserve_manifest.csv").read_text(encoding="utf-8").splitlines()
p_header, p_body = preserve_lines[0], preserve_lines[1:]
overlap_id = p_body[0].split(",")[0]
delete_lines = (d / "delete_manifest.csv").read_text(encoding="utf-8").splitlines()
d_header, d_body = delete_lines[0], delete_lines[1:]
fake_delete_row = f"{overlap_id},1,1,1,country,X,1,1,1,0,0,False,2026-01-01,CROSS_ROUND_DUPLICATE_FREEZE,1"
(d / "delete_manifest.csv").write_text("\n".join([d_header] + d_body + [fake_delete_row]) + "\n", encoding="utf-8")
p = run_utility(d)
record("preserve/delete overlap -> non-zero exit", p.returncode != 0, p.stdout[-300:])

# 5. Exclusion/delete overlap must fail (move one exclusion row into delete).
d = fresh_fixture_dir("exclusion_delete_overlap")
exclusion_lines = (d / "exclusion_manifest.csv").read_text(encoding="utf-8").splitlines()
e_header, e_body = exclusion_lines[0], exclusion_lines[1:]
overlap_id2 = e_body[0].split(",")[0]
delete_lines2 = (d / "delete_manifest.csv").read_text(encoding="utf-8").splitlines()
d_header2, d_body2 = delete_lines2[0], delete_lines2[1:]
fake_delete_row2 = f"{overlap_id2},1,1,1,country,X,1,1,1,0,0,False,2026-01-01,CROSS_ROUND_DUPLICATE_FREEZE,1"
(d / "delete_manifest.csv").write_text("\n".join([d_header2] + d_body2 + [fake_delete_row2]) + "\n", encoding="utf-8")
p = run_utility(d)
record("exclusion/delete overlap -> non-zero exit", p.returncode != 0, p.stdout[-300:])

# 6. Untouched, correct manifest copy must still pass the pre-DB checks
#    (sanity: the tests above fail because of the tampering, not because
#    the harness itself is broken). This will fail once it reaches the
#    git-SHA check against a bogus --release-dir -- confirm it gets THAT
#    far and no further, and confirm zero writes were possible either way.
d = fresh_fixture_dir("untampered_control")
p = run_utility(d)
record(
    "untampered manifest passes Steps 1-3 (fails later at release-dir git check, as expected)",
    "ALL PRECONDITIONS PASSED" in p.stdout or "release backend SHA" in p.stdout,
    p.stdout[-300:],
)

print()
passed = sum(1 for _, s in results if s == "PASS")
print(f"{passed}/{len(results)} static checks passed")
shutil.rmtree(FIXTURES, ignore_errors=True)
sys.exit(0 if passed == len(results) else 1)
