"""Interaction safety for comments, messaging, contact actions and advertising
(Child/Teen Safety Phase 9).

ONE backend place decides whether one member may interact with another. It adds
no new age or privacy rules; it reads the existing ones:

* the viewer's CURRENT age tier and legal-adult status (Phase 2 engine through
  Phase 7 viewer_for; UNKNOWN is never adult);
* the Phase 4 privacy floor/defaults/preferences, in particular
  `unknown_adult_direct_messages` (ALLOWED / RESTRICTED / PROHIBITED), which
  Phase 4 defined for "later phases (messaging ...)" to enforce;
* Phase 4 guardian relationships (VERIFIED, not revoked) - the only reliable
  adult-minor relationship this codebase has;
* Phase 6 local text rules (no external provider is called here);
* Phase 7 content-rating delivery (allowed_ratings_for) for advertising.

Direct-contact rule (messages, conversation creation, adding someone to a group):
  A PROTECTED party (a known minor, or UNKNOWN age) and a party who is not a
  known minor (an adult, or UNKNOWN - who may be an adult) may interact only if
  the protected party's `unknown_adult_direct_messages` is ALLOWED, or the other
  party is that protected party's VERIFIED guardian. RESTRICTED is enforced like
  PROHIBITED: the codebase has no reliable "known contact" relationship (follows,
  sponsorship, nomination, same contest/city, votes, comments and KYC are NOT
  trust), so nothing can satisfy "restricted to known adults". The rule is
  symmetric: a minor starting the conversation creates no trust and no reply
  exception. Two known minors may interact subject to blocks.
Group chat is a shared interaction with its own rule (see "Group chat" below):
membership stays open, is never trust and never unlocks direct contact.
A block (either direction) stops new direct interaction. History is never
deleted or rewritten; every NEW write is checked against CURRENT state.

Public responses never contain reason codes; audit events carry codes only
(never message/comment text, DOB, guardian or child-safety evidence).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional, Set

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.child_safety import AgeSafetyEventType, AgeTier, ContentRating, SafetyConcern
from app.models.age_safety import AgeSafetyEvent
from app.models.interaction_safety import UserBlock
from app.models.user import User

logger = logging.getLogger(__name__)

MINOR_TIERS = frozenset({AgeTier.UNDER_13, AgeTier.TEEN_13_15, AgeTier.TEEN_16_17})


class Reason:
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
    SELF = "SELF"
    BLOCKED = "BLOCKED"
    MINOR_PROTECTION = "MINOR_PROTECTION"
    NOT_PARTICIPANT = "NOT_PARTICIPANT"
    CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"
    TEXT_CHILD_SAFETY = "TEXT_CHILD_SAFETY"
    TEXT_PERSONAL_INFORMATION = "TEXT_PERSONAL_INFORMATION"
    EVALUATION_FAILED = "EVALUATION_FAILED"


class Channel:
    DIRECT_MESSAGE = "DIRECT_MESSAGE"
    GROUP_ADD = "GROUP_ADD"
    GROUP_MESSAGE = "GROUP_MESSAGE"
    COMMENT = "COMMENT"
    POST_COMMENT = "POST_COMMENT"
    FOLLOW = "FOLLOW"


_GENERIC = "This interaction isn't available."
_TEXT_MESSAGES = {
    Reason.TEXT_PERSONAL_INFORMATION: "For safety, don't share contact details, addresses or exact locations here.",
    Reason.TEXT_CHILD_SAFETY: "This content can't be posted.",
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Optional[str] = None

    def client_error(self) -> dict:
        """Safe public body: never names the other person's age, settings or blocks."""
        if self.reason in _TEXT_MESSAGES:
            return {"code": "CONTENT_NOT_ALLOWED", "message": _TEXT_MESSAGES[self.reason]}
        return {"code": "INTERACTION_UNAVAILABLE", "message": _GENERIC}


ALLOWED = Decision(True)


@dataclass(frozen=True)
class Party:
    user_id: int
    tier: AgeTier
    legal_adult: bool
    unknown_adult_dm: str = "PROHIBITED"

    @property
    def protected(self) -> bool:       # known minor or UNKNOWN: minor-safe treatment
        return self.tier != AgeTier.ADULT_18_PLUS or not self.legal_adult

    @property
    def known_minor(self) -> bool:
        return self.tier in MINOR_TIERS


def _usable(user: Optional[User]) -> bool:
    return (user is not None and isinstance(getattr(user, "id", None), int)
            and bool(getattr(user, "is_active", False)) and not getattr(user, "is_deleted", False))


def party(db: Session, user: User) -> Party:
    """Current age tier + DM setting (computed live; fail closed on any error)."""
    from app.services import viewer_access as va

    try:
        viewer = va.viewer_for(db, user)
        legal_adult = ContentRating.ADULT_18_PLUS in viewer.allowed_ratings
        p = Party(user.id, viewer.tier, legal_adult, "ALLOWED")
        if p.protected:
            from app.services.age_policy_engine import utc_today
            from app.services.teen_privacy import DM_FIELD, resolve_privacy

            setting = resolve_privacy(db, user, on=utc_today()).settings.get(DM_FIELD, "PROHIBITED")
            p = Party(user.id, viewer.tier, legal_adult, setting if setting in ("ALLOWED", "RESTRICTED") else "PROHIBITED")
        return p
    except Exception as exc:  # noqa: BLE001 - never fail open
        logger.warning("Phase 9 party evaluation failed: %s", type(exc).__name__)
        return Party(user.id, AgeTier.UNKNOWN, False, "PROHIBITED")


def is_blocked(db: Session, a_id: Optional[int], b_id: Optional[int]) -> bool:
    """A block between the two members, in either direction."""
    if not a_id or not b_id:
        return False
    return db.query(UserBlock.id).filter(or_(
        and_(UserBlock.blocker_id == a_id, UserBlock.blocked_id == b_id),
        and_(UserBlock.blocker_id == b_id, UserBlock.blocked_id == a_id))).first() is not None


def blocked_user_ids(db: Session, user_id: int) -> Set[int]:
    rows = db.query(UserBlock.blocker_id, UserBlock.blocked_id).filter(
        or_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == user_id)).all()
    return {b if a == user_id else a for a, b in rows}


def is_verified_guardian(db: Session, minor_id: int, adult_id: int) -> bool:
    """The adult is a VERIFIED (not revoked) Phase 4 guardian of this minor."""
    from app.core.child_safety import GuardianVerificationStatus
    from app.models.guardian import Guardian, GuardianRelationship

    return db.query(GuardianRelationship.id).join(Guardian, Guardian.id == GuardianRelationship.guardian_id).filter(
        GuardianRelationship.minor_user_id == minor_id,
        Guardian.user_id == adult_id,
        GuardianRelationship.verification_status == GuardianVerificationStatus.VERIFIED.value,
        GuardianRelationship.revoked_at.is_(None)).first() is not None


def can_contact(db: Session, actor: Optional[User], target: Optional[User]) -> Decision:
    """Direct contact between two members (DM, conversation creation, adding the
    target to a group). Backend-authoritative; see the module docstring."""
    if not _usable(actor) or not _usable(target):
        return Decision(False, Reason.ACCOUNT_UNAVAILABLE)
    if actor.id == target.id:
        return Decision(False, Reason.SELF)
    if is_blocked(db, actor.id, target.id):
        return Decision(False, Reason.BLOCKED)
    a, t = party(db, actor), party(db, target)
    for protected, other in ((t, a), (a, t)):
        if protected.protected and not other.known_minor:
            if protected.unknown_adult_dm == "ALLOWED":
                continue
            if protected.known_minor and is_verified_guardian(db, protected.user_id, other.user_id):
                continue
            return Decision(False, Reason.MINOR_PROTECTION)
    return ALLOWED


can_message = can_contact
can_start_conversation = can_contact


def can_follow(db: Session, actor: Optional[User], target: Optional[User]) -> Decision:
    if not _usable(actor) or not _usable(target):
        return Decision(False, Reason.ACCOUNT_UNAVAILABLE)
    if actor.id == target.id:
        return Decision(False, Reason.SELF)
    if is_blocked(db, actor.id, target.id):
        return Decision(False, Reason.BLOCKED)
    return ALLOWED


# ---------------------------------------------------------------------------
# Group chat (public/social groups)
#
# Anyone may still join a public group, and membership stays open. Group chat
# is a SHARED interaction, not private contact: an accepted message is visible
# to every CURRENT member without the private-DM trusted-contact requirement
# (can_contact is NOT consulted here). Being in the same group is NOT a
# relationship and creates no trust: it never unlocks DMs, conversation
# creation, follows or profile/contact access (those keep using can_contact).
# Safety for group chat comes from (a) CURRENT membership for sending and
# reading, (b) the minor-safe text rules whenever a minor / UNKNOWN-age member
# is in the group (guard_group_message), and (c) blocks: between two members
# with a block (either direction) neither sees the other's group messages or
# read receipts. The message row is stored once and never rewritten; every
# read/emit re-evaluates CURRENT membership and blocks. Nothing tells the
# sender or a reader that a message was withheld, or why.
# ---------------------------------------------------------------------------

class GroupAudience:
    """Which group messages one member may see: everything in the group except
    messages from a member with a block either way (one request)."""

    def __init__(self, db: Session, viewer: User):
        self.viewer, self._blocked = viewer, blocked_user_ids(db, viewer.id)

    def can_see(self, sender_id: Optional[int]) -> bool:
        return sender_id is not None and (sender_id == self.viewer.id or sender_id not in self._blocked)


def is_group_member(db: Session, group_id, user_id) -> bool:
    from app.models.social_group import GroupMember

    return bool(group_id and user_id) and db.query(GroupMember.id).filter(
        GroupMember.group_id == group_id, GroupMember.user_id == user_id).first() is not None


def visible_group_message(db: Session, user: Optional[User], message_id, group_id=None):
    """A live group message the member may see: CURRENT member of THAT group
    (and of `group_id` when given) and the sender is in their audience.
    Forged/foreign/hidden ids all give None (callers answer 404)."""
    from app.models.social_group import GroupMessage

    if not _usable(user) or not message_id:
        return None
    message = db.query(GroupMessage).filter(GroupMessage.id == message_id,
                                            GroupMessage.is_deleted == False).first()  # noqa: E712
    if message is None or (group_id is not None and str(message.group_id) != str(group_id)):
        return None
    if not is_group_member(db, message.group_id, user.id):
        return None
    return message if GroupAudience(db, user).can_see(message.sender_id) else None


def group_recipient_ids(db: Session, group_id, actor_ids: Iterable[Optional[int]]) -> Set[int]:
    """CURRENT members of the group who have no block (either way) with any
    actor (message sender, reader). The same rule as GroupAudience, so HTTP
    reads and Socket.IO delivery always agree."""
    from app.models.social_group import GroupMember

    actor_ids = list(actor_ids)
    if not actor_ids or any(not a for a in actor_ids):
        return set()
    excluded = set().union(*(blocked_user_ids(db, a) for a in actor_ids))
    members = {m for (m,) in db.query(GroupMember.user_id).filter(GroupMember.group_id == group_id).all()}
    return members - excluded


def guard_group_message(db: Session, user: User, group_id: int, text: Optional[str],
                        reply_to_id: Optional[int] = None) -> None:
    """New group message: CURRENT membership; a reply only to a message of the
    same group that this member can see; minor-safe text rules whenever a
    minor / UNKNOWN-age member is CURRENTLY in the group (generic refusal that
    names nobody)."""
    from fastapi import HTTPException, status

    from app.models.social_group import GroupMember

    if not is_group_member(db, group_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Vous devez être membre du groupe pour envoyer des messages")
    if reply_to_id is not None and visible_group_message(db, user, reply_to_id, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable")
    members = db.query(User).join(GroupMember, GroupMember.user_id == User.id).filter(
        GroupMember.group_id == group_id).all()
    guard_text(db, user, text, minor_involved=participants_protected(db, [user, *members]),
               channel=Channel.GROUP_MESSAGE, target_id=group_id)


# ---------------------------------------------------------------------------
# Text (local Phase 6 rules only; nothing leaves the platform)
# ---------------------------------------------------------------------------

_PERSONAL = frozenset({SafetyConcern.PII_EMAIL, SafetyConcern.PII_PHONE, SafetyConcern.HOME_ADDRESS,
                       SafetyConcern.PRECISE_LOCATION})


def check_text(text: Optional[str], *, minor_involved: bool) -> Decision:
    """Where a minor or UNKNOWN-age member is involved: sexual text is a
    child-safety refusal (Phase 6 s.11 classification) and contact details /
    addresses / exact locations are refused (Phase 4 floor: minors' contact
    information and precise location are never public)."""
    if not minor_involved or not text:
        return ALLOWED
    from app.services.content_safety import detect_text_concerns, detect_text_harm

    if SafetyConcern.CHILD_SEXUAL_CONTENT in detect_text_harm(text, possibly_minor=True):
        return Decision(False, Reason.TEXT_CHILD_SAFETY)
    if detect_text_concerns(text) & _PERSONAL:
        return Decision(False, Reason.TEXT_PERSONAL_INFORMATION)
    return ALLOWED


def entry_subject_protected(db: Session, contestant) -> bool:
    """Is the person an entry is about a (possible) minor? Phase 5/6 records
    first; a historical entry falls back to its owner's current tier."""
    from app.models.content_moderation import ContentModeration
    from app.models.contest_eligibility import ContestEntrySafety

    if contestant is None:
        return True
    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant.id).first()
    if safety is not None and safety.subject_age_tier:
        return safety.subject_age_tier != AgeTier.ADULT_18_PLUS.value
    moderation = db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant.id).first()
    if moderation is not None and moderation.subject_possibly_minor:
        return True
    owner = db.query(User).filter(User.id == contestant.user_id).first()
    return owner is None or party(db, owner).protected


# ---------------------------------------------------------------------------
# Enforcement helpers (audit + generic HTTP error)
# ---------------------------------------------------------------------------

def record_event(db: Session, event: AgeSafetyEventType, *, actor_id: Optional[int], details: Dict[str, object],
                 decision: Optional[str] = None, risk: bool = False, commit: bool = True) -> None:
    """Codes and ids only. Own small transaction by default; never raises."""
    try:
        now = datetime.utcnow()
        db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event.value, user_id=actor_id,
                              decision=decision, risk_flag=risk, details=details))
        if commit:
            db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Phase 9 audit failed: %s", type(exc).__name__)


def enforce(db: Session, decision: Decision, *, actor_id: Optional[int], channel: str,
            target_user_id: Optional[int] = None, target_id: Optional[int] = None) -> None:
    """Raise a generic 403 (after auditing the refusal) when not allowed."""
    if decision.allowed:
        return
    from fastapi import HTTPException, status

    details = {"channel": channel, "reason": decision.reason}
    if target_user_id is not None:
        details["target_user_id"] = int(target_user_id)
    if target_id is not None:
        details["target_id"] = int(target_id)
    child = decision.reason == Reason.TEXT_CHILD_SAFETY
    record_event(db, AgeSafetyEventType.CHILD_SAFETY_ESCALATION if child else AgeSafetyEventType.INTERACTION_BLOCKED_SAFETY,
                 actor_id=actor_id, details=details, decision="BLOCKED", risk=child)
    code = status.HTTP_422_UNPROCESSABLE_ENTITY if decision.reason in _TEXT_MESSAGES else status.HTTP_403_FORBIDDEN
    raise HTTPException(status_code=code, detail=decision.client_error())


def guard_contact(db: Session, actor: User, target: Optional[User], *, channel: str) -> None:
    enforce(db, can_contact(db, actor, target), actor_id=actor.id, channel=channel,
            target_user_id=getattr(target, "id", None))


def guard_text(db: Session, actor: User, text: Optional[str], *, minor_involved: bool, channel: str,
               target_id: Optional[int] = None) -> None:
    enforce(db, check_text(text, minor_involved=minor_involved), actor_id=actor.id, channel=channel,
            target_id=target_id)


def guard_post_comment(db: Session, user: User, post, parent_id: Optional[int], text: Optional[str]) -> None:
    """Comment/reply on a social or feed post the member may already see: a
    reply must target a live comment of the SAME post; a block with the post
    author or the replied-to author stops it; minor-involved text passes the
    local safety rules."""
    from fastapi import HTTPException, status

    from app.models.post import PostComment

    parent = None
    if parent_id is not None:
        parent = db.query(PostComment).filter(PostComment.id == parent_id).first()
        if parent is None or parent.post_id != post.id or getattr(parent, "is_deleted", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    others = {post.author_id, getattr(parent, "author_id", None)} - {None, user.id}
    for other_id in others:
        if is_blocked(db, user.id, other_id):
            enforce(db, Decision(False, Reason.BLOCKED), actor_id=user.id, channel=Channel.POST_COMMENT,
                    target_id=post.id)
    people = db.query(User).filter(User.id.in_(others or {-1})).all()
    guard_text(db, user, text, minor_involved=participants_protected(db, [user, *people]),
               channel=Channel.POST_COMMENT, target_id=post.id)


def safe_display_name(db: Session, user: Optional[User], fallback: str = "Someone") -> str:
    """Name for another member's notification: real name only where that
    person's age/consent floor allows it (Phase 7), otherwise the username."""
    if user is None:
        return fallback
    from app.services.viewer_access import PrivacyCache

    if PrivacyCache(db).display(user)["name"]:
        return user.full_name or user.username or fallback
    return user.username or fallback


# ---------------------------------------------------------------------------
# Advertising (source s.33 is incomplete: only "never serve age-inappropriate
# advertisements to minors" is confirmed). Delivery is decided per ad SOURCE
# from an operator-declared rating; nothing is guessed.
# ---------------------------------------------------------------------------

AD_SOURCES = ("adsense", "annualads_rotator", "annualads_sponsor")


def declared_ad_ratings() -> Dict[str, ContentRating]:
    from app.core.config import settings

    raw = getattr(settings, "AD_SOURCE_RATINGS", "") or ""
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except ValueError:
        logger.warning("AD_SOURCE_RATINGS is not valid JSON; every ad source is treated as unclassified")
        return {}
    out = {}
    for source, value in (parsed.items() if isinstance(parsed, dict) else ()):
        try:
            rating = ContentRating(str(value))
        except ValueError:
            continue
        if rating != ContentRating.PROHIBITED:
            out[str(source)] = rating
    return out


def can_deliver_ad(viewer, source: str, ratings: Optional[Dict[str, ContentRating]] = None) -> bool:
    """A declared rating is delivered by the Phase 7 rating rules; an
    UNCLASSIFIED source only to a viewer confirmed as a legal adult (never to
    minors, UNKNOWN or anonymous viewers)."""
    ratings = declared_ad_ratings() if ratings is None else ratings
    rating = ratings.get(source)
    if rating is None:
        return ContentRating.ADULT_18_PLUS in viewer.allowed_ratings
    return rating in viewer.allowed_ratings


def ad_eligibility(db: Session, user: Optional[User]) -> Dict[str, bool]:
    from app.services import viewer_access as va

    viewer = va.viewer_for(db, user)
    ratings = declared_ad_ratings()
    return {source: can_deliver_ad(viewer, source, ratings) for source in AD_SOURCES}


def participants_protected(db: Session, users: Iterable[Optional[User]]) -> bool:
    return any(u is None or party(db, u).protected for u in users)
