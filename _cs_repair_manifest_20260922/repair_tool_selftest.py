import copy, json, os, sys
os.environ["CS_AUD"] = "D:/laragon/www/mh5/_cs_repair_manifest_20260922"
sys.path.insert(0, "C:/Users/shaki/AppData/Local/Temp/claude/D--laragon-www-mh5/19f94cb2-c562-494f-bf7b-1ed677559fa7/scratchpad")
import f1_repair as R

d = json.load(open(os.environ["CS_AUD"] + "/raw_snapshot.json"))
man = R.load_manifests(verify_hash=False)
# real hash verification of the LOCAL frozen copies against the approved values
import hashlib
for n, want in R.EXPECT_HASH.items():
    assert hashlib.sha256(open(f"{os.environ['CS_AUD']}/{n}", "rb").read()).hexdigest() == want, n
print("local manifest hashes == approved values: OK")

cs = {r["id"]: dict(id=r["id"], contestant_id=r["contestant_id"], season_id=r["season_id"], is_active=bool(r["is_active"]),
                    joined_at=str(r["joined_at"]), created_at=str(r["created_at"]), updated_at=str(r["updated_at"])) for r in d["cs_all"]}
seasons = {s["id"]: (s["level"], s["round_id"]) for s in d["seasons"]}
crounds = {c["id"]: c["round_id"] for c in d["contestants"]}
votes = {(v["contestant_id"], v["season_id"]) for v in d["votes"]}
fps = {"top_high5_results": (1398, "a"), "contestant_voting": (1203, "b"), "contestants": (1073, "c"), "contest_seasons": (len(seasons), "d")}
pre = dict(cs=cs, seasons=seasons, crounds=crounds, votes=votes, fps=fps)

def post_of(pre, mutate=None, fps_override=None):
    p = copy.deepcopy(pre)
    for i in man["xid"]: p["cs"][i]["is_active"] = False
    if mutate: mutate(p)
    if fps_override: p["fps"] = fps_override
    return p

def show(name, results, expect_ok):
    s = R.summarize(results); ok = (not s["failed"]) == expect_ok
    print(("PASS " if ok else "FAIL ") + name + ("" if not s["failed"] else "  -> failed checks: " + ", ".join(n for n, _ in s["failed"])[:230]))
    return ok

allok = True
# 1. correct pre-state passes
allok &= show("check_pre on real snapshot (should pass)", R.check_pre(pre, man), True)
# 2. correct post-state passes
good_post = post_of(pre)
allok &= show("check_post on correct repair (should pass)", R.check_post(pre, good_post, man), True)
print("   post active:", sum(1 for r in good_post["cs"].values() if r["is_active"]), "| post groups:", len(R.anomalous_groups(good_post["cs"], seasons)))

xid = sorted(man["xid"]); kid = sorted(man["kid"]); eid = sorted(man["eid"])
nontarget_active = next(i for i, r in cs.items() if r["is_active"] and i not in man["xid"] and i not in man["kid"] and i not in man["eid"])
# 3. corrupted POST variants must FAIL
def m_extra(p): p["cs"][nontarget_active]["is_active"] = False
allok &= show("post: an extra non-target row deactivated", R.check_post(pre, post_of(pre, m_extra), man), False)
def m_missing(p): p["cs"][xid[0]]["is_active"] = True
allok &= show("post: one target NOT deactivated", R.check_post(pre, post_of(pre, m_missing), man), False)
def m_keep(p): p["cs"][kid[0]]["is_active"] = False
allok &= show("post: a KEEP row deactivated", R.check_post(pre, post_of(pre, m_keep), man), False)
def m_excl(p): p["cs"][eid[0]]["is_active"] = False
allok &= show("post: an EXCLUSION row deactivated", R.check_post(pre, post_of(pre, m_excl), man), False)
def m_upd(p): p["cs"][xid[1]]["updated_at"] = "2099-01-01 00:00:00"
allok &= show("post: target's updated_at also changed", R.check_post(pre, post_of(pre, m_upd), man), False)
allok &= show("post: protected table fingerprint changed", R.check_post(pre, post_of(pre, fps_override={**fps, "top_high5_results": (1398, "CHANGED")}), man), False)
allok &= show("post: protected table count changed", R.check_post(pre, post_of(pre, fps_override={**fps, "contestants": (1072, "c")}), man), False)
def m_newrow(p): p["cs"][10**9] = dict(id=10**9, contestant_id=96, season_id=254, is_active=True, joined_at="x", created_at="x", updated_at="x")
allok &= show("post: an unexpected new row appeared", R.check_post(pre, post_of(pre, m_newrow), man), False)
# 4. corrupted PRE variants must FAIL
def mut_pre(fn):
    p = copy.deepcopy(pre); fn(p); return p
allok &= show("pre: a target already inactive", R.check_pre(mut_pre(lambda p: p["cs"][xid[2]].__setitem__("is_active", False)), man), False)
allok &= show("pre: a KEEP row inactive", R.check_pre(mut_pre(lambda p: p["cs"][kid[3]].__setitem__("is_active", False)), man), False)
allok &= show("pre: target row drifted (updated_at)", R.check_pre(mut_pre(lambda p: p["cs"][xid[4]].__setitem__("updated_at", "2099-01-01")), man), False)
allok &= show("pre: contestant round changed", R.check_pre(mut_pre(lambda p: p["crounds"].__setitem__(cs[xid[5]]["contestant_id"], 999)), man), False)
allok &= show("pre: count drift (protected table)", R.check_pre(mut_pre(lambda p: p["fps"].__setitem__("contestant_voting", (1204, "b"))), man), False)
def new_active_in_group(p):
    r = cs[xid[6]]; p["cs"][10**9] = dict(id=10**9, contestant_id=r["contestant_id"], season_id=r["season_id"], is_active=True, joined_at="x", created_at="x", updated_at="x")
allok &= show("pre: extra active row in a repaired group", R.check_pre(mut_pre(new_active_in_group), man), False)
def vote_on_foreign(p): r = cs[xid[7]]; p["votes"].add((r["contestant_id"], r["season_id"]))
allok &= show("pre: a vote exists on a foreign target season", R.check_pre(mut_pre(vote_on_foreign), man), False)
def c96_bad(p): p["cs"][14311]["is_active"] = False
allok &= show("pre: contestant 96 foreign row not active", R.check_pre(mut_pre(c96_bad), man), False)
print("\nSELFTEST", "ALL PASS" if allok else "FAILURES PRESENT")
sys.exit(0 if allok else 1)
