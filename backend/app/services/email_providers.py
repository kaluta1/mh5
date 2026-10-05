"""Provider-independent email sending (EMAIL-1).

Application code never talks to a provider. The outbox worker hands an
`EmailMessage` to the active `EmailProvider` and gets a normalized
`ProviderResult` back: success, the provider's message id, whether a failure
is worth retrying, and a short safe category. Provider secrets never appear in
a result, a log line or an exception message produced here.

EMAIL-5 adds two things, both provided by the Resend SDK itself (nothing here
re-implements provider cryptography or invents provider behaviour):

* `idempotency_key` on a send. Resend receives it as the `Idempotency-Key`
  header. Sending the same delivery again with the same key (a retry after a
  timeout, or after a crash between the provider accepting the message and the
  application recording it) does not create a second message: the provider
  answers with the first message's id.
* `verify_resend_webhook`: the signature check for incoming provider webhooks
  (`resend.Webhooks.verify`: Svix headers, HMAC-SHA256 over
  "id.timestamp.raw body", five-minute timestamp tolerance, constant-time
  comparison), with the dedicated signing secret.

This file is the ONLY place that imports the provider SDK.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Failure categories (also stored on the delivery row).
FAIL_TIMEOUT = "timeout"
FAIL_NETWORK = "network"
FAIL_RATE_LIMITED = "provider_rate_limited"
FAIL_PROVIDER_ERROR = "provider_error"
FAIL_REJECTED = "provider_rejected"
FAIL_AUTH = "provider_auth"
# HTTP 409 on a request that carried an idempotency key: the provider already
# holds a request for this key (still in flight, or accepted with different
# content). Retried; never treated as a fresh rejection of the message.
FAIL_CONFLICT = "provider_conflict"

# Provider limit for an idempotency key.
MAX_IDEMPOTENCY_KEY_LENGTH = 256


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: Optional[str]
    from_header: str
    reply_to: Optional[str] = None


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider_message_id: Optional[str] = None
    retryable: bool = False
    error_category: Optional[str] = None
    error_code: Optional[str] = None
    safe_error_message: Optional[str] = None


class EmailProvider:
    name = "base"

    def send(self, message: EmailMessage, *, api_key: str,
             idempotency_key: Optional[str] = None) -> ProviderResult:  # pragma: no cover - interface
        """`idempotency_key` identifies the logical delivery: the same value on
        every attempt for it, so the provider can refuse to send it twice."""
        raise NotImplementedError


def classify_http_status(code: Optional[int]) -> ProviderResult:
    """Normalize a provider HTTP status into a failure result."""
    if code == 429:
        return ProviderResult(False, retryable=True, error_category=FAIL_RATE_LIMITED, error_code="429",
                              safe_error_message="The provider is rate limiting requests.")
    if code is not None and code >= 500:
        return ProviderResult(False, retryable=True, error_category=FAIL_PROVIDER_ERROR, error_code=str(code),
                              safe_error_message="The provider reported a temporary error.")
    if code == 409:
        return ProviderResult(False, retryable=True, error_category=FAIL_CONFLICT, error_code="409",
                              safe_error_message="The provider already holds a request for this delivery.")
    if code in (401, 403):
        return ProviderResult(False, retryable=False, error_category=FAIL_AUTH, error_code=str(code),
                              safe_error_message="The provider rejected the API key or the sender.")
    return ProviderResult(False, retryable=False, error_category=FAIL_REJECTED,
                          error_code=str(code) if code is not None else None,
                          safe_error_message="The provider rejected the message.")


class ResendEmailProvider(EmailProvider):
    """Resend through its official SDK. The SDK keeps the API key in module
    state, so a send sets it under a lock and clears it again."""

    name = "resend"
    _lock = threading.Lock()

    def send(self, message: EmailMessage, *, api_key: str, idempotency_key: Optional[str] = None) -> ProviderResult:
        import resend
        from resend.exceptions import ResendError

        params = {"from": message.from_header, "to": [message.to], "subject": message.subject,
                  "html": message.html}
        if message.text:
            params["text"] = message.text
        if message.reply_to:
            params["reply_to"] = message.reply_to
        try:
            with self._lock:
                resend.api_key = api_key
                try:
                    if idempotency_key:
                        response = resend.Emails.send(
                            params, {"idempotency_key": str(idempotency_key)[:MAX_IDEMPOTENCY_KEY_LENGTH]})
                    else:
                        response = resend.Emails.send(params)
                finally:
                    resend.api_key = None
        except ResendError as exc:
            try:
                code = int(getattr(exc, "code", None))
            except (TypeError, ValueError):
                code = None
            return classify_http_status(code)
        except Exception as exc:  # noqa: BLE001 - network layer; the text may echo the request
            kind = type(exc).__name__.lower()
            category = FAIL_TIMEOUT if "timeout" in kind else FAIL_NETWORK
            return ProviderResult(False, retryable=True, error_category=category, error_code=type(exc).__name__[:40],
                                  safe_error_message="The provider could not be reached.")
        message_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        return ProviderResult(True, provider_message_id=str(message_id) if message_id else None)


@dataclass
class FakeEmailProvider(EmailProvider):
    """In-memory provider for tests and local development. `script` queues the
    results of the next sends; without one every send succeeds."""

    name: str = "fake"
    sent: List[EmailMessage] = field(default_factory=list)
    api_keys: List[str] = field(default_factory=list)
    script: List[ProviderResult] = field(default_factory=list)
    # Every idempotency key received, in order (one entry per send call).
    idempotency_keys: List[Optional[str]] = field(default_factory=list)
    # What the provider remembers per key, like the real one: the message id
    # it answered with, and the content it accepted.
    accepted: Dict[str, Tuple[str, EmailMessage]] = field(default_factory=dict)

    def send(self, message: EmailMessage, *, api_key: str, idempotency_key: Optional[str] = None) -> ProviderResult:
        self.api_keys.append(api_key)
        self.idempotency_keys.append(idempotency_key)
        if idempotency_key and idempotency_key in self.accepted:
            message_id, first = self.accepted[idempotency_key]
            if first == message:
                # Same key, same content: no second message, the first id again.
                return ProviderResult(True, provider_message_id=message_id)
            return classify_http_status(409)        # same key, different content
        if self.script:
            result = self.script.pop(0)
            if result.success:
                self.sent.append(message)
                if idempotency_key and result.provider_message_id:
                    self.accepted[idempotency_key] = (result.provider_message_id, message)
            return result
        self.sent.append(message)
        message_id = f"fake-{len(self.sent)}"
        if idempotency_key:
            self.accepted[idempotency_key] = (message_id, message)
        return ProviderResult(True, provider_message_id=message_id)


class WebhookVerificationError(Exception):
    """The webhook could not be authenticated. Carries no detail on purpose."""


def verify_resend_webhook(raw_body: bytes, *, event_id: str, timestamp: str, signature: str, secret: str) -> None:
    """Authenticate a Resend webhook. Raises WebhookVerificationError unless
    the signature over the RAW body is valid for the dedicated signing secret
    and the timestamp is within the provider's tolerance.

    The check itself is the provider SDK's (`resend.Webhooks.verify`). The
    body is passed exactly as received: re-serialised JSON would not verify."""
    import resend

    if not (secret and event_id and timestamp and signature and raw_body):
        raise WebhookVerificationError()
    try:
        payload = raw_body.decode("utf-8")
        resend.Webhooks.verify({"payload": payload,
                                "headers": {"id": event_id, "timestamp": timestamp, "signature": signature},
                                "webhook_secret": secret})
    except Exception:  # noqa: BLE001 - every failure is the same refusal; the reason may echo input
        raise WebhookVerificationError() from None


_provider_factory: Callable[[], EmailProvider] = ResendEmailProvider


def get_provider() -> EmailProvider:
    return _provider_factory()


def set_provider_factory(factory: Optional[Callable[[], EmailProvider]]) -> None:
    """Dependency injection point (tests, local development). None restores Resend."""
    global _provider_factory
    _provider_factory = factory or ResendEmailProvider
