"""Availability of external creative links (YouTube, TikTok, Vimeo).

Management rule (2026-10-04): an entry whose external creative is dead - at
submission, or later - is removed from its contest.

Safety properties:

* No arbitrary fetch. The server only ever calls the three providers' public
  oEmbed endpoints on fixed hosts, with an identifier that was validated by a
  strict pattern. A member-supplied host is never contacted, so this cannot be
  used to reach internal or third-party addresses. Direct file links, Facebook
  links and hosted media are not checked.
* Only a definitive provider answer counts: HTTP 404 or 410. A timeout, a
  network or DNS error, 401, 403, 429, any 5xx, a redirect or anything
  unexpected is UNKNOWN and never removes anything.
* Removal needs TWO definitive results at least
  CREATIVE_LINK_CONFIRM_AFTER_HOURS apart. The first one is recorded in the
  audit trail (durable across restarts); a successful check in between clears
  it. If an unusual share of one batch looks dead, the whole batch is ignored
  (a provider or network anomaly, not hundreds of deleted videos).
* Removal is logical and reversible: the entry's verification_status becomes
  "creative_unavailable", which the publication rule treats like a rejection
  (not listed, not counted, not votable, not ranked). The row, its votes and
  its history are kept. An administrator restores it by approving the entry;
  nothing is restored automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.contests import Contestant
from app.models.round import Round, RoundStatus
from app.services.entry_exposure import (
    CREATIVE_UNAVAILABLE_STATUS,
    public_entry_clause,
    removed_entry_clause,
)

logger = logging.getLogger(__name__)

AUDIT_TABLE = "contestants"
ACTION_SUSPECT = "CREATIVE_LINK_SUSPECT"       # first definitive "not found"
ACTION_OK = "CREATIVE_LINK_OK"                 # available again after a suspicion
ACTION_REMOVED = "CREATIVE_LINK_REMOVED"       # confirmed dead: entry removed from the contest
_LINK_ACTIONS = (ACTION_SUSPECT, ACTION_OK, ACTION_REMOVED)

DEFINITIVE_DEAD_STATUSES = frozenset({404, 410})
# A batch in which more than this share of the definitive answers is "dead"
# (and at least this many answers were definitive) is treated as an anomaly.
ANOMALY_MIN_DEFINITIVE = 5
ANOMALY_DEAD_RATIO = 0.5

DEAD_LINK_MESSAGE = (
    "This video link is not available (it may have been deleted or made private). "
    "Please check the link and try again."
)


class LinkStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEAD = "DEAD"                # the provider says it does not exist
    UNKNOWN = "UNKNOWN"          # transient or ambiguous: never acted on
    UNSUPPORTED = "UNSUPPORTED"  # not a link this service can check safely


@dataclass(frozen=True)
class LinkCheck:
    status: LinkStatus
    provider: Optional[str] = None
    http_status: Optional[int] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class EntryLinkResult:
    status: LinkStatus
    checks: Tuple[LinkCheck, ...] = ()


# ---------------------------------------------------------------------------
# Provider endpoints (fixed hosts only)
# ---------------------------------------------------------------------------

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_NUMERIC_ID = re.compile(r"^\d{5,25}$")
_TIKTOK_PATH = re.compile(r"^/@([A-Za-z0-9._-]{1,64})/video/(\d{5,25})/?$")


def _is_host(hostname: str, *domains: str) -> bool:
    return any(hostname == d or hostname.endswith("." + d) for d in domains)


def provider_probe(url: str) -> Optional[Tuple[str, str]]:
    """(provider, oEmbed URL on that provider's own host) for a supported link,
    else None. The returned URL is built from validated identifiers only."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        return None

    from app.api.api_v1.endpoints.contestant import _canonicalize_social_media_url

    canonical = _canonicalize_social_media_url(url) or ""
    provider, _, identifier = canonical.partition(":")
    if provider == "youtube" and _YOUTUBE_ID.match(identifier):
        target = quote(f"https://www.youtube.com/watch?v={identifier}", safe="")
        return "youtube", f"https://www.youtube.com/oembed?format=json&url={target}"
    if provider == "vimeo" and _NUMERIC_ID.match(identifier):
        target = quote(f"https://vimeo.com/{identifier}", safe="")
        return "vimeo", f"https://vimeo.com/api/oembed.json?url={target}"
    if provider == "tiktok" and _is_host(hostname, "tiktok.com"):
        match = _TIKTOK_PATH.match(parsed.path or "")
        if match:
            target = quote(f"https://www.tiktok.com/@{match.group(1)}/video/{match.group(2)}", safe="")
            return "tiktok", f"https://www.tiktok.com/oembed?url={target}"
    return None


def _http_status(url: str) -> int:
    """HTTP status of a provider oEmbed URL. Redirects are not followed.
    Raises requests.RequestException on timeout / network failure."""
    response = requests.get(
        url,
        timeout=(3.05, float(settings.CREATIVE_LINK_HTTP_TIMEOUT_SECONDS)),
        allow_redirects=False,
        headers={"User-Agent": "MyHigh5-LinkCheck/1.0", "Accept": "application/json"},
    )
    try:
        return int(response.status_code)
    finally:
        response.close()


def check_url(url: str) -> LinkCheck:
    probe = provider_probe(url)
    if probe is None:
        return LinkCheck(LinkStatus.UNSUPPORTED)
    provider, endpoint = probe
    try:
        code = _http_status(endpoint)
    except requests.Timeout:
        return LinkCheck(LinkStatus.UNKNOWN, provider, None, "timeout")
    except requests.RequestException as exc:
        return LinkCheck(LinkStatus.UNKNOWN, provider, None, type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 - never let a check raise into a request or the scheduler
        return LinkCheck(LinkStatus.UNKNOWN, provider, None, type(exc).__name__)
    if code == 200:
        return LinkCheck(LinkStatus.AVAILABLE, provider, code)
    if code in DEFINITIVE_DEAD_STATUSES:
        return LinkCheck(LinkStatus.DEAD, provider, code)
    return LinkCheck(LinkStatus.UNKNOWN, provider, code, "ambiguous")


# ---------------------------------------------------------------------------
# Entry level
# ---------------------------------------------------------------------------

def _flatten_refs(blob: Any) -> List[str]:
    """Video references of an entry as strings (stored values may be JSON
    encoded more than once)."""
    out: List[str] = []
    pending: List[Any] = [blob]
    guard = 0
    while pending and guard < 200:
        guard += 1
        ref = pending.pop(0)
        if ref is None:
            continue
        if isinstance(ref, (list, tuple)):
            pending = list(ref) + pending
            continue
        text = str(ref).strip()
        if not text:
            continue
        if text[0] in "[\"":
            try:
                decoded = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                decoded = None
            if decoded is not None and decoded != ref:
                pending.insert(0, decoded)
                continue
        out.append(text)
    return out


def check_entry_links(video_media_ids: Any) -> EntryLinkResult:
    """DEAD only when the entry has at least one checkable external video and
    every creative it has is definitively dead. A hosted video, an unsupported
    link or any unknown answer keeps the entry."""
    refs = _flatten_refs(video_media_ids)
    checks: List[LinkCheck] = []
    other_creative = False
    for ref in refs[:5]:
        if not ref.startswith(("http://", "https://")):
            other_creative = True          # hosted media reference
            continue
        result = check_url(ref)
        if result.status == LinkStatus.UNSUPPORTED:
            other_creative = True
            continue
        checks.append(result)
    if not checks:
        return EntryLinkResult(LinkStatus.UNSUPPORTED)
    statuses = {c.status for c in checks}
    if LinkStatus.AVAILABLE in statuses:
        return EntryLinkResult(LinkStatus.AVAILABLE, tuple(checks))
    if statuses == {LinkStatus.DEAD} and not other_creative:
        return EntryLinkResult(LinkStatus.DEAD, tuple(checks))
    return EntryLinkResult(LinkStatus.UNKNOWN, tuple(checks))


def submission_link_is_dead(video_media_ids: Any) -> bool:
    """Submission-time check. True only for a definitive "does not exist";
    disabled, unsupported, transient or ambiguous results all return False so a
    provider problem never blocks a member."""
    if not settings.CREATIVE_LINK_CHECK_ENABLED or not video_media_ids:
        return False
    try:
        return check_entry_links(video_media_ids).status == LinkStatus.DEAD
    except Exception as exc:  # noqa: BLE001
        logger.warning("Creative link check failed at submission: %s", type(exc).__name__)
        return False


# ---------------------------------------------------------------------------
# Periodic recheck
# ---------------------------------------------------------------------------

def _candidates(db: Session, *, now: datetime, cycle_hours: int, batch_size: int) -> List[Contestant]:
    """Public entries of rounds that are still running, a rotating slice per run
    so every entry is looked at once per cycle and no run is unbounded."""
    slot = int(now.timestamp() // 3600) % cycle_hours
    today: date = now.date()
    return (
        db.query(Contestant)
        .join(Round, Round.id == Contestant.round_id)
        .filter(
            Contestant.is_deleted == False,  # noqa: E712
            Contestant.video_media_ids.isnot(None),
            Contestant.video_media_ids.ilike("%http%"),
            ~removed_entry_clause(),
            public_entry_clause(),
            Round.status.notin_([RoundStatus.COMPLETED, RoundStatus.CANCELLED]),
            (Round.voting_end_date.is_(None)) | (Round.voting_end_date >= today),
            (Contestant.id % cycle_hours) == slot,
        )
        .order_by(Contestant.id.asc())
        .limit(batch_size)
        .all()
    )


def _latest_link_events(db: Session, contestant_ids: Iterable[int]) -> Dict[int, AuditTrail]:
    ids = list(contestant_ids)
    if not ids:
        return {}
    rows = (
        db.query(AuditTrail)
        .filter(AuditTrail.table_name == AUDIT_TABLE, AuditTrail.record_id.in_(ids),
                AuditTrail.action.in_(_LINK_ACTIONS))
        .order_by(AuditTrail.id.asc())
        .all()
    )
    return {row.record_id: row for row in rows}      # later rows overwrite earlier ones


def _audit(db: Session, contestant_id: int, action: str, now: datetime, result: EntryLinkResult,
           old: Optional[dict] = None, new: Optional[dict] = None) -> None:
    details = {"providers": sorted({c.provider for c in result.checks if c.provider}),
               "http_status": sorted({c.http_status for c in result.checks if c.http_status})}
    db.add(AuditTrail(table_name=AUDIT_TABLE, record_id=contestant_id, action=action, old_values=old,
                      new_values={**(new or {}), **details}, user_id=None, created_at=now, updated_at=now))


def run_link_recheck(db: Session, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """One bounded, idempotent pass. Returns counts only (no member data)."""
    now = now or datetime.utcnow()
    summary: Dict[str, Any] = {"enabled": bool(settings.CREATIVE_LINK_CHECK_ENABLED), "candidates": 0,
                               "available": 0, "dead": 0, "unknown": 0, "suspected": 0, "removed": 0,
                               "cleared": 0, "aborted": False}
    if not settings.CREATIVE_LINK_CHECK_ENABLED:
        return summary
    cycle_hours = max(1, int(settings.CREATIVE_LINK_CHECK_CYCLE_HOURS))
    entries = _candidates(db, now=now, cycle_hours=cycle_hours,
                          batch_size=max(1, int(settings.CREATIVE_LINK_CHECK_BATCH_SIZE)))
    summary["candidates"] = len(entries)
    results: List[Tuple[Contestant, EntryLinkResult]] = []
    for entry in entries:
        result = check_entry_links(entry.video_media_ids)
        results.append((entry, result))
        if result.status == LinkStatus.AVAILABLE:
            summary["available"] += 1
        elif result.status == LinkStatus.DEAD:
            summary["dead"] += 1
        else:
            summary["unknown"] += 1

    definitive = summary["available"] + summary["dead"]
    if definitive >= ANOMALY_MIN_DEFINITIVE and summary["dead"] / definitive > ANOMALY_DEAD_RATIO:
        # Far too many "dead" answers at once: a provider or network anomaly.
        summary["aborted"] = True
        logger.warning("Creative link recheck ignored: %s of %s definitive answers were 'not found'",
                       summary["dead"], definitive)
        return summary

    latest = _latest_link_events(db, [e.id for e, _ in results])
    confirm_before = now - timedelta(hours=max(0, int(settings.CREATIVE_LINK_CONFIRM_AFTER_HOURS)))
    for entry, result in results:
        last = latest.get(entry.id)
        suspected = last is not None and last.action == ACTION_SUSPECT
        if result.status == LinkStatus.DEAD:
            if suspected and last.created_at <= confirm_before:
                previous = entry.verification_status
                entry.verification_status = CREATIVE_UNAVAILABLE_STATUS
                _audit(db, entry.id, ACTION_REMOVED, now, result,
                       old={"verification_status": previous},
                       new={"verification_status": CREATIVE_UNAVAILABLE_STATUS})
                summary["removed"] += 1
            elif not suspected:
                _audit(db, entry.id, ACTION_SUSPECT, now, result)
                summary["suspected"] += 1
            # suspected but too recent: wait for the confirmation delay (idempotent)
        elif result.status == LinkStatus.AVAILABLE and suspected:
            _audit(db, entry.id, ACTION_OK, now, result)
            summary["cleared"] += 1
    db.commit()
    if summary["suspected"] or summary["removed"] or summary["cleared"]:
        logger.info("Creative link recheck: %s", {k: v for k, v in summary.items() if k != "enabled"})
    return summary


class CreativeLinkScheduler:
    """Background recheck of external creative links (same shape as the other
    in-process schedulers; the blocking work runs in a worker thread)."""

    def __init__(self, check_interval_seconds: Optional[int] = None):
        self.check_interval = int(check_interval_seconds or settings.CREATIVE_LINK_CHECK_INTERVAL_SECONDS)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Creative link scheduler started (interval: %ss, enabled: %s)",
                    self.check_interval, settings.CREATIVE_LINK_CHECK_ENABLED)

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        await asyncio.sleep(120)   # let the application finish starting
        while self.running:
            try:
                await self._check_creative_links()
            except Exception as exc:  # noqa: BLE001
                logger.error("Creative link recheck failed: %s", type(exc).__name__)
            await asyncio.sleep(self.check_interval)

    async def _check_creative_links(self):
        await asyncio.to_thread(self._run_once)

    @staticmethod
    def _run_once() -> Dict[str, Any]:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            return run_link_recheck(db)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
