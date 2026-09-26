"""Content classification, moderation and child-safety pipeline (Child/Teen
Safety Phase 6: s.10, s.11, s.15, s.16, s.18).

One service decides the CONTENT side of publication; Phase 5
(app.services.contest_eligibility) decides PARTICIPATION eligibility and
composes both into the single authoritative exposure decision. Public
exposure of a governed entry requires both:

    participation eligible (age, rules, policy, guardian, rights, metadata)
    AND content APPROVED (with a non-PROHIBITED rating permitted for the
        subject and the contest)
    AND no unresolved child-safety escalation.

Ratings: the Phase 2 ContentRating vocabulary only
(GENERAL, TEEN_13_PLUS, TEEN_16_PLUS, ADULT_18_PLUS, PROHIBITED).

Coverage, not absence of findings: every safety dimension Phase 6 is
responsible for (CoverageDimension) records an explicit CoverageStatus. An
automated approval is possible only when EVERY dimension is
COMPLETED_NO_FINDING or NOT_APPLICABLE, there is no finding at all, the subject
is a determined adult, and the submission has checkable content. A dimension
that was NOT_RUN, NOT_SUPPORTED or FAILED (provider not configured or not
permitted, errors, external links, hosted video, unsanitized images...) keeps
the entry private for human review. "Nothing detected" is never confused with
"not evaluated", and a classifier outage is never an approval.

Child safety (s.11): sexual/nude/exploitative content involving or possibly
involving a minor is CHILD_SAFETY_ESCALATED - never an ADULT_18_PLUS rating.
It is blocked immediately, only codes are stored (no content copies), ordinary
moderators cannot approve or clear it, and only a user holding the explicit
`child_safety_resolve` permission (not implied by admin or the 'all'
wildcard) can resolve it. Resolution never publishes: CONFIRMED is terminal
(PROHIBITED); NO_CHILD_SAFETY_CONCERN only returns the item to ordinary review.
No reporting workflow is implemented: Sections 1-32 do not define one.

Minor content is not sent to the external moderation provider unless
CONTENT_MODERATION_EXTERNAL_FOR_MINORS is explicitly enabled.

Historical entries get no moderation row: nothing is bulk-classified, approved
or rewritten. A pre-Phase 6 entry that is already public stays as it was; any
entry that has to BECOME public from now on needs a moderation decision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from app.core.child_safety import (
    AUTO_APPROVABLE_COVERAGE,
    CHILD_SAFETY_ESCALATION_CONCERNS,
    PERMISSION_CHILD_SAFETY_RESOLVE,
    PERMISSION_MODERATE_CONTENT,
    ChildSafetyResolution,
    ClassifierStatus,
    ContentRating,
    CoverageDimension,
    CoverageStatus,
    MemberContentStatus,
    ModerationState,
    SafetyConcern,
)
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.media import Media

CLASSIFIER_VERSION = "p6-rules-2"

RATING_ORDER = [ContentRating.GENERAL, ContentRating.TEEN_13_PLUS, ContentRating.TEEN_16_PLUS,
                ContentRating.ADULT_18_PLUS, ContentRating.PROHIBITED]

# Proposed (never final) rating implied by a finding. PII/state findings imply none.
_FINDING_RATING = {
    SafetyConcern.OFFENSIVE_LANGUAGE: ContentRating.TEEN_13_PLUS,
    SafetyConcern.WEAPONS: ContentRating.TEEN_13_PLUS,
    SafetyConcern.VIOLENCE: ContentRating.TEEN_16_PLUS,
    SafetyConcern.DANGEROUS_BEHAVIOR: ContentRating.TEEN_16_PLUS,
    SafetyConcern.GRAPHIC_VIOLENCE: ContentRating.ADULT_18_PLUS,
    SafetyConcern.SEXUAL_CONTENT: ContentRating.ADULT_18_PLUS,
    SafetyConcern.HATE: ContentRating.PROHIBITED,
    SafetyConcern.CHILD_SEXUAL_CONTENT: ContentRating.PROHIBITED,
}


def max_rating(ratings: Iterable[Optional[ContentRating]]) -> Optional[ContentRating]:
    present = [r for r in ratings if r is not None]
    return max(present, key=RATING_ORDER.index) if present else None


def rating_exceeds(rating: Optional[ContentRating], ceiling: Optional[ContentRating]) -> bool:
    return bool(rating and ceiling and RATING_ORDER.index(rating) > RATING_ORDER.index(ceiling))


# ---------------------------------------------------------------------------
# Deterministic detectors (text). Not perfect by design: they only ever hold
# content for review; they never approve anything.
# ---------------------------------------------------------------------------

_TEXT_PATTERNS = (
    (SafetyConcern.PII_EMAIL, re.compile(r"[A-Za-z0-9._%+-]+\s*(?:@|\(at\)|\[at\])\s*[A-Za-z0-9.-]+\s*(?:\.|\(dot\)|\[dot\])\s*[A-Za-z]{2,}",
                                         re.IGNORECASE)),
    (SafetyConcern.PII_PHONE, re.compile(r"(?:\+?\d[\s().-]?){8,}\d")),
    (SafetyConcern.PRECISE_LOCATION, re.compile(r"-?\d{1,2}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")),
    (SafetyConcern.PRECISE_LOCATION, re.compile(
        r"(?:google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps|maps\.apple\.com|openstreetmap\.org/|///[a-z]+\.[a-z]+\.[a-z]+)",
        re.IGNORECASE)),
    (SafetyConcern.HOME_ADDRESS, re.compile(
        r"\b\d{1,5}\s+(?:[A-Za-z]+\s){0,3}(?:street|st\.|avenue|ave\.?|road|rd\.?|lane|boulevard|blvd|drive|"
        r"rue|calle|avenida|strasse|straße)\b", re.IGNORECASE)),
    (SafetyConcern.HOME_ADDRESS, re.compile(r"\b(?:my|our)\s+(?:home\s+)?address\s+is\b|\bi\s+live\s+at\b",
                                            re.IGNORECASE)),
    (SafetyConcern.SCHOOL_INFORMATION, re.compile(
        r"\b(?:school|high\s+school|primary\s+school|secondary\s+school|middle\s+school|academy|"
        r"école|ecole|lycée|lycee|collège|escuela|colegio)\b", re.IGNORECASE)),
    (SafetyConcern.SCHOOL_INFORMATION, re.compile(r"\b(?:grade|form|year)\s+\d{1,2}\s+(?:at|in)\b|\bclass\s+of\s+20\d\d\b",
                                                  re.IGNORECASE)),
)


def detect_text_concerns(text: Optional[str]) -> Set[SafetyConcern]:
    """Deterministic PII/location/school findings for entry text (codes only)."""
    found: Set[SafetyConcern] = set()
    for concern, pattern in _TEXT_PATTERNS:
        if text and pattern.search(text):
            found.add(concern)
    return found


# Deterministic harm rules for text (TEXT_HARM). Deliberately broad: a match only
# ever sends the entry to human review; it never approves or rejects anything.
_SEXUAL_TEXT = re.compile(r"\b(?:nudes?|naked|nsfw|porn\w*|xxx|sex(?:y|ual)?|onlyfans|erotic\w*|strip(?:tease|per)s?|"
                          r"lingerie|explicit)\b", re.IGNORECASE)
_HARM_TEXT = (
    (SafetyConcern.VIOLENCE, re.compile(r"\b(?:kill\w*|murder\w*|shoot(?:ing)?|stab\w*|bomb\w*|gun\w*|weapons?)\b",
                                        re.IGNORECASE)),
    (SafetyConcern.DANGEROUS_BEHAVIOR, re.compile(
        r"\b(?:drugs?|cocaine|heroin|meth|weed|overdose|suicid\w*|self[- ]?harm\w*)\b", re.IGNORECASE)),
)


def detect_text_harm(text: Optional[str], *, possibly_minor: bool) -> Set[SafetyConcern]:
    """Sexual text with a possibly-minor subject is CHILD_SEXUAL_CONTENT (s.11)."""
    found: Set[SafetyConcern] = set()
    if not text:
        return found
    if _SEXUAL_TEXT.search(text):
        found.add(SafetyConcern.CHILD_SEXUAL_CONTENT if possibly_minor else SafetyConcern.SEXUAL_CONTENT)
    for concern, pattern in _HARM_TEXT:
        if pattern.search(text):
            found.add(concern)
    return found


def _text_language(text: str) -> Set[SafetyConcern]:
    """Local profanity/spam rules of the existing moderation service (no network)."""
    from app.services.content_moderation import content_moderation_service

    return concerns_from_moderation([content_moderation_service.moderate_text(text)], possibly_minor_subject=False)


_FLAG_TO_FINDING = {
    "violence": SafetyConcern.VIOLENCE,
    "gore": SafetyConcern.GRAPHIC_VIOLENCE,
    "weapons": SafetyConcern.WEAPONS,
    "drugs": SafetyConcern.DANGEROUS_BEHAVIOR,
    "hate": SafetyConcern.HATE,
    "offensive": SafetyConcern.OFFENSIVE_LANGUAGE,
    "spam": SafetyConcern.SPAM,
}


def concerns_from_moderation(results: Iterable, *, possibly_minor_subject: bool) -> Set[SafetyConcern]:
    """Map moderation results (provider or local text rules) to findings. Sexual
    content with a possibly-minor subject is CHILD_SEXUAL_CONTENT (s.11), never
    an adult rating."""
    found: Set[SafetyConcern] = set()
    for result in results or ():
        for flag in getattr(result, "flags", None) or ():
            kind = getattr(getattr(flag, "type", None), "value", getattr(flag, "type", None))
            if kind == "adult":
                found.add(SafetyConcern.CHILD_SEXUAL_CONTENT if possibly_minor_subject else SafetyConcern.SEXUAL_CONTENT)
            elif kind in _FLAG_TO_FINDING:
                found.add(_FLAG_TO_FINDING[kind])
    return found


def result_completed(result) -> bool:
    """A provider result counts as a real classification only when it was not
    skipped, errored or failed closed."""
    details = getattr(result, "details", None) or {}
    return not any(details.get(k) for k in ("skipped", "error", "fail_closed"))


# ---------------------------------------------------------------------------
# Media references
# ---------------------------------------------------------------------------

def _refs(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = [raw]
    if not isinstance(parsed, list):
        parsed = [parsed]
    return [str(x).strip() for x in parsed if str(x).strip()]


def hosted_media(db: Session, ref: str):
    """(is_hosted_by_myhigh5, Media row if resolvable)."""
    if ref.isdigit():
        return True, db.query(Media).filter(Media.id == int(ref)).first()
    if "/api/v1/media/" in ref:
        path = ref[ref.index("/api/v1/media/"):]
        return True, db.query(Media).filter(Media.url.in_([ref, path])).first()
    if ref.startswith(("http://", "https://")):
        media = db.query(Media).filter(Media.url == ref).first()
        return (True, media) if media is not None else (False, None)
    return True, None


# ---------------------------------------------------------------------------
# Content gate (what Phase 5 composition consumes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassifierRun:
    """What media classification actually did for one submission (built by the
    caller that invoked the provider). media_results are the provider results
    for hosted media only."""

    status: ClassifierStatus = ClassifierStatus.NOT_RUN
    media_total: int = 0
    media_classified: int = 0
    media_failed: int = 0
    media_results: tuple = ()


@dataclass(frozen=True)
class ContentGate:
    state: ModerationState
    rating: Optional[ContentRating] = None
    proposed_rating: Optional[ContentRating] = None
    findings: frozenset = frozenset()
    classifier_status: ClassifierStatus = ClassifierStatus.NOT_RUN
    human_review_required: bool = True
    update_required: bool = False
    child_safety_escalated: bool = False
    automated: bool = False
    governed: bool = True          # False only for a pre-Phase 6 entry that is already public
    coverage: tuple = ()           # ((CoverageDimension, CoverageStatus), ...)

    def coverage_map(self) -> dict:
        return dict(self.coverage)

    @property
    def coverage_complete(self) -> bool:
        cov = self.coverage_map()
        return bool(cov) and all(cov.get(d) in AUTO_APPROVABLE_COVERAGE for d in CoverageDimension)

    @property
    def approved(self) -> bool:
        return (self.state == ModerationState.APPROVED and self.rating is not None
                and self.rating != ContentRating.PROHIBITED and not self.child_safety_escalated)

    @property
    def publishable(self) -> bool:
        return (not self.governed) or self.approved

    @classmethod
    def legacy_public(cls, findings: Iterable[SafetyConcern] = ()) -> "ContentGate":
        """A historical entry that was already public before Phase 6. Not
        reviewed, not approved - simply not rewritten (s.17 of the brief)."""
        return cls(state=ModerationState.APPROVED, findings=frozenset(findings), human_review_required=False,
                   governed=False)


def _hosted_refs(db: Session, refs: List[str]):
    out = []
    for ref in refs:
        is_hosted, media = hosted_media(db, ref)
        out.append((ref, is_hosted, media))
    return out


def classify(db: Session, *, title: Optional[str], description: Optional[str], image_media_ids: Optional[str],
             video_media_ids: Optional[str], moderation_results: Sequence = (), extra_concerns: Iterable = (),
             possibly_minor: bool, determined_adult: bool, run: Optional[ClassifierRun] = None) -> ContentGate:
    """Automated assessment of one submission with explicit per-dimension
    coverage (not persisted)."""
    run = run or ClassifierRun()
    cov = {}
    findings: Set[SafetyConcern] = set(extra_concerns)
    # Signals supplied by the caller (e.g. admin/synthetic, or earlier moderation results).
    findings |= concerns_from_moderation(moderation_results, possibly_minor_subject=possibly_minor)

    # --- text dimensions (deterministic, local) -------------------------------------------
    text = " ".join(x for x in (title, description) if x and x.strip())
    for dim, detector in ((CoverageDimension.TEXT_PERSONAL_INFORMATION, lambda t: detect_text_concerns(t)),
                          (CoverageDimension.TEXT_HARM, lambda t: detect_text_harm(t, possibly_minor=possibly_minor)),
                          (CoverageDimension.TEXT_LANGUAGE, _text_language)):
        if not text:
            cov[dim] = CoverageStatus.NOT_APPLICABLE
            continue
        try:
            found = detector(text)
        except Exception:  # noqa: BLE001 - a failed check is recorded, never treated as clean
            cov[dim] = CoverageStatus.FAILED
            continue
        findings |= found
        cov[dim] = CoverageStatus.COMPLETED_FINDING if found else CoverageStatus.COMPLETED_NO_FINDING

    # --- media dimensions ------------------------------------------------------------------
    images = _hosted_refs(db, _refs(image_media_ids))
    videos = _hosted_refs(db, _refs(video_media_ids))
    all_media = images + videos
    hosted = [m for m in all_media if m[1]]
    if not all_media:
        cov[CoverageDimension.MEDIA_CONTENT] = CoverageStatus.NOT_APPLICABLE
    elif len(hosted) < len(all_media):
        cov[CoverageDimension.MEDIA_CONTENT] = CoverageStatus.NOT_SUPPORTED   # external links (e.g. YouTube)
    elif run.media_failed:
        cov[CoverageDimension.MEDIA_CONTENT] = CoverageStatus.FAILED
    elif (run.status != ClassifierStatus.COMPLETED
          or run.media_classified < max(len(hosted), run.media_total)):
        # Not every hosted item was classified (provider unavailable/not permitted/partial).
        cov[CoverageDimension.MEDIA_CONTENT] = CoverageStatus.NOT_RUN
    else:
        media_found = concerns_from_moderation(run.media_results, possibly_minor_subject=possibly_minor)
        findings |= media_found
        cov[CoverageDimension.MEDIA_CONTENT] = (CoverageStatus.COMPLETED_FINDING if media_found
                                                else CoverageStatus.COMPLETED_NO_FINDING)
    if cov[CoverageDimension.MEDIA_CONTENT] in (CoverageStatus.NOT_SUPPORTED, CoverageStatus.NOT_RUN,
                                                CoverageStatus.FAILED):
        findings.add(SafetyConcern.UNCLASSIFIED_MEDIA)

    hosted_images = [m for m in images if m[1]]
    hosted_videos = [m for m in videos if m[1]]
    if hosted_videos:
        cov[CoverageDimension.MEDIA_METADATA] = CoverageStatus.NOT_SUPPORTED    # video stripping is Phase 7
    elif not hosted_images:
        cov[CoverageDimension.MEDIA_METADATA] = CoverageStatus.NOT_APPLICABLE
    elif all(media is not None and media.metadata_sanitized_at is not None for _, _, media in hosted_images):
        cov[CoverageDimension.MEDIA_METADATA] = CoverageStatus.COMPLETED_NO_FINDING
    else:
        cov[CoverageDimension.MEDIA_METADATA] = CoverageStatus.COMPLETED_FINDING
        findings.add(SafetyConcern.METADATA_UNVERIFIED)

    statuses = set(cov.values())
    if CoverageStatus.FAILED in statuses:
        status = ClassifierStatus.FAILED
    elif statuses <= AUTO_APPROVABLE_COVERAGE | {CoverageStatus.COMPLETED_FINDING}:
        status = ClassifierStatus.COMPLETED
    elif hosted and run.status == ClassifierStatus.UNAVAILABLE:
        status = ClassifierStatus.UNAVAILABLE
    else:
        status = ClassifierStatus.PARTIAL
    coverage = tuple(sorted(cov.items(), key=lambda kv: kv[0].value))
    proposed = max_rating([_FINDING_RATING.get(f) for f in findings]) or ContentRating.GENERAL

    if findings & CHILD_SAFETY_ESCALATION_CONCERNS:
        return ContentGate(ModerationState.CHILD_SAFETY_ESCALATED, None, ContentRating.PROHIBITED,
                           frozenset(findings), status, True, False, True, coverage=coverage)
    gate = ContentGate(ModerationState.REVIEW_REQUIRED, None, proposed, frozenset(findings), status, True,
                       coverage=coverage)
    # Safe auto-approval: COMPLETE coverage, zero findings, a determined adult,
    # and something that was actually checked. Minors always get human review.
    has_checked_content = CoverageStatus.COMPLETED_NO_FINDING in statuses
    if (determined_adult and not possibly_minor and not findings and has_checked_content
            and gate.coverage_complete):
        return replace(gate, state=ModerationState.APPROVED, rating=ContentRating.GENERAL,
                       human_review_required=False, automated=True)
    return gate


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _codes(items) -> List[str]:
    return sorted({getattr(i, "value", i) for i in items or ()})


def gate_from_row(row: ContentModeration) -> ContentGate:
    def rating(v):
        return ContentRating(v) if v else None
    return ContentGate(
        state=ModerationState(row.state), rating=rating(row.rating), proposed_rating=rating(row.proposed_rating),
        findings=frozenset(SafetyConcern(c) for c in (row.findings or ()) if c in SafetyConcern.__members__),
        classifier_status=ClassifierStatus(row.classifier_status), human_review_required=row.human_review_required,
        update_required=row.update_required, child_safety_escalated=row.child_safety_escalated,
        automated=row.automated_decision,
        coverage=tuple(sorted(((CoverageDimension(k), CoverageStatus(v)) for k, v in (row.coverage or {}).items()
                               if k in CoverageDimension.__members__ and v in CoverageStatus.__members__),
                              key=lambda kv: kv[0].value)))


def _snapshot(row: ContentModeration) -> dict:
    """Audit-safe: codes only (no content, no matched text, no evidence)."""
    return {"state": row.state, "rating": row.rating, "proposed_rating": row.proposed_rating,
            "findings": row.findings, "resolved_findings": row.resolved_findings,
            "classifier_status": row.classifier_status, "classifier_version": row.classifier_version,
            "coverage": row.coverage,
            "human_review_required": row.human_review_required, "update_required": row.update_required,
            "child_safety_escalated": row.child_safety_escalated,
            "child_safety_resolution": row.child_safety_resolution}


def _audit(db: Session, row: ContentModeration, action: str, actor_id: Optional[int], old: Optional[dict],
           reason: Optional[str] = None) -> None:
    new = _snapshot(row)
    if reason:
        new["reason_code"] = reason
    db.add(AuditTrail(table_name="content_moderation", record_id=row.id, action=action, old_values=old,
                      new_values=new, user_id=actor_id))


def record_assessment(db: Session, contestant_id: int, gate: ContentGate, *, possibly_minor: bool,
                      actor_id: Optional[int], now: datetime, action: str = "CONTENT_ASSESSED") -> ContentModeration:
    """Create (or, after the member changed the content, replace) the moderation
    record for an entry. A replacement always discards an earlier approval."""
    row = db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant_id).first()
    old = _snapshot(row) if row is not None else None
    if row is None:
        row = ContentModeration(contestant_id=contestant_id, created_at=now)
        db.add(row)
    row.state = gate.state.value
    row.rating = gate.rating.value if gate.rating else None
    row.proposed_rating = gate.proposed_rating.value if gate.proposed_rating else None
    row.findings = _codes(gate.findings)
    row.resolved_findings = []
    row.classifier_status = gate.classifier_status.value
    row.classifier_version = CLASSIFIER_VERSION
    row.coverage = {d.value: st.value for d, st in gate.coverage}
    row.human_review_required = gate.human_review_required
    row.update_required = gate.update_required
    row.subject_possibly_minor = possibly_minor
    row.child_safety_escalated = gate.child_safety_escalated
    row.child_safety_escalated_at = now if gate.child_safety_escalated else None
    row.child_safety_resolution = None
    row.automated_decision = gate.automated
    row.decided_by_user_id = None
    row.decided_at = now if gate.automated else None
    row.evaluated_at = now
    row.updated_at = now
    db.flush()
    _audit(db, row, action, actor_id, old)
    return row


def moderation_for(db: Session, contestant_id: int) -> Optional[ContentModeration]:
    return db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant_id).first()


def member_status(gate: Optional[ContentGate]) -> MemberContentStatus:
    """Safe status for the entry's owner. A child-safety escalation is shown only
    as a generic hold."""
    if gate is None or not gate.governed or gate.approved:
        return MemberContentStatus.APPROVED
    if gate.child_safety_escalated:
        return MemberContentStatus.CONTENT_HELD
    if gate.state == ModerationState.PROHIBITED:
        return MemberContentStatus.PROHIBITED
    if gate.update_required:
        return MemberContentStatus.UPDATE_REQUIRED
    return MemberContentStatus.UNDER_REVIEW


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

MODERATOR_ROLE_NAME = "moderator"   # the dedicated Moderator role seeded by app.initial_data


def can_moderate(user) -> bool:
    """Ordinary content moderation: an administrator (is_admin, or the admin
    'all' permission), the dedicated Moderator role, or a role explicitly
    granted moderate_content. Ordinary users and unrelated roles cannot."""
    if user is None or not getattr(user, "is_active", True):
        return False
    if getattr(user, "is_admin", False):
        return True
    role = getattr(user, "role", None)
    if role is None:
        return False
    return bool(role.name == MODERATOR_ROLE_NAME or role.has_permission("all")
                or role.has_permission(PERMISSION_MODERATE_CONTENT))


def can_resolve_child_safety(user) -> bool:
    """Child-safety resolution: ONLY a role that explicitly holds
    child_safety_resolve (e.g. a designated Child Safety Admin, or a Super Admin
    role that was explicitly granted it). Never implied by is_admin, by the
    'all' wildcard, by moderate_content or by the Moderator role, and never
    assigned automatically to any account."""
    if user is None or not getattr(user, "is_active", True):
        return False
    role = getattr(user, "role", None)
    return bool(role and PERMISSION_CHILD_SAFETY_RESOLVE in {p.name for p in role.permissions}
                | (set(role.inherit_from.get_all_permissions()) if role.inherit_from else set()))


# ---------------------------------------------------------------------------
# Moderator actions
# ---------------------------------------------------------------------------

class ModerationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_REVIEW_SATISFIES = frozenset({SafetyConcern.THIRD_PARTY_RIGHTS, SafetyConcern.UNCLASSIFIED_MEDIA,
                               SafetyConcern.METADATA_UNVERIFIED})

MODERATOR_ACTIONS = ("APPROVE", "HOLD", "REQUEST_UPDATE", "CLASSIFY", "PROHIBIT", "ESCALATE_CHILD_SAFETY",
                     "RESOLVE_ISSUE")


def moderate(db: Session, row: ContentModeration, *, action: str, actor, reason: str,
             rating: Optional[ContentRating] = None, finding_codes: Sequence[SafetyConcern] = (),
             now: Optional[datetime] = None, today=None) -> ContentModeration:
    """Ordinary moderation. Every action is authorized, audited (codes only) and
    followed by a FULL exposure re-evaluation (age, guardian, rights, metadata
    and content), so moderation can never bypass a participation requirement."""
    now = now or datetime.utcnow()
    if not can_moderate(actor):
        raise ModerationError("FORBIDDEN", "Not allowed.")
    if action not in MODERATOR_ACTIONS:
        raise ModerationError("INVALID_ACTION", "Unknown action.")
    if row.child_safety_escalated or row.child_safety_resolution == ChildSafetyResolution.CONFIRMED.value:
        # Ordinary moderation never touches a child-safety item (including a
        # confirmed one): only the dedicated resolution path can.
        raise ModerationError("CHILD_SAFETY_LOCKED", "This item is handled by child-safety review only.")
    old = _snapshot(row)
    findings = set(row.findings or ())

    if action == "APPROVE":
        final = rating or (ContentRating(row.rating) if row.rating else None)
        if final is None:
            raise ModerationError("RATING_REQUIRED", "A content rating is required to approve.")
        if final == ContentRating.PROHIBITED:
            raise ModerationError("PROHIBITED_RATING", "PROHIBITED content cannot be approved.")
        if row.state == ModerationState.PROHIBITED.value:
            raise ModerationError("PROHIBITED", "Prohibited content cannot be approved.")
        # Pipeline-state findings are answered by the human review itself; content
        # findings must be resolved explicitly first. Rights and minor metadata
        # remain separate participation gates.
        blocking = findings - {c.value for c in _REVIEW_SATISFIES}
        if blocking:
            raise ModerationError("UNRESOLVED_FINDINGS", "Resolve or confirm every finding before approving.")
        reviewed = findings & {SafetyConcern.UNCLASSIFIED_MEDIA.value}
        row.resolved_findings = sorted(set(row.resolved_findings or ()) | reviewed)
        findings -= reviewed
        row.rating, row.state = final.value, ModerationState.APPROVED.value
        row.human_review_required, row.update_required = False, False
    elif action == "CLASSIFY":
        if rating is None:
            raise ModerationError("RATING_REQUIRED", "A content rating is required.")
        row.rating = rating.value
        if rating == ContentRating.PROHIBITED:
            row.state = ModerationState.PROHIBITED.value
        elif row.state == ModerationState.APPROVED.value:
            row.state = ModerationState.REVIEW_REQUIRED.value  # a new rating needs a new approval
    elif action in ("HOLD", "REQUEST_UPDATE"):
        row.state = ModerationState.REVIEW_REQUIRED.value
        row.human_review_required = True
        row.update_required = action == "REQUEST_UPDATE"
        findings |= {getattr(f, "value", f) for f in finding_codes}
    elif action == "PROHIBIT":
        row.state, row.rating = ModerationState.PROHIBITED.value, ContentRating.PROHIBITED.value
    elif action == "RESOLVE_ISSUE":
        codes = {getattr(f, "value", f) for f in finding_codes} or set(findings)
        codes -= {c.value for c in CHILD_SAFETY_ESCALATION_CONCERNS}
        row.resolved_findings = sorted(set(row.resolved_findings or ()) | (codes & findings))
        findings -= codes
        if row.state == ModerationState.APPROVED.value:
            row.state = ModerationState.REVIEW_REQUIRED.value
    elif action == "ESCALATE_CHILD_SAFETY":
        findings.add(SafetyConcern.CHILD_SEXUAL_CONTENT.value)
        row.state = ModerationState.CHILD_SAFETY_ESCALATED.value
        row.child_safety_escalated, row.child_safety_escalated_at = True, now
        row.rating = None
    row.findings = sorted(findings)
    row.decided_by_user_id, row.decided_at, row.automated_decision = actor.id, now, False
    row.updated_at = now
    db.flush()
    _audit(db, row, f"MODERATION_{action}", actor.id, old, reason)
    return _sync_entry(db, row, actor_id=actor.id, trigger=f"MODERATION_{action}", now=now, today=today)


def resolve_child_safety(db: Session, row: ContentModeration, *, resolution: ChildSafetyResolution, actor,
                         reason: str, now: Optional[datetime] = None, today=None) -> ContentModeration:
    """Dedicated, explicitly authorized child-safety resolution. Never publishes."""
    now = now or datetime.utcnow()
    if not can_resolve_child_safety(actor):
        raise ModerationError("FORBIDDEN", "Not allowed.")
    if not row.child_safety_escalated:
        raise ModerationError("NOT_ESCALATED", "There is no open child-safety escalation.")
    old = _snapshot(row)
    row.child_safety_resolution = resolution.value
    row.child_safety_resolved_by_user_id, row.child_safety_resolved_at = actor.id, now
    row.child_safety_escalated = False
    if resolution == ChildSafetyResolution.CONFIRMED:
        row.state, row.rating = ModerationState.PROHIBITED.value, ContentRating.PROHIBITED.value
    else:
        row.findings = sorted(set(row.findings or ()) - {c.value for c in CHILD_SAFETY_ESCALATION_CONCERNS})
        row.state, row.rating = ModerationState.REVIEW_REQUIRED.value, None
        row.human_review_required = True
    row.decided_by_user_id, row.decided_at, row.automated_decision = actor.id, now, False
    row.updated_at = now
    db.flush()
    _audit(db, row, f"CHILD_SAFETY_RESOLVED_{resolution.value}", actor.id, old, reason)
    return _sync_entry(db, row, actor_id=actor.id, trigger=f"CHILD_SAFETY_{resolution.value}", now=now,
                       today=today, release_escalation=resolution == ChildSafetyResolution.NO_CHILD_SAFETY_CONCERN)


def mark_escalated(db: Session, contestant_id: int, *, actor_id: Optional[int], now: datetime,
                   possibly_minor: bool = True) -> ContentModeration:
    """Record a child-safety escalation raised by another path (e.g. the Phase 5
    update hook or admin review). Creates the record if needed."""
    row = moderation_for(db, contestant_id)
    if row is None:
        row = record_assessment(db, contestant_id, ContentGate(ModerationState.PENDING), possibly_minor=possibly_minor,
                                actor_id=actor_id, now=now, action="CONTENT_RECORD_CREATED")
    old = _snapshot(row)
    row.findings = sorted(set(row.findings or ()) | {SafetyConcern.CHILD_SEXUAL_CONTENT.value})
    row.state, row.rating = ModerationState.CHILD_SAFETY_ESCALATED.value, None
    row.child_safety_escalated, row.child_safety_escalated_at = True, now
    row.child_safety_resolution = None
    row.updated_at = now
    db.flush()
    _audit(db, row, "CHILD_SAFETY_ESCALATED", actor_id, old)
    return row


def _sync_entry(db: Session, row: ContentModeration, *, actor_id: Optional[int], trigger: str, now: datetime,
                today=None, release_escalation: bool = False) -> ContentModeration:
    """Apply the moderation change through the ONE authoritative Phase 5
    exposure path (full re-evaluation of every gate)."""
    from app.core.child_safety import EntryExposureStatus, SafetyStatus
    from app.models.contest_eligibility import ContestEntrySafety
    from app.services import contest_eligibility as ce
    from app.services.age_policy_engine import utc_today

    entry = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == row.contestant_id).first()
    if entry is None:
        db.commit()
        db.refresh(row)
        return row
    if row.child_safety_escalated:
        if entry.exposure_status != EntryExposureStatus.CHILD_SAFETY_ESCALATED.value:
            ce.escalate_entry(db, entry, actor_id=actor_id, action=trigger, now=now, sync_moderation=False)
        db.commit()
        db.refresh(row)
        return row
    if release_escalation and entry.exposure_status == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value:
        # Back to ordinary review only (still private); re-evaluation decides the rest.
        entry.exposure_status = EntryExposureStatus.HELD.value
        entry.safety_status = SafetyStatus.REVIEW_REQUIRED.value
    if row.state == ModerationState.PROHIBITED.value and \
            entry.exposure_status == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value:
        db.commit()  # confirmed child-safety item: stays in the protected state
        db.refresh(row)
        return row
    ce.reevaluate_entry(db, entry, actor_id=actor_id, trigger=trigger, today=today or utc_today(), now=now)
    db.commit()  # re-evaluation returns early (without commit) for administrator-BLOCKED entries
    db.refresh(row)
    return row
