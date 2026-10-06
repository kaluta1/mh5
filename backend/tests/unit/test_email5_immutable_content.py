"""EMAIL-5 hardening: one delivery, one message.

Whatever happens between two attempts of the same delivery (the entry is
renamed or removed, the KYC state moves on, the member changes address or
language, an Admin changes the sender, the year turns), the provider receives
the same request under the same idempotency key: same recipient, sender,
subject, HTML and plain text.

Everything is SYNTHETIC. Emails go to an in-memory provider that records every
request it is handed, including the ones it answers from its idempotency
memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytest

from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET, AuthToken
from app.models.contests import Contestant
from app.models.email import EmailDelivery
from app.models.kyc import KYCStatus
from app.services import auth_tokens, email_crypto, email_providers, kyc_notifications
from app.services import email_outbox as outbox_module
from app.services import email_render
from app.services import email_settings_service as svc
from app.services import email_templates as tpl
from app.services.email import email_service
from app.services.email_events import EMAIL_EVENTS, EmailEvent
from app.services.email_outbox import STALE_PROCESSING_AFTER, claim_batch, process_outbox, provider_idempotency_key
from app.services.email_providers import FAIL_NETWORK, EmailMessage, FakeEmailProvider, ProviderResult
from app.services.email_render import LINK_CREDENTIAL, RENDERERS, RenderError, render
from tests.unit.test_email2_auth_security import A, PW2, link_token, member
from tests.unit.test_email2_auth_security import ip  # noqa: F401  (fixture)
from tests.unit.test_email3_kyc_contest import verification
from tests.unit.test_email5_provider_delivery import event as provider_event
from tests.unit.test_email5_provider_delivery import post as post_webhook
from tests.unit.test_email5_provider_delivery import stored
from tests.unit.test_email5_provider_delivery import webhook_secret  # noqa: F401  (fixture)
from tests.unit.test_held_nomination_visibility import _nominate, _safety, api_world, world  # noqa: F401  (fixtures)
from tests.unit.test_phase5_contest_eligibility import person

T0 = datetime(2026, 10, 6, 9, 0, 0)
RECLAIM = T0 + STALE_PROCESSING_AFTER + timedelta(minutes=1)
LINK_EVENTS = (EmailEvent.AUTH_EMAIL_VERIFICATION.value, EmailEvent.AUTH_PASSWORD_RESET.value)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@dataclass
class RecordingProvider(FakeEmailProvider):
    """The fake provider, keeping every request it was handed."""

    requests: List[Tuple[Optional[str], EmailMessage]] = field(default_factory=list)

    def send(self, message, *, api_key, idempotency_key=None):
        self.requests.append((idempotency_key, message))
        return super().send(message, api_key=api_key, idempotency_key=idempotency_key)

    def for_key(self, key: str) -> List[EmailMessage]:
        return [m for k, m in self.requests if k == key]


@pytest.fixture
def provider(db, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_synthetic_test_key_not_real")
    instance = RecordingProvider()
    email_providers.set_provider_factory(lambda: instance)
    try:
        yield instance
    finally:
        email_providers.set_provider_factory(None)


def delivery(db, key: str) -> EmailDelivery:
    db.expire_all()
    return db.query(EmailDelivery).filter(EmailDelivery.idempotency_key == key).one()


def accepted_then_crash(db, provider, key: str) -> EmailDelivery:
    """The provider accepts the message; the application dies before saving that."""
    claim_batch(db, now=T0, batch_size=50)
    row = delivery(db, key)
    assert outbox_module._send_one(db, row, provider, T0) == "SENT"
    db.rollback()
    row = delivery(db, key)
    assert (row.status, row.provider_message_id, row.attempt_count) == ("PROCESSING", None, 1)
    return row


def times_out(db, provider, key: str) -> EmailDelivery:
    """The first attempt reaches no answer (transient failure): it will be retried."""
    provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)]
    process_outbox(db, provider=provider, now=T0)
    row = delivery(db, key)
    assert (row.status, row.attempt_count) == ("QUEUED", 1)
    return row


def change_everything_around(db, monkeypatch, *users) -> None:
    """What a retry must not pick up: sender settings, the date, and the
    recipients' address and language."""
    row = svc.get_settings(db)
    row.id = svc.SETTINGS_ROW_ID
    row.from_name, row.reply_to, row.support_address = "Renamed Sender", "other-reply@example.com", "help2@example.com"
    db.add(row)
    monkeypatch.setattr(tpl, "current_year", lambda: 2031)
    for user in users:
        user.preferred_language = "fr" if user.preferred_language != "fr" else "de"
    db.commit()


def assert_one_identical_message(provider, row, *, attempts=2) -> EmailMessage:
    key = provider_idempotency_key(row)
    requests = provider.for_key(key)
    assert len(requests) == attempts
    first = requests[0]
    for again in requests[1:]:
        assert (again.to, again.from_header, again.reply_to) == (first.to, first.from_header, first.reply_to)
        assert again.subject == first.subject
        assert again.html.encode("utf-8") == first.html.encode("utf-8")
        assert (again.text or "").encode("utf-8") == (first.text or "").encode("utf-8")
        assert again == first
    return first


# ===========================================================================
# THE BOUNDARY IS GENERIC: no event is rendered twice
# ===========================================================================

@pytest.mark.parametrize("event_key", sorted(k for k in EMAIL_EVENTS if k in RENDERERS))
def test_no_event_is_rendered_a_second_time(db, provider, monkeypatch, event_key):
    """Every registered event, present or future, goes through the same
    boundary: the worker renders on the first attempt and sends the stored
    message afterwards, whatever the renderer would produce by then."""
    user = member(db)
    calls = []

    def renderer(db_, to, user_id, ctx, lang):
        calls.append(lang)
        n = len(calls)
        link = f" https://example.test/x#token={LINK_CREDENTIAL}" if event_key in LINK_EVENTS else ""
        return f"Subject {n}", f"<p>body {n}{link}</p>", f"text {n}{link}"

    monkeypatch.setitem(RENDERERS, event_key, renderer)
    email_service.enqueue(db, event=EmailEvent(event_key), recipient=user.email, user_id=user.id, lang="es",
                          idempotency_key="t:generic", now=T0)
    queued = delivery(db, "t:generic")
    if queued.status != "QUEUED":
        pytest.skip(f"{event_key} is switched off by default ({queued.failure_category})")
    provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)] * 2
    process_outbox(db, provider=provider, now=T0)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=30))
    row = delivery(db, "t:generic")
    assert (row.status, row.attempt_count) == ("SENT", 3)
    assert calls == ["es"]                                                    # rendered once, in the delivery's language
    first = assert_one_identical_message(provider, row, attempts=3)
    assert first.subject == "Subject 1" and "body 1" in first.html and "text 1" in first.text
    assert LINK_CREDENTIAL not in first.html + first.text                     # a link event carries its credential
    assert row.payload_ciphertext is None                                     # and nothing is kept once it is sent


def test_the_message_is_kept_encrypted_from_the_first_attempt_until_the_end(db, provider):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:kept", now=T0)
    row = delivery(db, "t:kept")
    assert email_crypto.decrypt_payload(row.payload_ciphertext) == {"to": user.email, "context": {}}   # no body while queued
    row = times_out(db, provider, "t:kept")
    payload = email_crypto.decrypt_payload(row.payload_ciphertext)
    assert set(payload) == {"to", "context", "message"}
    assert set(payload["message"]) == {"subject", "html", "text", "from", "reply_to"}
    sent = provider.for_key(provider_idempotency_key(row))[0]
    assert (payload["message"]["subject"], payload["message"]["html"]) == (sent.subject, sent.html)
    for column in EmailDelivery.__table__.columns:                            # never in the clear
        assert sent.subject not in str(getattr(row, column.name)) and "<html" not in str(getattr(row, column.name)).lower()
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    row = delivery(db, "t:kept")
    assert row.status == "SENT" and row.payload_ciphertext is None


def test_a_delivery_queued_before_this_change_is_frozen_on_its_next_attempt(db, provider, monkeypatch):
    """Rows already in the outbox at deployment carry no message yet."""
    user = member(db, verified=True)
    now = T0
    old = EmailDelivery(event_key="KYC.APPROVED", category="KYC", user_id=user.id, recipient_masked="m***@e***.com",
                        lang="en", status="QUEUED", attempt_count=0, idempotency_key="t:old", next_attempt_at=now,
                        payload_ciphertext=email_crypto.encrypt_payload({"to": user.email, "context": {}}),
                        created_at=now, updated_at=now)
    db.add(old)
    db.commit()
    row = times_out(db, provider, "t:old")
    change_everything_around(db, monkeypatch, user)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    assert_one_identical_message(provider, delivery(db, "t:old"))


# ===========================================================================
# RECIPIENT AND LANGUAGE
# ===========================================================================

def test_recipient_and_language_are_those_of_the_delivery(db, provider, monkeypatch):
    user = member(db, verified=True, preferred_language="fr")
    address = user.email
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=address, user_id=user.id, lang="fr",
                          idempotency_key="t:who", now=T0)
    # the account changes address and language BEFORE the first attempt ...
    user.email, user.preferred_language = "moved@example.com", "en"
    db.commit()
    row = times_out(db, provider, "t:who")
    french = provider.for_key(provider_idempotency_key(row))[0]
    assert french.to == address
    assert french.subject == tpl.get_kyc_approved_email("fr")[0] != tpl.get_kyc_approved_email("en")[0]
    # ... and again before the retry
    user.email, user.preferred_language = "moved-again@example.com", "de"
    db.commit()
    change_everything_around(db, monkeypatch)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    row = delivery(db, "t:who")
    assert row.status == "SENT" and row.lang == "fr"
    again = assert_one_identical_message(provider, row)
    assert again.to == address and "moved" not in " ".join(m.to for _k, m in provider.requests)
    assert row.recipient_hash == email_crypto.recipient_hash(address)


def test_the_sender_of_a_delivery_does_not_change_between_attempts(db, provider, monkeypatch):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_REJECTED, recipient=user.email, user_id=user.id,
                          context={"reason": "blurred"}, idempotency_key="t:from", now=T0)
    row = times_out(db, provider, "t:from")
    change_everything_around(db, monkeypatch, user)
    fresh = svc.get_settings(db)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    first = assert_one_identical_message(provider, delivery(db, "t:from"))
    assert first.from_header != svc.from_header(fresh) and first.reply_to != fresh.reply_to   # the change was real
    assert "2031" not in first.html + (first.text or "")
    # a NEW delivery uses the new settings
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:from2", now=T0 + timedelta(minutes=6))
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=6))
    newer = provider.for_key(provider_idempotency_key(delivery(db, "t:from2")))[0]
    assert newer.from_header == svc.from_header(fresh) and "2031" in newer.html


# ===========================================================================
# PROVIDER IDEMPOTENCY
# ===========================================================================

def test_same_delivery_same_key_and_request_other_delivery_other_key(db, provider, monkeypatch):
    user = member(db, verified=True)
    for key in ("t:k1", "t:k2"):
        email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                              idempotency_key=key, now=T0)
    provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)] * 2
    process_outbox(db, provider=provider, now=T0)
    change_everything_around(db, monkeypatch, user)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    one, two = delivery(db, "t:k1"), delivery(db, "t:k2")
    assert provider_idempotency_key(one) != provider_idempotency_key(two)
    assert_one_identical_message(provider, one)
    assert_one_identical_message(provider, two)
    assert len(provider.sent) == 2                                            # no conflict, one message each
    for key in (provider_idempotency_key(one), provider_idempotency_key(two)):
        assert user.email not in key and "KYC" not in key


def test_identical_content_is_what_makes_the_provider_answer_instead_of_refusing(db, provider, monkeypatch):
    """The provider refuses a key reused with other content (409). Before the
    message was kept, that is what a retry after a change produced."""
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:409", now=T0)
    row = accepted_then_crash(db, provider, "t:409")
    change_everything_around(db, monkeypatch, user)
    summary = process_outbox(db, provider=provider, now=RECLAIM)
    assert (summary["requeued"], summary["sent"], summary["retry"], summary["failed"]) == (1, 1, 0, 0)
    row = delivery(db, "t:409")
    assert (row.status, row.provider_message_id, row.failure_category) == ("SENT", "fake-1", None)
    assert len(provider.sent) == 1


# ===========================================================================
# EMAIL-3: CONTEST
# ===========================================================================

ENTRY_CASES = [
    # event, state it is sent for (exposure, verification), state it is retried in
    (EmailEvent.CONTEST_NOMINATION_PUBLISHED, ("PUBLIC", None), ("BLOCKED", None)),
    (EmailEvent.CONTEST_NOMINATION_ACTION_REQUIRED, ("HELD", None), ("BLOCKED", None)),
    (EmailEvent.CONTEST_NOMINATION_REMOVED, ("BLOCKED", None), ("PUBLIC", None)),
    (EmailEvent.CONTEST_PARTICIPATION_PENDING_REVIEW, ("HELD", None), ("PUBLIC", None)),
    (EmailEvent.CONTEST_PARTICIPATION_PUBLISHED, ("PUBLIC", None), ("HELD", None)),
    (EmailEvent.CONTEST_PARTICIPATION_ACTION_REQUIRED, ("PUBLIC", None), ("BLOCKED", None)),
    (EmailEvent.CONTEST_PARTICIPATION_REJECTED, ("BLOCKED", None), ("PUBLIC", None)),
    (EmailEvent.CONTEST_CREATIVE_UNAVAILABLE, ("PUBLIC", "creative_unavailable"), ("PUBLIC", "approved")),
]


def _set_entry_state(db, entry_id, exposure, verification_status):
    safety = _safety(db, entry_id)
    safety.exposure_status = exposure
    if verification_status is not None:
        db.query(Contestant).get(entry_id).verification_status = verification_status
    db.commit()


@pytest.mark.parametrize("crash", [accepted_then_crash, times_out], ids=["crash-after-accept", "timeout"])
@pytest.mark.parametrize("event, before, after", ENTRY_CASES, ids=[c[0].value for c in ENTRY_CASES])
def test_a_contest_email_is_retried_as_it_was_first_sent(client, db, world, provider, monkeypatch, event, before,
                                                         after, crash):
    c, _rnd = world()
    owner = person(db, 30)
    entry_id = _nominate(client, db, c, owner)["id"]
    db.query(EmailDelivery).delete()                                          # the submission's own email is not the subject here
    _set_entry_state(db, entry_id, *before)
    title, contest_name = db.query(Contestant).get(entry_id).title, c.name
    email_service.enqueue(db, event=event, recipient=owner.email, user_id=owner.id, lang="en",
                          context={"contestant_id": entry_id}, idempotency_key="t:entry", now=T0)

    row = crash(db, provider, "t:entry")
    # the entry is renamed, its contest is renamed, its state is no longer the one announced
    entry = db.query(Contestant).get(entry_id)
    entry.title, c.name = "A completely different title", "Another contest name"
    db.commit()
    _set_entry_state(db, entry_id, *after)
    change_everything_around(db, monkeypatch, owner)
    with pytest.raises(RenderError):                                          # rendered now, it would not even be sent
        render(db, event_key=event.value, to=owner.email, user_id=owner.id, context={"contestant_id": entry_id}, lang="en")

    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, "t:entry")
    assert (row.status, row.attempt_count) == ("SENT", 2)
    first = assert_one_identical_message(provider, row)
    assert title in first.html and contest_name in first.html
    assert "A completely different title" not in first.html + first.text and "Another contest name" not in first.html
    assert len(provider.sent) == 1 and db.query(EmailDelivery).count() == 1


def test_the_real_nomination_path_end_to_end(client, db, world, provider, monkeypatch):
    """enqueue (by the submission endpoint) -> provider accepts -> crash ->
    title and state change -> reclaim -> retry: the same request, the same key."""
    c, _rnd = world()
    nominator = person(db, 30)
    entry_id = _nominate(client, db, c, nominator)["id"]
    key = f"contest.entry.published:{entry_id}"
    row = accepted_then_crash(db, provider, key)
    first_request = provider.requests[0]

    entry = db.query(Contestant).get(entry_id)
    entry.title = "Renamed after sending"
    db.commit()
    _set_entry_state(db, entry_id, "HELD", None)
    change_everything_around(db, monkeypatch, nominator)

    summary = process_outbox(db, provider=provider, now=RECLAIM)
    assert (summary["requeued"], summary["sent"]) == (1, 1)
    row = delivery(db, key)
    assert (row.status, row.provider_message_id) == ("SENT", "fake-1")
    assert provider.requests == [first_request, first_request]                # key and message, byte for byte
    assert first_request[0] == provider_idempotency_key(row)
    assert "My song" in first_request[1].html and "Renamed after sending" not in first_request[1].html
    assert len(provider.sent) == 1
    # nothing about the entry was touched by sending
    assert db.query(Contestant).get(entry_id).title == "Renamed after sending"
    assert _safety(db, entry_id).exposure_status == "HELD"


def test_a_state_change_before_the_first_attempt_still_cancels_the_email(client, db, world, provider):
    """Unchanged EMAIL-3 rule: an email that was never handed to the provider
    does not announce a state that is no longer true."""
    c, _rnd = world()
    nominator = person(db, 30)
    entry_id = _nominate(client, db, c, nominator)["id"]
    _set_entry_state(db, entry_id, "BLOCKED", None)
    process_outbox(db, provider=provider, now=T0)
    row = delivery(db, f"contest.entry.published:{entry_id}")
    assert (row.status, row.failure_category, row.failure_code) == ("FAILED", "render_error", "state_changed")
    assert provider.requests == []


# ===========================================================================
# EMAIL-3: KYC
# ===========================================================================

KYC_CASES = [
    (KYCStatus.PENDING_PROOF_OF_ADDRESS, "KYC.ACTION_REQUIRED", KYCStatus.REJECTED),
    (KYCStatus.APPROVED, "KYC.APPROVED", KYCStatus.REJECTED),
    (KYCStatus.REJECTED, "KYC.REJECTED", KYCStatus.APPROVED),
]


@pytest.mark.parametrize("crash", [accepted_then_crash, times_out], ids=["crash-after-accept", "timeout"])
@pytest.mark.parametrize("status, event_key, later", KYC_CASES, ids=[c[1] for c in KYC_CASES])
def test_a_kyc_email_is_retried_as_it_was_first_sent(db, provider, monkeypatch, status, event_key, later, crash):
    user = person(db, 30)
    v = verification(db, user, status=status)
    kyc_notifications.notify_status(db, v.id)                                 # the real notifier
    (queued,) = db.query(EmailDelivery).all()
    assert queued.event_key == event_key
    key = queued.idempotency_key

    row = crash(db, provider, key)
    v.status = later                                                          # the verification moves on
    user.is_active = False                                                    # and so does the account
    db.commit()
    change_everything_around(db, monkeypatch, user)
    if event_key == "KYC.ACTION_REQUIRED":
        with pytest.raises(RenderError):
            render(db, event_key=event_key, to=user.email, user_id=user.id, context={}, lang="en")

    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, key)
    assert (row.status, row.attempt_count) == ("SENT", 2)
    first = assert_one_identical_message(provider, row)
    assert first.to == user.email and len(provider.sent) == 1
    db.refresh(v)
    assert v.status == later                                                  # sending decided nothing


def test_a_kyc_state_change_before_the_first_attempt_still_cancels_the_email(db, provider):
    user = person(db, 30)
    v = verification(db, user, status=KYCStatus.PENDING_PROOF_OF_ADDRESS)
    kyc_notifications.notify_status(db, v.id)
    v.status = KYCStatus.APPROVED
    db.commit()
    process_outbox(db, provider=provider, now=T0)
    (row,) = db.query(EmailDelivery).all()
    assert (row.status, row.failure_code) == ("FAILED", "state_changed") and provider.requests == []


# ===========================================================================
# EMAIL-2: AUTH
# ===========================================================================

AUTH_LINKS = [(PURPOSE_EMAIL_VERIFICATION, "verify-email", EmailEvent.AUTH_EMAIL_VERIFICATION),
              (PURPOSE_PASSWORD_RESET, "reset-password", EmailEvent.AUTH_PASSWORD_RESET)]


@pytest.mark.parametrize("crash", [accepted_then_crash, times_out], ids=["crash-after-accept", "timeout"])
@pytest.mark.parametrize("purpose, page, event", AUTH_LINKS, ids=[c[2].value for c in AUTH_LINKS])
def test_a_link_email_is_retried_identically_and_its_link_stays_safe(client, db, provider, monkeypatch, ip, purpose,
                                                                    page, event, crash):
    user = member(db)
    email_service.enqueue(db, event=event, recipient=user.email, user_id=user.id, lang="en",
                          idempotency_key="t:link", now=T0)
    row = crash(db, provider, "t:link")
    first = provider.for_key(provider_idempotency_key(row))[0]
    token = link_token({"html": first.html}, page)
    assert token == auth_tokens.delivery_credential(purpose, user.id, outbox_module.delivery_ref(row))   # deterministic
    assert token in first.text and LINK_CREDENTIAL not in first.html + first.text

    # nothing stored can be turned into the link: the kept message holds a placeholder, the database a digest
    payload = email_crypto.decrypt_payload(row.payload_ciphertext)
    kept = payload["message"]
    assert token not in str(payload) and LINK_CREDENTIAL in kept["html"] and LINK_CREDENTIAL in kept["text"]
    assert token not in stored(db) and token not in (row.payload_ciphertext or "")
    assert db.query(AuthToken).one().token_hash == auth_tokens.hash_token(token)

    user.preferred_language = "fr"
    db.commit()
    change_everything_around(db, monkeypatch)
    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, "t:link")
    assert (row.status, row.attempt_count) == ("SENT", 2)
    assert_one_identical_message(provider, row)
    assert len(provider.sent) == 1 and token not in stored(db)
    # one link exists, it was not replaced, and it is still one-time
    link = db.query(AuthToken).one()
    assert link.revoked_at is None and link.consumed_at is None and link.expires_at > datetime.utcnow()
    if purpose == PURPOSE_EMAIL_VERIFICATION:
        assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
        assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    else:
        assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 200
        assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 400


@pytest.mark.parametrize("purpose, page, event", AUTH_LINKS, ids=[c[2].value for c in AUTH_LINKS])
def test_a_link_is_not_mailed_again_once_it_must_not_be(client, db, provider, ip, purpose, page, event):
    """Keeping the message does not keep the right to send a credential: the
    EMAIL-2 rules are checked on every attempt. A refused retry sends nothing;
    it never sends something else."""
    def retry_after(change, key):
        user = member(db)
        email_service.enqueue(db, event=event, recipient=user.email, user_id=user.id, idempotency_key=key, now=T0)
        row = times_out(db, provider, key)
        before = len(provider.requests)
        change(user)
        db.commit()
        process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
        row = delivery(db, key)
        assert len(provider.requests) == before                              # nothing was handed to the provider
        return row, user

    def newer_link(user):
        auth_tokens.issue(db, user, purpose, delivery_ref="999:newer")

    def used(user):
        token = db.query(AuthToken).filter(AuthToken.user_id == user.id).one()
        assert auth_tokens.mark_used(db, token.id, datetime.utcnow())

    def moved(user):
        user.email = f"moved_{user.id}@example.com"

    def deactivated(user):
        user.is_active = False

    for name, change, code in (("newer", newer_link, "link_revoked"), ("used", used, "link_used"),
                               ("moved", moved, "recipient_changed"), ("inactive", deactivated, "recipient_gone")):
        row, user = retry_after(change, f"t:{name}")
        assert (row.status, row.failure_category, row.failure_code) == ("FAILED", "render_error", code), name
        assert row.payload_ciphertext is None
    # the address binding of the link that WAS mailed is untouched by the refused retry
    moved_user = db.query(AuthToken).join(EmailDelivery, EmailDelivery.user_id == AuthToken.user_id).filter(
        EmailDelivery.idempotency_key == "t:moved").one()
    assert moved_user.email_hash != auth_tokens.email_fingerprint(f"moved_{moved_user.user_id}@example.com")
    if purpose == PURPOSE_EMAIL_VERIFICATION:
        def verified(user):
            user.email_verified = True
        row, _user = retry_after(verified, "t:verified")
        assert (row.status, row.failure_code) == ("FAILED", "already_verified")


@pytest.mark.parametrize("event, context", [(EmailEvent.AUTH_WELCOME, {}),
                                            (EmailEvent.AUTH_PASSWORD_CHANGED, {"ip_address": "198.51.100.7"})])
def test_welcome_and_password_changed_are_retried_identically(db, provider, monkeypatch, event, context):
    user = member(db, verified=True)
    address = user.email
    email_service.enqueue(db, event=event, recipient=address, user_id=user.id, lang="en", context=context,
                          idempotency_key="t:auth", now=T0)
    row = accepted_then_crash(db, provider, "t:auth")
    user.email, user.is_active = "elsewhere@example.com", False
    db.commit()
    change_everything_around(db, monkeypatch, user)
    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, "t:auth")
    assert row.status == "SENT"
    assert assert_one_identical_message(provider, row).to == address and len(provider.sent) == 1


def test_the_real_registration_email_is_retried_identically(client, db, provider, monkeypatch, ip):
    from tests.unit.test_email2_auth_security import body

    data = body()
    assert client.post(f"{A}/register", json=data).status_code == 201
    keys = [r.idempotency_key for r in db.query(EmailDelivery).order_by(EmailDelivery.id)]
    assert keys
    provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)] * len(keys)
    process_outbox(db, provider=provider, now=T0)
    change_everything_around(db, monkeypatch)
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    for key in keys:
        row = delivery(db, key)
        assert row.status == "SENT", key
        assert_one_identical_message(provider, row)
    assert data["password"] not in stored(db)
    for _key, message in provider.requests:
        assert data["password"] not in message.html + (message.text or "")


# ===========================================================================
# EMAIL-1
# ===========================================================================

EMAIL1_CASES = [
    (EmailEvent.GUARDIAN_CONSENT_REQUEST, {"token": "synthetic-guardian-token-0001", "username": "young_user"}),
    (EmailEvent.GUARDIAN_REGISTRATION_COMPLETION, {"token": "synthetic-guardian-token-0002"}),
    (EmailEvent.AFFILIATE_INVITATION, {"inviter_name": "Asha", "referral_code": "ASHA1", "message": "Join <b>me</b>"}),
    (EmailEvent.ADMIN_CONTENT_REPORT, {"contestant_title": "T", "author_name": "A", "contest_name": "C",
                                       "reporter_name": "R", "reason": "spam", "description": "d", "report_id": 7}),
    (EmailEvent.ADMIN_CONTACT_MESSAGE, {"name": "N", "email": "n@example.com", "category": "general",
                                        "subject": "Hello", "message": "Line 1\nLine 2"}),
    (EmailEvent.SUPPORT_CONTACT_CONFIRMATION, {"name": "N", "subject": "Hello", "category": "general", "message": "m"}),
    (EmailEvent.SUPPORT_NEWSLETTER_CONFIRMATION, {}),
]


@pytest.mark.parametrize("event, context", EMAIL1_CASES, ids=[c[0].value for c in EMAIL1_CASES])
def test_email1_events_are_retried_identically(db, provider, monkeypatch, event, context):
    email_service.enqueue(db, event=event, recipient="someone@example.com", context=context, lang="en",
                          idempotency_key="t:e1", now=T0)
    row = delivery(db, "t:e1")
    if row.status != "QUEUED":
        pytest.skip(f"{event.value} is switched off by default ({row.failure_category})")
    row = accepted_then_crash(db, provider, "t:e1")
    change_everything_around(db, monkeypatch)
    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, "t:e1")
    assert (row.status, row.provider_message_id) == ("SENT", "fake-1")
    assert_one_identical_message(provider, row)
    assert len(provider.sent) == 1


def test_the_admin_test_email_is_unchanged(db, provider):
    admin = member(db, verified=True)
    row = outbox_module.send_test_email(db, recipient="check@example.com", actor_id=admin.id, provider=provider, now=T0)
    assert (row.status, row.event_key, row.attempt_count, row.payload_ciphertext) == ("SENT", "SYSTEM.TEST_EMAIL", 1, None)
    ((key, message),) = provider.requests
    assert key == provider_idempotency_key(row) and message.to == "check@example.com"
    assert message.subject.startswith("[TEST]")


# ===========================================================================
# SWITCHES AND WEBHOOKS ARE UNCHANGED
# ===========================================================================

def test_an_emergency_stop_still_stops_a_retry(db, provider, monkeypatch):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:stop", now=T0)
    times_out(db, provider, "t:stop")
    row = svc.get_settings(db)
    row.id, row.emergency_stop = svc.SETTINGS_ROW_ID, True
    db.add(row)
    db.commit()
    process_outbox(db, provider=provider, now=T0 + timedelta(minutes=5))
    row = delivery(db, "t:stop")
    assert row.status == "SUPPRESSED" and row.payload_ciphertext is None and len(provider.requests) == 1


def test_provider_events_still_reach_a_delivery_recovered_after_a_crash(client, db, provider, webhook_secret, monkeypatch):
    user = member(db, verified=True)
    email_service.enqueue(db, event=EmailEvent.KYC_APPROVED, recipient=user.email, user_id=user.id,
                          idempotency_key="t:hook", now=T0)
    accepted_then_crash(db, provider, "t:hook")
    # the provider reports the first copy before the application knows its id
    early = post_webhook(client, provider_event("email.delivered", "fake-1"))
    assert early.status_code == 200 and early.json()["result"] == "unmatched"
    change_everything_around(db, monkeypatch, user)
    process_outbox(db, provider=provider, now=RECLAIM)
    row = delivery(db, "t:hook")
    assert (row.status, row.provider_message_id) == ("DELIVERED", "fake-1")
    assert post_webhook(client, provider_event("email.bounced", "fake-1")).json()["result"] == "applied"
    assert delivery(db, "t:hook").status == "BOUNCED" and len(provider.sent) == 1
