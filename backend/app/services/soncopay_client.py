"""SoncoPay API client (customer payment collection only).

Built from the official documentation (soncopay.com/developers, API v1) and
the official Python SDK 2.11.2, which is not used directly: it is synchronous
(urllib) and is not published on PyPI. This client calls the same documented
routes with the same rules:

  * JSON over HTTPS, the API key in the X-Api-Key header (sp_test_... works on
    separate test data, sp_live_... moves real money);
  * GET is retried on a network error, 429, 502, 503 and 504; POST /v1/payments
    is retried only when no answer arrived (network error, 502, 503): sending
    the SAME order_id again returns the same payment, so the retry cannot
    create a second one (documented); a choice of method is never retried;
  * an error answer is {"detail": "...", "code": "..."}: the code is kept, the
    text stays out of every message we show or log.

The API host is API_BASE. The documentation and the SDK show the placeholder
"soncopay.example"; the live API answers at https://soncopay.com (verified
2026-10-21: /v1/* answers 401 {"detail": "missing X-Api-Key header"}).

The key is never logged, never put in an exception and never returned.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://soncopay.com"
USER_AGENT = "MyHigh5/soncopay-integration"

CREATE_TIMEOUT = httpx.Timeout(30.0, connect=5.0, read=25.0, write=10.0, pool=5.0)
READ_TIMEOUT = httpx.Timeout(20.0, connect=5.0, read=15.0, write=10.0, pool=5.0)
GET_RETRY_STATUSES = (429, 502, 503, 504)
CREATE_RETRY_STATUSES = (502, 503)
MAX_RETRIES = 2

KEY_PREFIX = {"test": "sp_test_", "live": "sp_live_"}


class SoncoPayError(Exception):
    """A SoncoPay call that did not succeed. `status_code` is the HTTP status
    (None when no answer arrived), `code` SoncoPay's stable error code when it
    sent one, `stage` the step (create / read / methods / choose / simulate).
    The message never carries the key or a response body."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, code: Optional[str] = None,
                 stage: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.stage = stage


def _transport() -> Optional[httpx.AsyncBaseTransport]:
    """Tests replace this with an httpx.MockTransport. Never set in production."""
    return None


def _backoff(attempt: int, retry_after: Optional[str]) -> float:
    try:
        wait = float(retry_after) if retry_after else 0.0
    except ValueError:
        wait = 0.0
    if wait > 0:
        return min(wait, 5.0)
    return min(0.5 * 2 ** attempt, 3.0) + random.random() / 10


class SoncoPayClient:
    def __init__(self, api_key: str, environment: str, *, base_url: str = API_BASE):
        if environment not in KEY_PREFIX:
            raise SoncoPayError("Unknown SoncoPay environment", stage="config")
        key = (api_key or "").strip()
        # Test and Live never mix: a Live key is never used for Test, nor the reverse.
        if not key.startswith(KEY_PREFIX[environment]):
            raise SoncoPayError(f"The SoncoPay {environment.title()} API key does not start with "
                                f"{KEY_PREFIX[environment]}", stage="config")
        self.__key = key
        self.environment = environment
        self.base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"SoncoPayClient(environment={self.environment!r})"

    async def _request(self, method: str, path: str, *, stage: str, body: Optional[dict] = None,
                       timeout: httpx.Timeout = READ_TIMEOUT, retry_statuses: tuple = (),
                       retry_network: bool = False) -> Dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT, "X-Api-Key": self.__key}
        attempt = 0
        async with httpx.AsyncClient(timeout=timeout, transport=_transport()) as client:
            while True:
                try:
                    response = await client.request(method, self.base_url + path, headers=headers, json=body)
                except httpx.HTTPError as exc:
                    if retry_network and attempt < MAX_RETRIES:
                        await asyncio.sleep(_backoff(attempt, None))
                        attempt += 1
                        continue
                    logger.warning("SoncoPay %s %s: no answer (%s)", stage, self.environment, type(exc).__name__)
                    raise SoncoPayError("SoncoPay could not be reached", stage=stage) from None
                if response.status_code in retry_statuses and attempt < MAX_RETRIES:
                    await asyncio.sleep(_backoff(attempt, response.headers.get("retry-after")))
                    attempt += 1
                    continue
                if response.status_code >= 400:
                    code = None
                    try:
                        answer = response.json()
                        code = answer.get("code") if isinstance(answer, dict) else None
                    except ValueError:
                        pass
                    code = str(code)[:60] if code else None
                    logger.warning("SoncoPay %s %s refused: HTTP %s code=%s", stage, self.environment,
                                   response.status_code, code)
                    raise SoncoPayError(f"SoncoPay refused the request (HTTP {response.status_code})",
                                        status_code=response.status_code, code=code, stage=stage)
                try:
                    answer = response.json()
                except ValueError:
                    raise SoncoPayError("SoncoPay answered with something that is not JSON",
                                        status_code=response.status_code, stage=stage) from None
                if not isinstance(answer, dict):
                    raise SoncoPayError("SoncoPay answered with an unexpected document",
                                        status_code=response.status_code, stage=stage)
                return answer

    # -- payments ------------------------------------------------------------

    async def create_payment(self, *, amount: str, currency: str, order_id: str, description: str,
                             return_url: str, callback_url: Optional[str], metadata: Optional[dict] = None,
                             lifetime_minutes: Optional[int] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"amount": amount, "currency": currency, "order_id": order_id,
                                "description": description, "return_url": return_url}
        if callback_url:
            body["callback_url"] = callback_url
        if metadata:
            body["metadata"] = metadata
        if lifetime_minutes:
            body["lifetime_minutes"] = int(lifetime_minutes)
        payment = await self._request("POST", "/v1/payments", stage="create", body=body, timeout=CREATE_TIMEOUT,
                                      retry_statuses=CREATE_RETRY_STATUSES, retry_network=True)
        if not str(payment.get("id") or "").startswith("pay_"):
            raise SoncoPayError("SoncoPay payment creation returned no payment id", stage="create")
        return payment

    async def retrieve_payment(self, payment_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/v1/payments/{_payment_path(payment_id)}", stage="read",
                                   retry_statuses=GET_RETRY_STATUSES, retry_network=True)

    async def payment_methods(self, payment_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/v1/payments/{_payment_path(payment_id)}/methods", stage="methods",
                                   retry_statuses=GET_RETRY_STATUSES, retry_network=True)

    async def choose_method(self, payment_id: str, choice: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", f"/v1/payments/{_payment_path(payment_id)}/method", stage="choose",
                                   body=choice, timeout=CREATE_TIMEOUT)

    async def simulate(self, payment_id: str) -> Dict[str, Any]:
        """Test mode only: pays the chosen method. Refused here for a Live key."""
        if self.environment != "test":
            raise SoncoPayError("Simulated payments exist in the Test environment only", stage="simulate")
        return await self._request("POST", f"/v1/payments/{_payment_path(payment_id)}/simulate", stage="simulate")

    async def account_methods(self) -> Dict[str, Any]:
        """GET /v1/methods: the methods open to the account. No side effect (connection test)."""
        return await self._request("GET", "/v1/methods", stage="methods", retry_statuses=GET_RETRY_STATUSES,
                                   retry_network=True)


def _payment_path(payment_id: str) -> str:
    value = str(payment_id or "")
    # SoncoPay payment ids look like pay_3f9a5c0d21e4b7a6c8d1: nothing else is put in a URL.
    if not value.startswith("pay_") or not value[4:].isalnum() or len(value) > 64:
        raise SoncoPayError("Not a SoncoPay payment id", stage="read")
    return value
