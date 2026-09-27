"""Phase 9: comments, messaging, advertising and interaction safety
(MyHigh5 Child/Teen Safety; Section 33 "Advertising to Minors" is truncated).

Every user, message, comment, guardian, report and ad setting here is
SYNTHETIC. No external moderation/ad provider is called and nothing touches a
real database, email, payment or KYC service.
Test ids refer to the Phase 9 required matrix (A..AD).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest

from app.core.child_safety import ContentRating as CR
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent
from app.models.comment import Comment, Report
from app.models.interaction_safety import UserBlock
from app.models.notification import Notification
from app.models.post import Post, PostComment, PostVisibility
from app.models.private_message import ConversationType, PrivateConversation, PrivateMessage
from app.models.social_group import GroupMember, GroupMemberRole, GroupType, SocialGroup
from app.services import interaction_safety as isafe
from app.services import teen_privacy
from app.services import viewer_access as va
from app.services.age_policy_engine import utc_today
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import accept_admin_review, person, verified_guardian  # noqa: F401
from tests.unit.test_phase6_content_safety import role_user
from tests.unit.test_phase7_age_safe_delivery import gov

TODAY = utc_today()
SEND = "/api/v1/feed/messages/send"
SECRET = "Private note 1234"


def adult(db, **kw):
    return person(db, 30, full_name="Adult Realname", **kw)


def minor(db, age=15, **kw):
    return person(db, age, full_name="Minor Realname", city="Arusha", **kw)


def allow_adult_dms(db, user):
    teen_privacy.set_preferences(db, user, {teen_privacy.DM_FIELD: "ALLOWED"}, on=TODAY)


def send(client, sender, recipient, text="hello"):
    return client.post(SEND, json={"recipient_id": recipient.id, "content": text}, headers=auth(sender))


def conversation(db, a, b):
    c = PrivateConversation(conversation_type=ConversationType.DIRECT, user1_id=a.id, user2_id=b.id,
                            message_count=0, unread_count_user1=0, unread_count_user2=0)
    db.add(c)
    db.commit()
    return c


def events(db, kind):
    return db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == kind).all()


def generic(r):
    body = r.json()
    detail = body.get("detail", body)
    return r.status_code == 403 and detail.get("code") == "INTERACTION_UNAVAILABLE" and "MINOR" not in r.text \
        and "BLOCK" not in r.text.upper().replace("BLOCKED_BY_ME", "")


# ===========================================================================
# MESSAGING (A-N)
# ===========================================================================

def test_A_adult_to_adult_messaging_still_works(client, db):
    a, b = adult(db), adult(db)
    r = send(client, a, b)
    assert r.status_code == 201, r.text
    back = send(client, b, a, "hi back")
    assert back.status_code == 201


def test_B_unknown_adult_to_minor_is_blocked(client, db):
    a = adult(db)
    for m in (minor(db, 14), minor(db, 16)):       # 13-15 floor PROHIBITED; 16-17 default RESTRICTED
        r = send(client, a, m)
        assert generic(r), r.text
    assert db.query(PrivateMessage).count() == 0
    assert db.query(PrivateConversation).count() == 0
    blocked = events(db, "INTERACTION_BLOCKED_SAFETY")
    assert blocked and all(e.details["reason"] == "MINOR_PROTECTION" for e in blocked)
    assert all("hello" not in json.dumps(e.details) for e in blocked)


def test_B_a_16_17_member_who_allows_adult_messages_can_be_messaged(client, db):
    a, m = adult(db), minor(db, 16)
    allow_adult_dms(db, m)
    assert send(client, a, m).status_code == 201
    m13 = minor(db, 14)
    with pytest.raises(teen_privacy.PrivacyPreferenceError):   # the 13-15 floor cannot be lowered
        allow_adult_dms(db, m13)


def test_C_direct_recipient_id_bypass_through_legacy_routes_fails(client, db):
    a, m = adult(db), minor(db)
    r = client.post(f"/api/v1/messages/conversations/direct/{m.id}", headers=auth(a))
    assert generic(r)
    assert db.query(PrivateConversation).count() == 0
    r = client.post(f"/api/v1/messages/groups/1/invite", json={"invitee_id": m.id}, headers=auth(a))
    assert r.status_code in (403, 404)


def test_D_H_existing_conversation_cannot_bypass_current_rules(client, db):
    a, m = adult(db), minor(db)
    conv = conversation(db, a, m)              # historical adult/minor conversation
    r = client.post(f"/api/v1/messages/conversations/{conv.id}/messages",
                    json={"content": "hi", "message_type": "text"}, headers=auth(a))
    assert generic(r), r.text
    assert generic(send(client, a, m))
    b = adult(db)
    conv2 = conversation(db, a, b)
    db.add(UserBlock(blocker_id=b.id, blocked_id=a.id))
    db.commit()
    for path_sender, other in ((a, b), (b, a)):   # H: blocked in both directions, also via the conversation id
        assert generic(send(client, path_sender, other))
        r = client.post(f"/api/v1/messages/conversations/{conv2.id}/messages",
                        json={"content": "hi", "message_type": "text"}, headers=auth(path_sender))
        assert generic(r)


def test_E_F_unknown_age_is_never_treated_as_adult(client, db):
    a, u1, u2, m = adult(db), person(db, None), person(db, None), minor(db)
    assert generic(send(client, a, u1))     # E: UNKNOWN recipient
    assert generic(send(client, u1, a))     # F: UNKNOWN sender
    assert generic(send(client, u1, u2))
    assert generic(send(client, u1, m))
    assert isafe.party(db, u1).protected and not isafe.party(db, u1).legal_adult


def test_minor_to_adult_creates_no_trust_and_minor_to_minor_works(client, db):
    a, m1, m2 = adult(db), minor(db, 14), minor(db, 15)
    assert generic(send(client, m1, a))       # symmetric: no reply exception is invented
    assert send(client, m1, m2).status_code == 201
    assert send(client, m2, m1).status_code == 201


def test_only_a_verified_guardian_is_a_trusted_adult(client, db, accept_admin_review):
    from app.models.guardian import Guardian

    m, parent = minor(db), adult(db)
    rel = verified_guardian(db, m)
    db.query(Guardian).filter(Guardian.id == rel.guardian_id).update({"user_id": parent.id})
    db.commit()
    assert send(client, parent, m).status_code == 201
    assert send(client, m, parent).status_code == 201
    rel.revoked_at = datetime.utcnow()
    db.commit()
    assert generic(send(client, parent, m))
    # sponsor / nominator / follower / KYC are never trust
    from app.models.follow import Follow

    stranger = adult(db, identity_verified=True)
    db.add(Follow(follower_id=m.id, following_id=stranger.id))
    db.add(Follow(follower_id=stranger.id, following_id=m.id))
    m.sponsor_id = stranger.id if hasattr(m, "sponsor_id") else None
    db.commit()
    assert generic(send(client, stranger, m))


def test_G_I_J_blocks_and_new_restrictions_keep_history(client, db):
    a, m = adult(db), minor(db, 16)
    allow_adult_dms(db, m)
    assert send(client, a, m, "first").status_code == 201
    assert send(client, m, a, "reply").status_code == 201
    before = db.query(PrivateMessage).count()
    teen_privacy.set_preferences(db, m, {teen_privacy.DM_FIELD: "RESTRICTED"}, on=TODAY)
    assert generic(send(client, a, m, "second"))          # J
    assert db.query(PrivateMessage).count() == before      # I: nothing deleted
    conv_id = db.query(PrivateConversation).one().id
    history = client.get(f"/api/v1/feed/messages/conversations/{conv_id}/messages", headers=auth(m))
    assert history.status_code == 200 and {x["content"] for x in history.json()} == {"first", "reply"}
    b = adult(db)
    assert client.post(f"/api/v1/interactions/blocks/{b.id}", headers=auth(a)).status_code == 200
    assert client.post(f"/api/v1/interactions/blocks/{b.id}", headers=auth(a)).status_code == 200  # idempotent
    assert db.query(UserBlock).count() == 1
    assert generic(send(client, b, a)) and generic(send(client, a, b))                           # G
    assert client.get(f"/api/v1/interactions/contact/{a.id}", headers=auth(b)).json() == {
        "user_id": a.id, "can_message": False, "blocked_by_me": False}                          # who blocked is hidden
    assert [x["user_id"] for x in client.get("/api/v1/interactions/blocks", headers=auth(b)).json()] == []
    client.delete(f"/api/v1/interactions/blocks/{b.id}", headers=auth(b))                       # not b's block
    assert db.query(UserBlock).count() == 1
    client.delete(f"/api/v1/interactions/blocks/{b.id}", headers=auth(a))
    assert send(client, b, a).status_code == 201
    assert events(db, "USER_BLOCKED") and events(db, "USER_UNBLOCKED")


def test_K_restricted_profile_fields_absent_from_conversation_payloads(client, db):
    a, m = adult(db), minor(db, 15)
    m2 = minor(db, 14)
    assert send(client, m2, m).status_code == 201
    conv = db.query(PrivateConversation).one()
    blob = client.get(f"/api/v1/messages/conversations/{conv.id}", headers=auth(m2)).text
    blob += client.get("/api/v1/feed/messages/conversations", headers=auth(m2)).text
    blob += client.get(f"/api/v1/users/{m.id}", headers=auth(a)).text
    for leaked in ("Minor Realname", m.email, "Arusha", "date_of_birth"):
        assert leaked not in blob


def test_L_U_notifications_use_safe_display_identity(client, db):
    m = minor(db, 15)
    owner = adult(db)
    entry = gov(db, owner, rating=CR.GENERAL)
    r = client.post(f"/api/v1/comments/{entry.id}/comments", json={"content": "Great work", "target_type": "contest"},
                    headers=auth(m))
    assert r.status_code == 200, r.text
    note = db.query(Notification).filter(Notification.user_id == owner.id).one()
    assert "Minor Realname" not in note.message and m.username in note.message
    assert r.json()["author_name"] == "Minor Realname"   # the author always sees their own name
    listing = client.get(f"/api/v1/comments/{entry.id}/comments", headers=auth(owner)).text
    assert "Minor Realname" not in listing                 # everyone else: username only
    assert isafe.safe_display_name(db, adult(db)) == "Adult Realname"


def test_text_safety_when_a_minor_is_involved(client, db):
    m1, m2 = minor(db, 14), minor(db, 15)
    r = send(client, m1, m2, "call me on +255 712 345 678")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CONTENT_NOT_ALLOWED"
    r = send(client, m1, m2, "send nudes")
    assert r.status_code == 422
    ev = events(db, "CHILD_SAFETY_ESCALATION")
    assert ev and ev[-1].risk_flag and "nudes" not in json.dumps([e.details for e in ev])
    assert db.query(PrivateMessage).count() == 0
    a, b = adult(db), adult(db)
    assert send(client, a, b, "call me on +255 712 345 678").status_code == 201   # adults: unchanged


def test_M_N_staff_report_review_is_permission_bound(client, db):
    a, b = adult(db), adult(db)
    assert send(client, a, b, SECRET).status_code == 201
    msg = db.query(PrivateMessage).one()
    r1 = client.post("/api/v1/interactions/reports", json={"target_type": "message", "target_id": msg.id,
                                                           "reason": "HARASSMENT"}, headers=auth(b))
    assert r1.status_code == 201
    dup = client.post("/api/v1/interactions/reports", json={"target_type": "message", "target_id": msg.id,
                                                            "reason": "HARASSMENT"}, headers=auth(b))
    assert dup.status_code == 200 and dup.json()["duplicate"] is True
    r2 = client.post("/api/v1/interactions/reports", json={"target_type": "user", "target_id": a.id,
                                                           "reason": "CHILD_SAFETY"}, headers=auth(b))
    assert r2.status_code == 201
    outsider = adult(db)
    assert client.post("/api/v1/interactions/reports", json={"target_type": "message", "target_id": msg.id,
                                                             "reason": "SPAM"}, headers=auth(outsider)).status_code == 404
    moderator = role_user(db, "moderate_content")
    admin = person(db, 45, admin=True)
    resolver = role_user(db, "child_safety_resolve")
    base = "/api/v1/admin/content-moderation/interaction-reports"
    for staff in (moderator, admin):                       # M/N: ordinary staff never see the child-safety report
        ids = [x["id"] for x in client.get(base, headers=auth(staff)).json()]
        assert r1.json()["id"] in ids and r2.json()["id"] not in ids
        assert client.get(f"{base}/{r2.json()['id']}", headers=auth(staff)).status_code == 404
    assert [x["id"] for x in client.get(base, headers=auth(resolver)).json()] == [r2.json()["id"]]
    evidence = client.get(f"{base}/{r1.json()['id']}", headers=auth(moderator))
    assert evidence.status_code == 200 and evidence.json()["evidence"] == SECRET   # only the reported message
    assert db.query(AuditTrail).filter(AuditTrail.action == "EVIDENCE_ACCESSED").count() == 1
    assert client.get(base, headers=auth(adult(db))).status_code == 403
    assert db.query(Notification).filter(Notification.user_id == a.id).count() == 0     # reported user not told
    assert all(SECRET not in json.dumps(e.details) for e in db.query(AgeSafetyEvent).all())
    # N: an ordinary admin is still subject to the member rules
    assert generic(send(client, admin, minor(db)))


def test_socket_identity_is_never_taken_from_the_client():
    from app.services.social_socket import social_socket_service

    assert asyncio.run(social_socket_service._authenticate_user({"user_id": 1})) is None
    assert asyncio.run(social_socket_service._authenticate_user({"token": "garbage", "user_id": 1})) is None


def test_group_add_is_direct_contact_and_member_lists_hide_private_fields(client, db):
    a, m, b = adult(db), minor(db), adult(db)
    g = SocialGroup(name="G", group_type=GroupType.PRIVATE, creator_id=a.id, member_count=1)
    db.add(g)
    db.flush()
    db.add(GroupMember(group_id=g.id, user_id=a.id, role=GroupMemberRole.OWNER))
    db.commit()
    r = client.post(f"/api/v1/feed/groups/{g.id}/members/by-username", json={"username": m.username}, headers=auth(a))
    assert generic(r)
    r = client.post(f"/api/v1/groups/{g.id}/members/add", json={"username": m.username}, headers=auth(a))
    assert generic(r)
    assert client.post(f"/api/v1/feed/groups/{g.id}/members/by-username", json={"username": b.username},
                       headers=auth(a)).status_code == 200
    m2, m3 = minor(db), minor(db)
    m2.full_name = "Other Minor"
    db.add_all([GroupMember(group_id=g.id, user_id=m2.id), GroupMember(group_id=g.id, user_id=m3.id)])
    db.commit()
    for path in (f"/api/v1/groups/{g.id}/members", f"/api/v1/feed/groups/{g.id}/members"):
        text = client.get(path, headers=auth(m3)).text
        assert m2.email not in text and b.email not in text and "Other Minor" not in text
        assert "Adult Realname" in text   # an adult's name is still shown


def test_follow_respects_blocks(client, db):
    a, b = adult(db), adult(db)
    db.add(UserBlock(blocker_id=b.id, blocked_id=a.id))
    db.commit()
    assert generic(client.post("/api/v1/follow", json={"user_id": b.id}, headers=auth(a)))


# ===========================================================================
# COMMENTS (O-W)
# ===========================================================================

def comment_on(client, user, entry, text="Nice", parent_id=None):
    body = {"content": text, "target_type": "contest"}
    if parent_id is not None:
        body["parent_id"] = parent_id
    return client.post(f"/api/v1/comments/{entry.id}/comments", json=body, headers=auth(user))


def test_O_eligible_user_can_comment(client, db):
    entry = gov(db, adult(db), rating=CR.GENERAL)
    r = comment_on(client, adult(db), entry)
    assert r.status_code == 200, r.text


def test_P_Q_R_no_comment_on_inaccessible_or_cross_entry_targets(client, db):
    held = gov(db, adult(db), exposure="HELD", state="PENDING")
    escalated = gov(db, adult(db), exposure="CHILD_SAFETY_ESCALATED", state="CHILD_SAFETY_ESCALATED", escalated=True)
    adult_only = gov(db, adult(db), rating=CR.ADULT_18_PLUS)
    viewer = adult(db)
    for entry in (held, escalated):                       # P / R
        assert comment_on(client, viewer, entry).status_code == 404
    assert comment_on(client, minor(db), adult_only).status_code in (403, 404)
    public = gov(db, adult(db), rating=CR.GENERAL)
    other = gov(db, adult(db), rating=CR.GENERAL)
    parent = Comment(user_id=viewer.id, contestant_id=other.id, content="elsewhere")
    hidden = Comment(user_id=viewer.id, contestant_id=public.id, content="hidden", is_hidden=True)
    db.add_all([parent, hidden])
    db.commit()
    assert comment_on(client, viewer, public, parent_id=parent.id).status_code == 404   # Q: cross-entry reply
    assert comment_on(client, viewer, public, parent_id=hidden.id).status_code == 404
    assert db.query(Comment).filter(Comment.contestant_id == public.id).count() == 1


def test_S_T_comment_payloads_use_the_safe_profile(client, db):
    entry = gov(db, adult(db), rating=CR.GENERAL)
    m = minor(db)
    assert comment_on(client, m, entry).status_code == 200
    listing = client.get(f"/api/v1/comments/{entry.id}/comments", headers=auth(adult(db))).text
    assert "Minor Realname" not in listing and m.email not in listing and "Arusha" not in listing


def test_V_child_safety_comment_path(client, db):
    owner = minor(db)
    entry = gov(db, owner, rating=CR.GENERAL)
    r = comment_on(client, adult(db), entry, "so sexy")
    assert r.status_code == 422 and "sexy" not in r.text
    assert events(db, "CHILD_SAFETY_ESCALATION")[-1].risk_flag
    assert db.query(Comment).count() == 0


def test_W_blocks_and_reports_on_comments(client, db):
    owner, commenter = adult(db), adult(db)
    entry = gov(db, owner, rating=CR.GENERAL)
    db.add(UserBlock(blocker_id=owner.id, blocked_id=commenter.id))
    db.commit()
    assert generic(comment_on(client, commenter, entry))
    third = adult(db)
    c = comment_on(client, third, entry).json()
    rep = client.post("/api/v1/interactions/reports", json={"target_type": "comment", "target_id": c["id"],
                                                            "reason": "SPAM"}, headers=auth(owner))
    assert rep.status_code == 201
    row = db.query(Report).get(rep.json()["id"])
    assert row.comment_id == c["id"] and row.contestant_id is None       # stays out of the legacy list
    assert db.query(Notification).filter(Notification.user_id == third.id,
                                         Notification.message.like("%report%")).count() == 0


def test_like_requires_entry_access(client, db):
    held = gov(db, adult(db), exposure="HELD", state="PENDING")
    c = Comment(user_id=held.user_id, contestant_id=held.id, content="x")
    db.add(c)
    db.commit()
    assert client.post(f"/api/v1/comments/comment/{c.id}/like", headers=auth(adult(db))).status_code == 404


def test_post_comments_respect_visibility_blocks_and_text_rules(client, db):
    m, a, b = minor(db), adult(db), adult(db)
    post = Post(author_id=m.id, content="my drawing", visibility=PostVisibility.PUBLIC)
    other = Post(author_id=b.id, content="x", visibility=PostVisibility.PUBLIC)
    private = Post(author_id=b.id, content="x", visibility=PostVisibility.PRIVATE)
    db.add_all([post, other, private])
    db.commit()
    for base in ("/api/v1/social/posts", "/api/v1/feed/posts"):
        r = client.post(f"{base}/{post.id}/comments", json={"content": "text me at 0712345678"}, headers=auth(a))
        assert r.status_code == 422
        assert client.post(f"{base}/{private.id}/comments", json={"content": "hi"}, headers=auth(a)).status_code == 404
    oc = PostComment(post_id=other.id, author_id=b.id, content="x")
    db.add(oc)
    db.add(UserBlock(blocker_id=b.id, blocked_id=a.id))
    db.commit()
    assert client.post(f"/api/v1/feed/posts/{post.id}/comments", json={"content": "hi", "parent_id": oc.id},
                       headers=auth(a)).status_code == 404
    assert generic(client.post(f"/api/v1/social/posts/{other.id}/comments", json={"content": "hi"}, headers=auth(a)))


# ===========================================================================
# ADVERTISING (X-AD) - operator-declared source ratings; nothing invented
# ===========================================================================

def eligibility(client, user=None):
    r = client.get("/api/v1/ads/eligibility", headers=auth(user) if user else {})
    assert r.status_code == 200 and "no-store" in r.headers.get("cache-control", "")
    return r.json()["sources"]


def test_X_Y_Z_AA_unclassified_sources_only_reach_confirmed_adults(client, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AD_SOURCE_RATINGS", "")
    assert all(eligibility(client, adult(db)).values())                          # X
    for viewer in (minor(db, 14), minor(db, 17), person(db, None), None):        # Y, Z, AA
        assert not any(eligibility(client, viewer).values())


def test_declared_ratings_follow_phase7_rating_rules(client, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AD_SOURCE_RATINGS", json.dumps(
        {"adsense": "GENERAL", "annualads_rotator": "ADULT_18_PLUS", "annualads_sponsor": "TEEN_16_PLUS"}))
    assert eligibility(client) == {"adsense": True, "annualads_rotator": False, "annualads_sponsor": False}
    assert eligibility(client, minor(db, 16)) == {"adsense": True, "annualads_rotator": False, "annualads_sponsor": True}
    assert eligibility(client, adult(db)) == {"adsense": True, "annualads_rotator": True, "annualads_sponsor": True}
    monkeypatch.setattr(settings, "AD_SOURCE_RATINGS", "{not json")
    assert not any(eligibility(client).values())                                 # invalid config fails closed
    monkeypatch.setattr(settings, "AD_SOURCE_RATINGS", json.dumps({"adsense": "PROHIBITED"}))
    assert eligibility(client)["adsense"] is False


def test_AB_AD_sponsor_sso_is_not_sent_for_minors_and_adds_no_new_attributes(client, db, monkeypatch):
    from app.core.config import settings
    from jose import jwt

    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", True)
    monkeypatch.setattr(settings, "ANNUALADS_SSO_SECRET", "synthetic-secret-synthetic-secret")
    monkeypatch.setattr(settings, "ANNUALADS_TENANT_ID", "tenant")
    monkeypatch.setattr(settings, "AD_SOURCE_RATINGS", "")
    for viewer in (minor(db), person(db, None)):
        r = client.get("/api/v1/sponsor-embed/sso-token", headers=auth(viewer))
        assert r.status_code == 403 and viewer.email not in r.text
    r = client.get("/api/v1/sponsor-embed/sso-token", headers=auth(adult(db)))
    assert r.status_code == 200
    claims = jwt.decode(r.json()["token"], "synthetic-secret-synthetic-secret", algorithms=["HS256"])
    assert set(claims) == {"sub", "email", "name", "tenant_id", "exp"}          # AD: no DOB/age/location added


def test_AD_eligibility_payload_carries_booleans_only(db):
    out = isafe.ad_eligibility(db, minor(db))
    assert set(out) == set(isafe.AD_SOURCES) and all(isinstance(v, bool) for v in out.values())
    assert va.viewer_for(db, None) == va.ANONYMOUS


# ===========================================================================
# Socket relay + group messages (found on resume, 2026-09-28)
# ===========================================================================

class _FakeSio:
    def __init__(self, rooms=None):
        self.emitted, self.rooms = [], rooms or {}
        sio = self

        class _Manager:
            def get_participants(self, namespace, room):
                return ((sid, sid) for sid in sio.rooms.get(room, ()))
        self.manager = _Manager()

    async def emit(self, event, data, room=None, to=None):
        self.emitted.append((event, to or room, data))


def _socket(monkeypatch):
    from app.services import social_socket as ss
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(ss, "SessionLocal", TestingSessionLocal)
    handlers = {}

    class _Reg:
        def event(self, fn):
            handlers[fn.__name__] = fn
            return fn

    svc = ss.SocialSocketService.__new__(ss.SocialSocketService)
    svc.sio, svc.user_sessions = _Reg(), {}
    svc._register_handlers()
    svc.sio = _FakeSio()
    return svc, handlers


def test_socket_cannot_reroute_a_message_into_another_conversation(db, monkeypatch):
    svc, h = _socket(monkeypatch)
    a, b, m = adult(db), adult(db), minor(db)
    ab, am = conversation(db, a, b), conversation(db, a, m)   # am: legacy row, predates Phase 9
    msg = PrivateMessage(conversation_id=ab.id, sender_id=a.id, content="hi", message_type="text")
    db.add(msg)
    db.commit()
    svc.user_sessions["sid"] = a.id
    r = asyncio.run(h["send_private_message"]("sid", {"conversation_id": am.id, "message_id": msg.id}))
    assert "error" in r and svc.sio.emitted == []
    # Even its own conversation: a minor recipient is re-checked against CURRENT rules.
    legacy = PrivateMessage(conversation_id=am.id, sender_id=a.id, content="old", message_type="text")
    db.add(legacy)
    db.commit()
    r = asyncio.run(h["send_private_message"]("sid", {"conversation_id": am.id, "message_id": legacy.id}))
    assert "error" in r and svc.sio.emitted == []
    r = asyncio.run(h["send_private_message"]("sid", {"conversation_id": ab.id, "message_id": msg.id}))
    assert r == {"success": True} and svc.sio.emitted


def test_socket_group_relay_only_own_message_of_that_group(db, monkeypatch):
    from app.models.social_group import GroupMessage

    svc, h = _socket(monkeypatch)
    a, b = adult(db), adult(db)
    g1 = SocialGroup(name="G1", group_type=GroupType.PRIVATE, creator_id=a.id, member_count=1)
    g2 = SocialGroup(name="G2", group_type=GroupType.PRIVATE, creator_id=b.id, member_count=1)
    db.add_all([g1, g2])
    db.flush()
    db.add_all([GroupMember(group_id=g1.id, user_id=a.id), GroupMember(group_id=g2.id, user_id=b.id)])
    other = GroupMessage(group_id=g2.id, sender_id=b.id, content="g2 secret")
    db.add(other)
    db.commit()
    svc.user_sessions["sid"] = a.id
    r = asyncio.run(h["send_message"]("sid", {"group_id": g1.id, "message_id": other.id}))
    assert "error" in r and svc.sio.emitted == []


def test_group_message_text_rules_apply_when_a_minor_is_a_member(client, db):
    a, m, b = adult(db), minor(db), adult(db)
    g = SocialGroup(name="G", group_type=GroupType.PRIVATE, creator_id=a.id, member_count=2)
    db.add(g)
    db.flush()
    db.add_all([GroupMember(group_id=g.id, user_id=a.id, role=GroupMemberRole.OWNER),
                GroupMember(group_id=g.id, user_id=m.id)])
    db.commit()
    url = f"/api/v1/social/groups/{g.id}/messages"
    r = client.post(url, json={"content": "call me on +255 712 345 678"}, headers=auth(a))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CONTENT_NOT_ALLOWED"
    assert client.post(url, json={"content": "good luck everyone"}, headers=auth(a)).status_code == 201
    g2 = SocialGroup(name="G2", group_type=GroupType.PRIVATE, creator_id=a.id, member_count=2)
    db.add(g2)
    db.flush()
    db.add_all([GroupMember(group_id=g2.id, user_id=a.id), GroupMember(group_id=g2.id, user_id=b.id)])
    db.commit()
    r = client.post(f"/api/v1/social/groups/{g2.id}/messages", json={"content": "call me on +255 712 345 678"},
                    headers=auth(a))
    assert r.status_code == 201   # adults only: unchanged


# ===========================================================================
# PUBLIC GROUP INTERACTION: open membership, shared chat visible to current
# members (blocks excepted), minor-safe text rules, never trust or DM access.
# ===========================================================================

def public_group(db, owner, *members):
    g = SocialGroup(name="Public", group_type=GroupType.PUBLIC, creator_id=owner.id, member_count=1)
    db.add(g)
    db.flush()
    db.add(GroupMember(group_id=g.id, user_id=owner.id, role=GroupMemberRole.OWNER))
    for m in members:
        db.add(GroupMember(group_id=g.id, user_id=m.id))
    db.commit()
    return g


def gpost(client, user, g, text, **extra):
    return client.post(f"/api/v1/social/groups/{g.id}/messages", json={"content": text, **extra}, headers=auth(user))


def gread(client, user, g):
    r = client.get(f"/api/v1/social/groups/{g.id}/messages", headers=auth(user))
    assert r.status_code == 200
    return r


def texts(r):
    return {m["content"] for m in r.json()["messages"]}


def test_PG_A_C_N_adult_and_unknown_share_safe_group_chat_but_not_dms(client, db):
    a, u = adult(db), person(db, None)
    g = public_group(db, a)
    assert client.post(f"/api/v1/feed/groups/{g.id}/join", headers=auth(u)).status_code == 200   # joining stays open
    assert not isafe.can_contact(db, a, u).allowed           # N: UNKNOWN is never adult
    assert isafe.party(db, u).protected and not isafe.party(db, u).legal_adult
    assert gpost(client, a, g, "welcome everyone").status_code == 201
    assert gpost(client, u, g, "thanks, happy to be here").status_code == 201
    assert texts(gread(client, u, g)) == {"welcome everyone", "thanks, happy to be here"}   # A
    assert texts(gread(client, a, g)) == {"welcome everyone", "thanks, happy to be here"}
    assert generic(send(client, a, u)) and generic(send(client, u, a))                      # C: still no DM
    assert db.query(PrivateMessage).count() == 0


def test_PG_B_C_adult_and_minor_discuss_without_gaining_private_trust(client, db):
    m = minor(db)
    g = public_group(db, m)
    a = adult(db)
    assert client.post(f"/api/v1/feed/groups/{g.id}/join", headers=auth(a)).status_code == 200
    assert gpost(client, a, g, "great entry, good luck").status_code == 201
    assert gpost(client, m, g, "thank you").status_code == 201
    assert texts(gread(client, m, g)) == texts(gread(client, a, g)) == {"great entry, good luck", "thank you"}  # B
    assert not isafe.can_contact(db, a, m).allowed and not isafe.can_contact(db, m, a).allowed   # no trust created
    assert generic(send(client, a, m))                                                     # C: DM still refused
    r = client.post(f"/api/v1/messages/conversations/direct/{m.id}", headers=auth(a))
    assert r.status_code in (403, 404, 405)
    r = client.post(f"/api/v1/feed/groups/{public_group(db, a).id}/members/by-username",
                    json={"username": m.username}, headers=auth(a))
    assert generic(r)                                          # adding them elsewhere is still direct contact
    assert db.query(PrivateMessage).count() == 0


def test_PG_O_confirmed_adult_groups_unchanged(client, db):
    a, b, c = adult(db), adult(db), adult(db)
    g = public_group(db, a, b)
    assert client.post(f"/api/v1/feed/groups/{g.id}/join", headers=auth(c)).status_code == 200
    assert gpost(client, a, g, "hello adults").status_code == 201
    assert gpost(client, c, g, "call me on +255 712 345 678").status_code == 201   # adults only: unchanged
    for u in (a, b, c):
        assert texts(gread(client, u, g)) == {"hello adults", "call me on +255 712 345 678"}


def test_PG_D_E_F_N_minor_safe_text_rules_with_minor_or_unknown_present(client, db):
    a, b, m, u = adult(db), adult(db), minor(db), person(db, None)
    for other in (m, u):                                       # D: a minor, or UNKNOWN (never adult)
        g = public_group(db, a, b, other)
        r = gpost(client, a, g, "call me on +255 712 345 678")   # E
        assert r.status_code == 422 and r.json()["detail"]["code"] == "CONTENT_NOT_ALLOWED"
        assert "Minor" not in r.text and other.username not in r.text and "UNKNOWN" not in r.text
        before = len(events(db, "CHILD_SAFETY_ESCALATION"))
        assert gpost(client, a, g, "send nudes").status_code == 422   # F: existing child-safety path
        ev = events(db, "CHILD_SAFETY_ESCALATION")
        assert len(ev) == before + 1 and ev[-1].risk_flag and ev[-1].details["channel"] == "GROUP_MESSAGE"
        assert "nudes" not in json.dumps(ev[-1].details)
    from app.models.social_group import GroupMessage
    assert db.query(GroupMessage).count() == 0                 # nothing unsafe was stored


def test_PG_G_blocks_hide_group_messages_both_ways_without_revealing(client, db):
    a, b, c = adult(db), adult(db), person(db, None)
    g = public_group(db, a, b, c)
    db.add(UserBlock(blocker_id=b.id, blocked_id=a.id))
    db.commit()
    r = gpost(client, a, g, "from a")
    assert r.status_code == 201 and "block" not in r.text.lower()   # ordinary success, nothing revealed
    assert gpost(client, b, g, "from b").status_code == 201
    assert texts(gread(client, a, g)) == {"from a"}            # the blocked side doesn't see the blocker
    assert texts(gread(client, b, g)) == {"from b"}            # the blocker doesn't see the blocked
    assert texts(gread(client, c, g)) == {"from a", "from b"}  # others unaffected
    listing = json.dumps(gread(client, a, g).json()).lower()
    assert "block" not in listing and "withheld" not in listing
    assert generic(send(client, a, b))                         # no DM bypass either


def test_PG_H_I_sender_and_viewer_must_be_current_members(client, db):
    a, b = adult(db), person(db, None)
    g = public_group(db, a, b)
    assert gpost(client, b, g, "hi").status_code == 201
    assert client.delete(f"/api/v1/feed/groups/{g.id}/leave", headers=auth(b)).status_code == 200
    assert gpost(client, b, g, "still here?").status_code == 403                                   # H
    assert client.get(f"/api/v1/social/groups/{g.id}/messages", headers=auth(b)).status_code == 403  # I


def test_PG_J_M_forged_ids_and_history_untouched(client, db):
    from app.models.social_group import GroupMessage

    a, b, m = adult(db), adult(db), minor(db)
    g1, g2 = public_group(db, a, b), public_group(db, m)
    other = GroupMessage(group_id=g2.id, sender_id=m.id, content="g2 only")
    db.add(other)
    db.commit()
    before = [(x.id, x.content, x.sender_id, x.is_deleted) for x in db.query(GroupMessage).order_by(GroupMessage.id)]
    assert gpost(client, a, g2, "x").status_code == 403                                   # not a member
    assert client.get(f"/api/v1/social/groups/{g2.id}/messages", headers=auth(a)).status_code == 403
    assert gpost(client, a, g1, "x", reply_to_id=other.id).status_code == 404             # cross-group reply
    assert gpost(client, a, g1, "x", reply_to_id=999999).status_code == 404               # nonexistent reply
    assert client.post(f"/api/v1/social/messages/{other.id}/read", headers=auth(a)).status_code == 404
    assert client.post(f"/api/v1/social/messages/999999/read", headers=auth(a)).status_code == 404
    db.add(UserBlock(blocker_id=m.id, blocked_id=b.id))
    db.commit()
    assert client.post(f"/api/v1/feed/groups/{g2.id}/join", headers=auth(b)).status_code == 200
    assert client.post(f"/api/v1/social/messages/{other.id}/read", headers=auth(b)).status_code == 404  # blocked
    assert gpost(client, b, g2, "x", reply_to_id=other.id).status_code == 404
    db.expire_all()
    after = [(x.id, x.content, x.sender_id, x.is_deleted) for x in db.query(GroupMessage).order_by(GroupMessage.id)]
    assert after == before                                     # M: history unchanged


def test_PG_K_L_socket_uses_the_same_group_decision_as_http(client, db, monkeypatch):
    from app.models.social_group import GroupMessage

    svc, h = _socket(monkeypatch)
    a, b, m, u, x = adult(db), adult(db), minor(db), person(db, None), adult(db)
    g = public_group(db, a, b, m, u, x)
    outsider = adult(db)
    db.add(UserBlock(blocker_id=x.id, blocked_id=a.id))
    msg = GroupMessage(group_id=g.id, sender_id=a.id, content="adult says hi")
    db.add(msg)
    db.commit()
    sockets = {"sa": a, "sb": b, "sm": m, "su": u, "sx": x, "so": outsider}
    svc.user_sessions.update({sid: usr.id for sid, usr in sockets.items()})
    svc.sio = _FakeSio({f"group_{g.id}": list(sockets)})
    assert asyncio.run(h["send_message"]("sa", {"group_id": g.id, "message_id": msg.id})) == {"success": True}
    got = {to for _, to, _ in svc.sio.emitted}
    assert got == {"sa", "sb", "sm", "su"}                     # L: not the blocked member, not a stale non-member
    assert all(not str(to).startswith("group_") for to in got)  # never a shared room broadcast
    http = {sid for sid, usr in sockets.items() if usr is not outsider
            and "adult says hi" in texts(gread(client, usr, g))}
    assert http == got                                         # K: HTTP reads and socket delivery agree
    svc.sio.emitted.clear()                                    # forged ids
    assert "error" in asyncio.run(h["send_message"]("sb", {"group_id": g.id, "message_id": msg.id}))
    assert "error" in asyncio.run(h["send_message"]("sa", {"group_id": g.id + 999, "message_id": msg.id}))
    assert "error" in asyncio.run(h["send_message"]("so", {"group_id": g.id, "message_id": msg.id}))
    assert asyncio.run(h["message_read"]("sx", {"message_id": msg.id})) == {"success": False}
    assert asyncio.run(h["message_read"]("so", {"message_id": msg.id})) == {"success": False}
    assert svc.sio.emitted == []
    assert asyncio.run(h["message_read"]("sm", {"message_id": msg.id})) == {"success": True}
    assert {to for _, to, _ in svc.sio.emitted} == {"sa", "sb", "sm", "su"}
    svc.sio.emitted.clear()                                    # the REST notification uses the same emitter
    asyncio.run(svc.emit_group_safe(g.id, [a.id], "new_message", {"content": "adult says hi"}))
    assert {to for _, to, _ in svc.sio.emitted} == got


def test_PG_socket_fails_closed_without_room_information(db, monkeypatch):
    svc, _h = _socket(monkeypatch)
    a, b = adult(db), adult(db)
    g = public_group(db, a, b)
    fake = _FakeSio()

    class _Broken:
        def get_participants(self, *_):
            raise RuntimeError("no rooms")
    fake.manager = _Broken()
    svc.sio, svc.user_sessions = fake, {"sb": b.id}
    asyncio.run(svc.emit_group_safe(g.id, [a.id], "new_message", {}))
    assert fake.emitted == []
