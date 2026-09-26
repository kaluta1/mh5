#!/usr/bin/env python3
"""ContestantSeason 722-row repair tool (exact-ID, single guarded transaction).

Modes:  precheck | backup | execute --backup PATH --backup-sha SHA | verify --backup PATH
The ONLY mutation this tool can perform is, inside `execute`:
    UPDATE contestant_seasons SET is_active = false WHERE id = ANY(<722 manifest ids>) AND is_active = true
and only when every precondition holds; any failed assertion rolls back.
No secret is ever printed.
"""
import argparse, collections, csv, datetime, hashlib, json, os, re, sys

AUD = os.environ.get("CS_AUD", "/root/cs_repair_audit_20260922")
ENVFILE = os.environ.get("CS_ENV", "/opt/kalutasociety/current/backend/.env")
EXPECT_HASH = {
    "contestantseason_keep_manifest.csv": "9d2e2df21050010cf551e99098858eb86509bdc1c1dcd70e596de87f5dd66307",
    "contestantseason_deactivate_manifest.csv": "39a151b0447251b7cd75e539d6a7ce060ddf8cb1d9e91ef71575c3e73becf4b7",
    "contestantseason_exclusion_manifest.csv": "894dd5f8145d3d84e6a435cb7c2cf923780010899ba46e61e68b54fa55ff2e33",
}
ROLLBACK_FILE = "contestantseason_rollback_artifact.json"
FP_TABLES = ["top_high5_results", "contestant_voting", "contestants", "contest_seasons"]
BASE = dict(top_high5_results=1398, contestant_voting=1203, contestants=1073, active=3918, total=16771, groups=747, group_contestants=376, group_rows=2084)
POST = dict(active=3196, groups=339)
C96 = {11704: (254, 3), 14311: (261, 4), 15977: (265, 21)}  # cs id -> (season id, season round)


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ------------------------------------------------------------------ manifests
def load_manifests(directory=AUD, verify_hash=True):
    hashes = {}
    if verify_hash:
        stored = dict(l.strip().split("  ")[::-1] for l in open(f"{directory}/SHA256SUMS.txt") if l.strip())
        for n, want in EXPECT_HASH.items():
            hashes[n] = sha256_file(f"{directory}/{n}") == want
        hashes[ROLLBACK_FILE] = sha256_file(f"{directory}/{ROLLBACK_FILE}") == stored[ROLLBACK_FILE]
    rd = lambda n: list(csv.DictReader(open(f"{directory}/{n}")))
    K, X, E = (rd("contestantseason_keep_manifest.csv"), rd("contestantseason_deactivate_manifest.csv"), rd("contestantseason_exclusion_manifest.csv"))
    ids = lambda rows: {int(r["contestant_season_id"]) for r in rows}
    return dict(K=K, X=X, E=E, kid=ids(K), xid=ids(X), eid=ids(E), hashes=hashes, xids=sorted(ids(X)), kids=sorted(ids(K)))


# ------------------------------------------------------------------ pure logic
def gkey(row, seasons):
    return (row["contestant_id"], seasons[row["season_id"]][0])


def anomalous_groups(cs, seasons):
    g = collections.defaultdict(list)
    for r in cs.values():
        if r["is_active"]:
            g[gkey(r, seasons)].append(r["id"])
    return {k: v for k, v in g.items() if len({seasons[cs[i]["season_id"]][1] for i in v}) > 1}


def _row_evidence(r, cs, seasons, cr):
    live = cs.get(int(r["contestant_season_id"]))
    if live is None: return "MISSING"
    if not live["is_active"]: return "INACTIVE"
    if live["contestant_id"] != int(r["contestant_id"]) or live["season_id"] != int(r["season_id"]): return "IDENTITY"
    if (live["joined_at"], live["created_at"], live["updated_at"]) != (r["joined_at"], r["created_at"], r["updated_at"]): return "ROW_DRIFT"
    lvl, rnd = seasons[live["season_id"]]
    if lvl != r["level"] or str(rnd) != r["season_round_id"]: return "SEASON_EVIDENCE"
    if str(cr.get(live["contestant_id"])) != r["contestant_round_id"]: return "CONTESTANT_ROUND_EVIDENCE"
    return None


def check_pre(st, man):
    """Every precondition. Returns list of (name, ok, detail)."""
    cs, seasons, cr, votes, fps = st["cs"], st["seasons"], st["crounds"], st["votes"], st["fps"]
    K, X, E, kid, xid, eid = man["K"], man["X"], man["E"], man["kid"], man["xid"], man["eid"]
    R = []
    add = lambda n, ok, d="": R.append((n, bool(ok), d))
    for t in ("top_high5_results", "contestant_voting", "contestants"):
        add(f"count.{t}", fps[t][0] == BASE[t], fps[t][0])
    active = sum(1 for r in cs.values() if r["is_active"])
    add("count.active_contestant_seasons", active == BASE["active"], active)
    add("count.contestant_seasons_total", len(cs) == BASE["total"], len(cs))
    ag = anomalous_groups(cs, seasons)
    add("anomaly.groups", len(ag) == BASE["groups"], len(ag))
    add("anomaly.contestants", len({k[0] for k in ag}) == BASE["group_contestants"], len({k[0] for k in ag}))
    add("anomaly.active_rows", sum(len(v) for v in ag.values()) == BASE["group_rows"], sum(len(v) for v in ag.values()))
    add("manifest.row_counts", (len(K), len(X), len(E)) == (408, 722, 954), (len(K), len(X), len(E)))
    add("manifest.ids_unique", (len(kid), len(xid), len(eid)) == (408, 722, 954))
    add("disjoint.keep_deactivate", not (kid & xid)); add("disjoint.deactivate_exclusion", not (xid & eid)); add("disjoint.keep_exclusion", not (kid & eid))
    bad = collections.defaultdict(list)
    for r in X:
        e = _row_evidence(r, cs, seasons, cr)
        if e is None:
            live = cs[int(r["contestant_season_id"])]
            if seasons[live["season_id"]][1] == cr.get(live["contestant_id"]): e = "NOT_FOREIGN"
            elif (live["contestant_id"], live["season_id"]) in votes: e = "HAS_VOTES_ON_FOREIGN_SEASON"
        if e: bad["deactivate"].append((r["contestant_season_id"], e))
    for r in K:
        e = _row_evidence(r, cs, seasons, cr)
        if e is None:
            live = cs[int(r["contestant_season_id"])]
            if seasons[live["season_id"]][1] != cr.get(live["contestant_id"]): e = "KEEP_NOT_HOME_ROUND"
        if e: bad["keep"].append((r["contestant_season_id"], e))
    for r in E:
        e = _row_evidence(r, cs, seasons, cr)
        if e: bad["exclusion"].append((r["contestant_season_id"], e))
    add("targets.722_found_active_and_exact", not bad["deactivate"], bad["deactivate"][:5])
    add("keep.408_found_active_and_exact", not bad["keep"], bad["keep"][:5])
    add("exclusion.954_found_active_and_exact", not bad["exclusion"], bad["exclusion"][:5])
    live_active = collections.defaultdict(set)
    for r in cs.values():
        if r["is_active"]: live_active[gkey(r, seasons)].add(r["id"])
    exp_rep, exp_ex = collections.defaultdict(set), collections.defaultdict(set)
    for r in K + X: exp_rep[(int(r["contestant_id"]), r["level"])].add(int(r["contestant_season_id"]))
    for r in E: exp_ex[(int(r["contestant_id"]), r["level"])].add(int(r["contestant_season_id"]))
    add("groups.repaired_composition_exact", all(live_active.get(k) == v for k, v in exp_rep.items()), len(exp_rep))
    add("groups.excluded_composition_exact", all(live_active.get(k) == v for k, v in exp_ex.items()), len(exp_ex))
    add("groups.union_equals_live_anomalous", set(ag) == set(exp_rep) | set(exp_ex))
    add("groups.exactly_one_keep_each", all(len(v & kid) == 1 for v in exp_rep.values()) and len(exp_rep) == 408)
    ok96 = cr.get(96) == 3 and all(i in cs and cs[i]["contestant_id"] == 96 and cs[i]["season_id"] == s and cs[i]["is_active"] and seasons[s][1] == rnd for i, (s, rnd) in C96.items())
    add("contestant96.keep_and_foreign_rows_match", ok96)
    add("contestant96.classification", 11704 in kid and {14311, 15977} <= xid)
    return R


def check_post(pre, post, man):
    cs0, cs1, seasons = pre["cs"], post["cs"], pre["seasons"]
    K, X, E, kid, xid, eid = man["K"], man["X"], man["E"], man["kid"], man["xid"], man["eid"]
    R = []
    add = lambda n, ok, d="": R.append((n, bool(ok), d))
    changed = {i for i in cs0 if cs0[i] != cs1.get(i)} | {i for i in cs1 if i not in cs0}
    add("post.changed_rows_are_exactly_targets", changed == xid, (len(changed), len(changed - xid), len(xid - changed)))
    add("post.targets_only_is_active_changed", all({k: v for k, v in cs0[i].items() if k != "is_active"} == {k: v for k, v in cs1[i].items() if k != "is_active"} and cs0[i]["is_active"] and not cs1[i]["is_active"] for i in xid))
    add("post.722_targets_inactive", sum(1 for i in xid if not cs1[i]["is_active"]) == 722)
    add("post.408_keep_still_active", sum(1 for i in kid if cs1[i]["is_active"]) == 408)
    add("post.exclusion_rows_unchanged", all(cs0[i] == cs1[i] for i in eid))
    add("post.non_target_rows_unchanged", all(cs0[i] == cs1[i] for i in cs0 if i not in xid) and len(cs0) == len(cs1))
    active = sum(1 for r in cs1.values() if r["is_active"])
    add("post.active_total", active == POST["active"], active)
    ag = anomalous_groups(cs1, seasons)
    exp_ex = {(int(r["contestant_id"]), r["level"]) for r in E}
    add("post.anomalous_groups", len(ag) == POST["groups"], len(ag))
    add("post.remaining_groups_equal_excluded_groups", set(ag) == exp_ex)
    exp_rep = collections.defaultdict(set)
    for r in K + X: exp_rep[(int(r["contestant_id"]), r["level"])].add(int(r["contestant_season_id"]))
    act1 = collections.defaultdict(set)
    for r in cs1.values():
        if r["is_active"]: act1[gkey(r, seasons)].add(r["id"])
    keep_by_group = {(int(r["contestant_id"]), r["level"]): int(r["contestant_season_id"]) for r in K}
    lost_auth = sum(1 for k, kid_ in keep_by_group.items() if act1.get(k) != {kid_})
    add("post.authoritative_memberships_lost", lost_auth == 0, lost_auth)
    def levels(cs):
        m = collections.defaultdict(set)
        for r in cs.values():
            if r["is_active"]: m[r["contestant_id"]].add(seasons[r["season_id"]][0])
        return m
    l0, l1 = levels(cs0), levels(cs1)
    lost_levels = sum(1 for c, s in l0.items() if not s <= l1.get(c, set()))
    add("post.legitimate_levels_lost", lost_levels == 0, lost_levels)
    xlevel = {int(r["contestant_season_id"]): r["level"] for r in X}
    cross = len(changed - xid) + sum(1 for i in changed & xid if seasons[cs1[i]["season_id"]][0] != xlevel[i])
    add("post.cross_level_memberships_affected", cross == 0, cross)
    for t in ("top_high5_results", "contestant_voting", "contestants", "contest_seasons"):
        add(f"post.protected_table_unchanged.{t}", pre["fps"][t] == post["fps"][t], (pre["fps"][t][0], post["fps"][t][0]))
    add("post.contestant96", cs1[11704]["is_active"] and not cs1[14311]["is_active"] and not cs1[15977]["is_active"])
    return R


def summarize(results):
    fails = [(n, d) for n, ok, d in results if not ok]
    return dict(checks=len(results), passed=len(results) - len(fails), failed=fails)


# ------------------------------------------------------------------ database
def engine():
    from sqlalchemy import create_engine
    url = re.search(r"^DATABASE_URL=(.*)$", open(ENVFILE).read(), re.M).group(1).strip().strip('"').strip("'")
    return create_engine(url)


def load_state(conn):
    from sqlalchemy import text
    q = lambda s: conn.execute(text(s))
    cs = {r[0]: dict(id=r[0], contestant_id=r[1], season_id=r[2], is_active=bool(r[3]), joined_at=str(r[4]), created_at=str(r[5]), updated_at=str(r[6]))
          for r in q("select id, contestant_id, season_id, is_active, joined_at, created_at, updated_at from contestant_seasons")}
    seasons = {r[0]: (r[1], r[2]) for r in q("select id, level::text, round_id from contest_seasons")}
    crounds = {r[0]: r[1] for r in q("select id, round_id from contestants")}
    votes = {(r[0], r[1]) for r in q("select contestant_id, season_id from contestant_voting")}
    fps = {}
    for t in FP_TABLES:
        row = q(f"select count(*), md5(coalesce(string_agg(x::text, '|' order by x.id), '')) from {t} x").one()
        fps[t] = (row[0], row[1])
    return dict(cs=cs, seasons=seasons, crounds=crounds, votes=votes, fps=fps)


def now(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def out(obj): print(json.dumps(obj, indent=1, default=str))


def mode_precheck():
    from sqlalchemy import text
    man = load_manifests()
    eng = engine()
    with eng.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            st = load_state(conn)
            ro = conn.execute(text("show transaction_read_only")).scalar()
    res = check_pre(st, man)
    s = summarize(res)
    out(dict(mode="precheck", transaction_read_only=ro, manifest_hashes=man["hashes"], **s,
             LIVE_PRECHECK_EXACT="YES" if not s["failed"] and all(man["hashes"].values()) else "NO",
             pre_active=sum(1 for r in st["cs"].values() if r["is_active"]), pre_groups=len(anomalous_groups(st["cs"], st["seasons"])),
             fps={k: v for k, v in st["fps"].items()}))


def mode_backup():
    from sqlalchemy import text
    man = load_manifests()
    if not all(man["hashes"].values()): out(dict(mode="backup", ABORT="manifest hash mismatch", hashes=man["hashes"])); sys.exit(2)
    eng = engine()
    with eng.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            st = load_state(conn)
    s = summarize(check_pre(st, man))
    if s["failed"]: out(dict(mode="backup", ABORT="live state does not match manifest", **s)); sys.exit(2)
    ts = now(); path = f"{AUD}/execution_backup_{ts}.json"
    payload = dict(purpose="exact pre-repair state of the 722 DEACTIVATE rows; restore = set is_active=true for exactly these ids where is_active=false",
                   created_utc=ts, code_sha=os.popen("git -C /opt/kalutasociety/current rev-parse HEAD").read().strip(),
                   manifest_hashes=EXPECT_HASH, ids=man["xids"], rows=[st["cs"][i] for i in man["xids"]],
                   protected_fps={k: list(v) for k, v in st["fps"].items()},
                   restore_sql="UPDATE contestant_seasons SET is_active = true WHERE id = ANY(:ids) AND is_active = false",
                   note="the repair changes ONLY is_active; joined_at/created_at/updated_at are untouched")
    with open(path, "x") as f: json.dump(payload, f, indent=1, sort_keys=True)
    os.chmod(path, 0o400)
    sha = sha256_file(path); open(path + ".sha256", "x").write(f"{sha}  {os.path.basename(path)}\n"); os.chmod(path + ".sha256", 0o400)
    out(dict(mode="backup", EXECUTION_BACKUP_PATH=path, EXECUTION_BACKUP_SHA256=sha, rows=len(payload["rows"])))


def mode_execute(backup_path, backup_sha):
    from sqlalchemy import text
    man = load_manifests()
    report = dict(mode="execute", started_utc=now(), TRANSACTION_STARTED="NO", TRANSACTION_COMMITTED="NO", TRANSACTION_ROLLED_BACK="NO", ROWS_UPDATED=None)
    if not all(man["hashes"].values()): report["ABORT"] = "manifest hash mismatch"; out(report); sys.exit(2)
    if sha256_file(backup_path) != backup_sha: report["ABORT"] = "execution backup hash mismatch"; out(report); sys.exit(2)
    backup = json.load(open(backup_path))
    if backup["ids"] != man["xids"]: report["ABORT"] = "backup ids != manifest ids"; out(report); sys.exit(2)
    eng = engine()
    conn = eng.connect().execution_options(isolation_level="REPEATABLE READ")
    trans = conn.begin(); report["TRANSACTION_STARTED"] = "YES"
    try:
        conn.execute(text("SET LOCAL lock_timeout = '15s'")); conn.execute(text("SET LOCAL statement_timeout = '90s'"))
        conn.execute(text("SET LOCAL idle_in_transaction_session_timeout = '300s'"))
        locked = [r[0] for r in conn.execute(text("SELECT id FROM contestant_seasons WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"), {"ids": sorted(man["xid"] | man["kid"])})]
        report["rows_locked"] = len(locked)
        if len(locked) != 1130: raise RuntimeError(f"locked {len(locked)} rows, expected 1130 (722 targets + 408 keep)")
        pre = load_state(conn)
        pre_res = check_pre(pre, man); report["preconditions"] = summarize(pre_res)
        if report["preconditions"]["failed"]: raise RuntimeError("precondition failed: " + json.dumps(report["preconditions"]["failed"], default=str)[:600])
        if any(pre["cs"][r["id"]] != r for r in backup["rows"]): raise RuntimeError("live target rows differ from the execution backup")
        if {k: list(v) for k, v in pre["fps"].items()} != backup["protected_fps"]: raise RuntimeError("protected tables changed since the execution backup")
        res = conn.execute(text("UPDATE contestant_seasons SET is_active = false WHERE id = ANY(:ids) AND is_active = true RETURNING id"), {"ids": man["xids"]})
        returned = sorted(r[0] for r in res); report["ROWS_UPDATED"] = len(returned)
        if returned != man["xids"]: raise RuntimeError(f"UPDATE affected {len(returned)} rows / id set differs from manifest (expected 722 exact)")
        post = load_state(conn)
        post_res = check_post(pre, post, man); report["postconditions"] = summarize(post_res)
        if report["postconditions"]["failed"]: raise RuntimeError("postcondition failed: " + json.dumps(report["postconditions"]["failed"], default=str)[:600])
        report["in_txn_summary"] = dict(active=sum(1 for r in post["cs"].values() if r["is_active"]), groups=len(anomalous_groups(post["cs"], post["seasons"])))
        trans.commit(); report["TRANSACTION_COMMITTED"] = "YES"
    except Exception as e:
        try: trans.rollback()
        except Exception: pass
        report["TRANSACTION_ROLLED_BACK"] = "YES"; report["ABORT"] = f"{type(e).__name__}: {str(e)[:700]}"
    finally:
        conn.close()
    report["finished_utc"] = now()
    rp = f"{AUD}/repair_execution_report_{report['finished_utc']}.json"
    try: json.dump(report, open(rp, "x"), indent=1, default=str); os.chmod(rp, 0o400); report["report_path"] = rp
    except Exception as e: report["report_write_error"] = str(e)[:100]
    out(report)
    sys.exit(0 if report["TRANSACTION_COMMITTED"] == "YES" else 3)


def mode_verify(backup_path):
    from sqlalchemy import text
    man = load_manifests(); backup = json.load(open(backup_path))
    eng = engine()
    with eng.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            st = load_state(conn)
    cs, seasons, cr = st["cs"], st["seasons"], st["crounds"]
    R = []
    add = lambda n, ok, d="": R.append((n, bool(ok), d))
    active = sum(1 for r in cs.values() if r["is_active"]); ag = anomalous_groups(cs, seasons)
    add("active_contestant_seasons=3196", active == POST["active"], active)
    add("anomalous_groups=339", len(ag) == POST["groups"], len(ag))
    add("remaining_groups_equal_excluded_groups", set(ag) == {(int(r["contestant_id"]), r["level"]) for r in man["E"]})
    add("722_targets_inactive_and_only_is_active_changed", all(not cs[r["id"]]["is_active"] and {k: v for k, v in cs[r["id"]].items() if k != "is_active"} == {k: v for k, v in r.items() if k != "is_active"} for r in backup["rows"]))
    add("408_keep_active_and_exact", all(_row_evidence(r, cs, seasons, cr) is None for r in man["K"]))
    add("954_exclusion_rows_active_and_exact", all(_row_evidence(r, cs, seasons, cr) is None for r in man["E"]))
    add("total_rows_unchanged", len(cs) == BASE["total"], len(cs))
    for t in ("top_high5_results", "contestant_voting", "contestants", "contest_seasons"):
        add(f"protected_table_unchanged.{t}", list(st["fps"][t]) == backup["protected_fps"][t], st["fps"][t][0])
    add("contestant96", cs[11704]["is_active"] and not cs[14311]["is_active"] and not cs[15977]["is_active"])
    out(dict(mode="verify", **summarize(R), active=active, groups=len(ag), counts={t: st["fps"][t][0] for t in FP_TABLES},
             c96={i: cs[i]["is_active"] for i in C96}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["precheck", "backup", "execute", "verify"])
    ap.add_argument("--backup"); ap.add_argument("--backup-sha")
    a = ap.parse_args()
    {"precheck": mode_precheck, "backup": mode_backup, "execute": lambda: mode_execute(a.backup, a.backup_sha), "verify": lambda: mode_verify(a.backup)}[a.mode]()
