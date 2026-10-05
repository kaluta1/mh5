"""Central registry of every application email event (EMAIL-1).

This is the single source of truth for event keys. Application code refers to
events through `EmailEvent`, never through ad-hoc strings. The registry holds
the DEFAULT enabled state; the database (email_event_settings) stores only
Admin overrides, so a new event gets a sane default without any seed data.

`trigger_implemented` says whether the application emits the event today.
Registering an event does not make the application send it.

Status by phase (53 events; no key has been added or renamed since EMAIL-1)
---------------------------------------------------------------------------
EMAIL-1  foundation + the events that already existed (auth, guardian, admin
         KYC approve/reject, payment confirmed, invitation, admin, support).
EMAIL-2  AUTH.EMAIL_VERIFICATION, AUTH.WELCOME, AUTH.PASSWORD_RESET,
         AUTH.PASSWORD_CHANGED on one-time links. A controlled new-account
         test on production is still to be done at final QA.
EMAIL-3  status emails that follow a COMMITTED state transition:
           KYC.ACTION_REQUIRED   identity accepted, proof of address expected
           KYC.APPROVED          now also the automatic approval path
           KYC.REJECTED          now also provider rejections (no reason sent)
           CONTEST.NOMINATION_PUBLISHED / _ACTION_REQUIRED / _REMOVED
           CONTEST.PARTICIPATION_PENDING_REVIEW / _PUBLISHED /
                                 _ACTION_REQUIRED / _REJECTED
           CONTEST.CREATIVE_UNAVAILABLE
         Emitted only by app.services.kyc_notifications and
         app.services.contest_notifications, after the commit.
         Deferred (registered, unwired): KYC.SUBMITTED, KYC.EXPIRED,
         CONTEST.NOMINATION_RESTORED, CONTEST.NOMINEE_CLAIMED,
         CONTEST.VOTING_OPEN, CONTEST.VOTING_CLOSING, CONTEST.ADVANCED,
         CONTEST.RESULT_PUBLISHED, ADMIN.KYC_REVIEW_REQUIRED,
         ADMIN.MODERATION_REVIEW_REQUIRED.
         Need a business decision first: CONTEST.NOMINEE_CLAIM_INVITATION,
         CONTEST.NOT_ADVANCED, CONTEST.WINNER.
         Intentionally unwired: AUTH.ACCOUNT_SUSPENDED, AUTH.ACCOUNT_RESTORED.
EMAIL-4  (blocked, pending payment decisions) billing, affiliate commission
         and payout events. Nothing in EMAIL-3 touches them.
EMAIL-5  provider webhooks (delivered / bounced / complained) and
         provider-side idempotency. Not started.
Open backlog outside these phases: email branding / deliverability (logo in
received mail, spam placement).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class EmailCategory(str, Enum):
    AUTH = "AUTH"
    GUARDIAN = "GUARDIAN"
    KYC = "KYC"
    CONTEST = "CONTEST"
    BILLING = "BILLING"
    AFFILIATE = "AFFILIATE"
    PAYOUT = "PAYOUT"
    ADMIN = "ADMIN"
    SUPPORT = "SUPPORT"


class EmailClassification(str, Enum):
    SECURITY = "security"
    TRANSACTIONAL = "transactional"
    MARKETING = "marketing"
    OPERATIONAL = "operational"


class EmailPhase(str, Enum):
    """Planning status from the audit."""
    NOW = "IMPLEMENT_NOW"
    LATER = "LATER"
    APPROVAL = "REQUIRES_BUSINESS_APPROVAL"


class EmailEvent(str, Enum):
    # AUTH
    AUTH_EMAIL_VERIFICATION = "AUTH.EMAIL_VERIFICATION"
    AUTH_WELCOME = "AUTH.WELCOME"
    AUTH_PASSWORD_RESET = "AUTH.PASSWORD_RESET"
    AUTH_PASSWORD_CHANGED = "AUTH.PASSWORD_CHANGED"
    AUTH_ACCOUNT_SUSPENDED = "AUTH.ACCOUNT_SUSPENDED"
    AUTH_ACCOUNT_RESTORED = "AUTH.ACCOUNT_RESTORED"
    # GUARDIAN
    GUARDIAN_CONSENT_REQUEST = "GUARDIAN.CONSENT_REQUEST"
    GUARDIAN_REGISTRATION_COMPLETION = "GUARDIAN.REGISTRATION_COMPLETION"
    # KYC
    KYC_SUBMITTED = "KYC.SUBMITTED"
    KYC_ACTION_REQUIRED = "KYC.ACTION_REQUIRED"
    KYC_APPROVED = "KYC.APPROVED"
    KYC_REJECTED = "KYC.REJECTED"
    KYC_EXPIRED = "KYC.EXPIRED"
    # CONTEST
    CONTEST_NOMINATION_PUBLISHED = "CONTEST.NOMINATION_PUBLISHED"
    CONTEST_NOMINATION_ACTION_REQUIRED = "CONTEST.NOMINATION_ACTION_REQUIRED"
    CONTEST_NOMINATION_REMOVED = "CONTEST.NOMINATION_REMOVED"
    CONTEST_NOMINATION_RESTORED = "CONTEST.NOMINATION_RESTORED"
    CONTEST_NOMINEE_CLAIM_INVITATION = "CONTEST.NOMINEE_CLAIM_INVITATION"
    CONTEST_NOMINEE_CLAIMED = "CONTEST.NOMINEE_CLAIMED"
    CONTEST_PARTICIPATION_PENDING_REVIEW = "CONTEST.PARTICIPATION_PENDING_REVIEW"
    CONTEST_PARTICIPATION_PUBLISHED = "CONTEST.PARTICIPATION_PUBLISHED"
    CONTEST_PARTICIPATION_ACTION_REQUIRED = "CONTEST.PARTICIPATION_ACTION_REQUIRED"
    CONTEST_PARTICIPATION_REJECTED = "CONTEST.PARTICIPATION_REJECTED"
    CONTEST_CREATIVE_UNAVAILABLE = "CONTEST.CREATIVE_UNAVAILABLE"
    CONTEST_VOTING_OPEN = "CONTEST.VOTING_OPEN"
    CONTEST_VOTING_CLOSING = "CONTEST.VOTING_CLOSING"
    CONTEST_ADVANCED = "CONTEST.ADVANCED"
    CONTEST_NOT_ADVANCED = "CONTEST.NOT_ADVANCED"
    CONTEST_RESULT_PUBLISHED = "CONTEST.RESULT_PUBLISHED"
    CONTEST_WINNER = "CONTEST.WINNER"
    # BILLING
    BILLING_PAYMENT_CONFIRMED = "BILLING.PAYMENT_CONFIRMED"
    BILLING_PAYMENT_FAILED = "BILLING.PAYMENT_FAILED"
    BILLING_PAYMENT_EXPIRED = "BILLING.PAYMENT_EXPIRED"
    BILLING_RECEIPT = "BILLING.RECEIPT"
    BILLING_REFUND = "BILLING.REFUND"
    BILLING_MEMBERSHIP_RENEWED = "BILLING.MEMBERSHIP_RENEWED"
    BILLING_MEMBERSHIP_EXPIRING = "BILLING.MEMBERSHIP_EXPIRING"
    # AFFILIATE (direct level 1 only)
    AFFILIATE_INVITATION = "AFFILIATE.INVITATION"
    AFFILIATE_DIRECT_REFERRAL = "AFFILIATE.DIRECT_REFERRAL"
    AFFILIATE_COMMISSION_EARNED = "AFFILIATE.COMMISSION_EARNED"
    AFFILIATE_COMMISSION_AVAILABLE = "AFFILIATE.COMMISSION_AVAILABLE"
    # PAYOUT
    PAYOUT_REQUESTED = "PAYOUT.REQUESTED"
    PAYOUT_COMPLETED = "PAYOUT.COMPLETED"
    PAYOUT_FAILED = "PAYOUT.FAILED"
    # ADMIN
    ADMIN_CONTENT_REPORT = "ADMIN.CONTENT_REPORT"
    ADMIN_CONTACT_MESSAGE = "ADMIN.CONTACT_MESSAGE"
    ADMIN_KYC_REVIEW_REQUIRED = "ADMIN.KYC_REVIEW_REQUIRED"
    ADMIN_MODERATION_REVIEW_REQUIRED = "ADMIN.MODERATION_REVIEW_REQUIRED"
    ADMIN_PAYMENT_REVIEW_REQUIRED = "ADMIN.PAYMENT_REVIEW_REQUIRED"
    ADMIN_PAYOUT_REVIEW_REQUIRED = "ADMIN.PAYOUT_REVIEW_REQUIRED"
    ADMIN_EMAIL_SYSTEM_ALERT = "ADMIN.EMAIL_SYSTEM_ALERT"
    # SUPPORT
    SUPPORT_CONTACT_CONFIRMATION = "SUPPORT.CONTACT_CONFIRMATION"
    SUPPORT_NEWSLETTER_CONFIRMATION = "SUPPORT.NEWSLETTER_CONFIRMATION"


@dataclass(frozen=True)
class EmailEventDefinition:
    key: str
    label: str
    category: EmailCategory
    classification: EmailClassification
    recipient: str
    default_enabled: bool
    critical: bool
    phase: EmailPhase
    trigger_implemented: bool
    # Shown to an Admin before a critical event is switched off.
    disable_warning: Optional[str] = None


_T = EmailClassification.TRANSACTIONAL
_S = EmailClassification.SECURITY
_M = EmailClassification.MARKETING
_O = EmailClassification.OPERATIONAL
_NOW, _LATER, _APPROVAL = EmailPhase.NOW, EmailPhase.LATER, EmailPhase.APPROVAL
E = EmailEvent


def _d(event: EmailEvent, label: str, classification: EmailClassification, recipient: str, *,
       on: bool = True, phase: EmailPhase = _NOW, live: bool = False, critical: bool = False,
       warning: Optional[str] = None) -> EmailEventDefinition:
    category = EmailCategory(event.value.split(".", 1)[0])
    return EmailEventDefinition(key=event.value, label=label, category=category, classification=classification,
                                recipient=recipient, default_enabled=on, critical=critical, phase=phase,
                                trigger_implemented=live, disable_warning=warning)


_DEFINITIONS: List[EmailEventDefinition] = [
    # ---- AUTH ----------------------------------------------------------------
    _d(E.AUTH_EMAIL_VERIFICATION, "Email verification", _S, "User", live=True, critical=True,
       warning="New members will not receive their email verification link. They cannot verify their "
               "address, and features that require a verified email (such as confirming a nomination claim) "
               "stay unavailable to them."),
    _d(E.AUTH_WELCOME, "Welcome", _T, "User", live=True),
    _d(E.AUTH_PASSWORD_RESET, "Password reset", _S, "User", live=True, critical=True,
       warning="Members who forget their password will not receive a reset link and cannot recover "
               "their account on their own."),
    _d(E.AUTH_PASSWORD_CHANGED, "Password changed", _S, "User", live=True, critical=True,
       warning="Members will no longer be told when their password changes, so an account takeover "
               "can go unnoticed."),
    _d(E.AUTH_ACCOUNT_SUSPENDED, "Account suspended", _T, "User", on=False, phase=_LATER),
    _d(E.AUTH_ACCOUNT_RESTORED, "Account restored", _T, "User", on=False, phase=_LATER),
    # ---- GUARDIAN ------------------------------------------------------------
    _d(E.GUARDIAN_CONSENT_REQUEST, "Guardian approval request", _S, "Parent or guardian", live=True, critical=True,
       warning="Parents and guardians will not receive consent requests, so a minor's registration "
               "can never be approved."),
    _d(E.GUARDIAN_REGISTRATION_COMPLETION, "Finish account (guardian approved)", _S, "Minor", live=True,
       critical=True,
       warning="A minor whose guardian has approved will not receive the link to finish creating the "
               "account, so the registration cannot be completed."),
    # ---- KYC -----------------------------------------------------------------
    _d(E.KYC_SUBMITTED, "KYC received, under review", _T, "User"),
    _d(E.KYC_ACTION_REQUIRED, "KYC action required", _T, "User", live=True),
    _d(E.KYC_APPROVED, "KYC approved", _T, "User", live=True),
    _d(E.KYC_REJECTED, "KYC rejected", _T, "User", live=True),
    _d(E.KYC_EXPIRED, "KYC expired", _T, "User", on=False, phase=_LATER),
    # ---- CONTEST -------------------------------------------------------------
    # A valid nomination is public as soon as it is submitted: there is no
    # "pending review" or "submitted" email for a nomination.
    _d(E.CONTEST_NOMINATION_PUBLISHED, "Nomination published", _T, "Nominator", live=True),
    _d(E.CONTEST_NOMINATION_ACTION_REQUIRED, "Nomination update requested", _T, "Nominator", live=True),
    _d(E.CONTEST_NOMINATION_REMOVED, "Nomination removed", _T, "Nominator", live=True),
    _d(E.CONTEST_NOMINATION_RESTORED, "Nomination restored", _T, "Nominator", on=False, phase=_LATER),
    _d(E.CONTEST_NOMINEE_CLAIM_INVITATION, "Nominee claim invitation", _T, "Nominee (non-member)", on=False,
       phase=_APPROVAL),
    _d(E.CONTEST_NOMINEE_CLAIMED, "Nominee claimed", _T, "Nominator", on=False, phase=_LATER),
    _d(E.CONTEST_PARTICIPATION_PENDING_REVIEW, "Participation under review", _T, "Entrant", live=True),
    _d(E.CONTEST_PARTICIPATION_PUBLISHED, "Participation published", _T, "Entrant", live=True),
    _d(E.CONTEST_PARTICIPATION_ACTION_REQUIRED, "Participation update required", _T, "Entrant", live=True),
    _d(E.CONTEST_PARTICIPATION_REJECTED, "Participation rejected", _T, "Entrant", live=True),
    _d(E.CONTEST_CREATIVE_UNAVAILABLE, "Video link no longer available", _T, "Entry owner", live=True),
    _d(E.CONTEST_VOTING_OPEN, "Voting open", _T, "Entrants", on=False, phase=_LATER),
    _d(E.CONTEST_VOTING_CLOSING, "Voting closing soon", _T, "Entrants", on=False, phase=_LATER),
    _d(E.CONTEST_ADVANCED, "Advanced to next stage", _T, "Entrant", on=False, phase=_LATER),
    _d(E.CONTEST_NOT_ADVANCED, "Not advanced", _T, "Entrant", on=False, phase=_APPROVAL),
    _d(E.CONTEST_RESULT_PUBLISHED, "Results published", _T, "Entrants", on=False, phase=_LATER),
    _d(E.CONTEST_WINNER, "Winner", _T, "Winner", on=False, phase=_APPROVAL),
    # ---- BILLING -------------------------------------------------------------
    _d(E.BILLING_PAYMENT_CONFIRMED, "Payment confirmed", _T, "Payer", live=True),
    _d(E.BILLING_PAYMENT_FAILED, "Payment failed", _T, "Payer", on=False, phase=_LATER),
    _d(E.BILLING_PAYMENT_EXPIRED, "Payment expired", _T, "Payer", on=False, phase=_LATER),
    _d(E.BILLING_RECEIPT, "Receipt / invoice", _T, "Payer", on=False, phase=_LATER),
    _d(E.BILLING_REFUND, "Refund", _T, "Payer", on=False, phase=_APPROVAL),
    _d(E.BILLING_MEMBERSHIP_RENEWED, "Membership renewed", _T, "Member", on=False, phase=_APPROVAL),
    _d(E.BILLING_MEMBERSHIP_EXPIRING, "Membership expiring", _T, "Member", on=False, phase=_APPROVAL),
    # ---- AFFILIATE -----------------------------------------------------------
    _d(E.AFFILIATE_INVITATION, "Referral invitation", _M, "Invitee (non-member)", live=True),
    _d(E.AFFILIATE_DIRECT_REFERRAL, "New direct referral", _T, "Sponsor", on=False, phase=_LATER),
    _d(E.AFFILIATE_COMMISSION_EARNED, "Commission earned", _T, "Sponsor", on=False, phase=_APPROVAL),
    _d(E.AFFILIATE_COMMISSION_AVAILABLE, "Commission available", _T, "Sponsor", on=False, phase=_APPROVAL),
    # ---- PAYOUT --------------------------------------------------------------
    _d(E.PAYOUT_REQUESTED, "Payout requested", _T, "Member", on=False, phase=_APPROVAL),
    _d(E.PAYOUT_COMPLETED, "Payout completed", _T, "Member", on=False, phase=_APPROVAL),
    _d(E.PAYOUT_FAILED, "Payout failed", _T, "Member", on=False, phase=_APPROVAL),
    # ---- ADMIN ---------------------------------------------------------------
    _d(E.ADMIN_CONTENT_REPORT, "Content report", _O, "Admin recipients", live=True),
    _d(E.ADMIN_CONTACT_MESSAGE, "Contact form message", _O, "Support address", live=True),
    _d(E.ADMIN_KYC_REVIEW_REQUIRED, "KYC review required", _O, "Admin recipients", on=False),
    _d(E.ADMIN_MODERATION_REVIEW_REQUIRED, "Moderation review required", _O, "Moderator recipients", on=False,
       phase=_LATER),
    _d(E.ADMIN_PAYMENT_REVIEW_REQUIRED, "Payment review required", _O, "Admin recipients", on=False,
       phase=_APPROVAL),
    _d(E.ADMIN_PAYOUT_REVIEW_REQUIRED, "Payout review required", _O, "Admin recipients", on=False,
       phase=_APPROVAL),
    _d(E.ADMIN_EMAIL_SYSTEM_ALERT, "Email delivery / provider failure", _O, "Admin recipients"),
    # ---- SUPPORT -------------------------------------------------------------
    _d(E.SUPPORT_CONTACT_CONFIRMATION, "Contact confirmation", _T, "Sender", live=True),
    _d(E.SUPPORT_NEWSLETTER_CONFIRMATION, "Newsletter confirmation", _M, "Subscriber", live=True),
]

EMAIL_EVENTS: Dict[str, EmailEventDefinition] = {d.key: d for d in _DEFINITIONS}

# Internal key of the Admin "Send test email" tool. It is a tool, not a business
# event: it has no switch and is deliberately NOT part of the registry.
TEST_EMAIL_KEY = "SYSTEM.TEST_EMAIL"

if len(EMAIL_EVENTS) != len(_DEFINITIONS) or set(EMAIL_EVENTS) != {e.value for e in EmailEvent}:
    raise RuntimeError("Email event registry is inconsistent (duplicate or missing definition)")


class UnknownEmailEvent(ValueError):
    pass


def get_event(event) -> EmailEventDefinition:
    key = event.value if isinstance(event, EmailEvent) else str(event)
    try:
        return EMAIL_EVENTS[key]
    except KeyError as exc:
        raise UnknownEmailEvent(key) from exc


def all_events() -> List[EmailEventDefinition]:
    return list(_DEFINITIONS)
