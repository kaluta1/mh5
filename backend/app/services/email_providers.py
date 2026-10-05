"""Provider-independent email sending (EMAIL-1).

Application code never talks to a provider. The outbox worker hands an
`EmailMessage` to the active `EmailProvider` and gets a normalized
`ProviderResult` back: success, the provider's message id, whether a failure
is worth retrying, and a short safe category. Provider secrets never appear in
a result, a log line or an exception message produced here.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Failure categories (also stored on the delivery row).
FAIL_TIMEOUT = "timeout"
FAIL_NETWORK = "network"
FAIL_RATE_LIMITED = "provider_rate_limited"
FAIL_PROVIDER_ERROR = "provider_error"
FAIL_REJECTED = "provider_rejected"
FAIL_AUTH = "provider_auth"


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

    def send(self, message: EmailMessage, *, api_key: str) -> ProviderResult:  # pragma: no cover - interface
        raise NotImplementedError


def classify_http_status(code: Optional[int]) -> ProviderResult:
    """Normalize a provider HTTP status into a failure result."""
    if code == 429:
        return ProviderResult(False, retryable=True, error_category=FAIL_RATE_LIMITED, error_code="429",
                              safe_error_message="The provider is rate limiting requests.")
    if code is not None and code >= 500:
        return ProviderResult(False, retryable=True, error_category=FAIL_PROVIDER_ERROR, error_code=str(code),
                              safe_error_message="The provider reported a temporary error.")
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

    def send(self, message: EmailMessage, *, api_key: str) -> ProviderResult:
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

    def send(self, message: EmailMessage, *, api_key: str) -> ProviderResult:
        self.api_keys.append(api_key)
        if self.script:
            result = self.script.pop(0)
            if result.success:
                self.sent.append(message)
            return result
        self.sent.append(message)
        return ProviderResult(True, provider_message_id=f"fake-{len(self.sent)}")


_provider_factory: Callable[[], EmailProvider] = ResendEmailProvider


def get_provider() -> EmailProvider:
    return _provider_factory()


def set_provider_factory(factory: Optional[Callable[[], EmailProvider]]) -> None:
    """Dependency injection point (tests, local development). None restores Resend."""
    global _provider_factory
    _provider_factory = factory or ResendEmailProvider
