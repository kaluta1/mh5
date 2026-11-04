"""The eight MyHigh5 advertising packages (Advertising Phase A, owner-approved minimum prices 2026-11-04).

ONE registry for: the package code, its campaign pricing model, its minimum rate (a floor: a campaign may
pay more, never less), the unit it is billed by, the ONE event type that charges it, and whether the
application can actually deliver and measure it today (readiness). Nothing here charges money or creates
any earning; it is the contract the serving, validation and settlement code reads.

Daily City also needs adv_settings.daily_city_min_impressions (the approved minimum delivery threshold):
while it is not determined, Daily City cannot be switched on, drafted or bought.

Purchasable = readiness OK AND the package is switched on (adv_settings.enabled_packages; Standard CPM is
the existing package and follows the existing campaigns/funding switches) AND campaigns_enabled AND
funding_enabled. Every new package is OFF by default. A package that is NOT READY cannot be switched on.

Billing model per package (the charge is always server-side, at the campaign's stored rate):
  cpm          VIEWABLE impression (>= 50% for >= 1 s, MRC display)   reserve rate/1000 at decision
  cpm_video    VIDEO_2S: >= 2 s continuous playback, >= 50% in view   reserve rate/1000 at decision
  cpc          CLICK through the MyHigh5 redirect                       reserve rate at decision
  cpv          VIDEO_VIEW: >= 10 s playback (or the whole video)        reserve rate at decision
  engagement   CLICK on the call-to-action (the only implemented action) reserve rate at decision
  lead         ACCEPTED lead (charged at acceptance, not at decision)   no reservation at decision
  daily_local  one booked local-area day (settled after the day)        booked fee in the campaign budget
  daily_city   one booked city day: earned only with at least the        booked fee in the campaign budget
               threshold of valid viewable impressions from verified residents
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Optional

SIX = Decimal("0.000001")

# Event types (adv_impression_events.event_type).
SERVED, VIEWABLE, VIDEO_2S, VIDEO_VIEW, CLICK = "SERVED", "VIEWABLE", "VIDEO_2S", "VIDEO_VIEW", "CLICK"
EVENT_TYPES = (SERVED, VIEWABLE, VIDEO_2S, VIDEO_VIEW, CLICK)

VIDEO_IMPRESSION_MIN_MS = 2000          # approved: two seconds
CPV_MIN_MS = 10000                      # approved (provisional): ten seconds, or the whole video if shorter
CLICK_MIN_DELAY_MS = 1000               # a click within a second of serving is not a human click
ENGAGEMENT_ACTIONS = ("CTA_CLICK",)     # save / share / follow do not exist on ad units: not billable


@dataclass(frozen=True)
class Package:
    code: str
    pricing_model: str                  # adv_campaigns.pricing_model
    name: str
    floor: Decimal                      # minimum rate, USD
    unit: str
    billable_event: Optional[str]       # the event type that charges; None = settled otherwise
    per_thousand: bool = False          # the rate is per 1,000 units
    booking: Optional[str] = None       # LOCAL | CITY for the daily packages
    not_ready: Optional[str] = None     # why the application cannot deliver or measure it today


PACKAGES = {p.code: p for p in (
    Package("cpm", "CPM", "Standard CPM", Decimal("0.50"), "1,000 valid viewable impressions", VIEWABLE,
            per_thousand=True),
    Package("cpm_video", "CPM_VIDEO", "Video CPM", Decimal("1.00"), "1,000 qualifying video impressions (2 s)",
            VIDEO_2S, per_thousand=True,
            not_ready="Video creatives cannot be stored or played yet: the media store caps videos at 32 MB, "
                      "has no duration check and no ad video player exists"),
    Package("cpc", "CPC", "Cost per click", Decimal("0.05"), "one valid click", CLICK),
    Package("cpv", "CPV", "Cost per view", Decimal("0.005"), "one qualifying video view (10 s or complete)",
            VIDEO_VIEW,
            not_ready="Video creatives cannot be stored or played yet (see Video CPM)"),
    Package("engagement", "ENGAGEMENT", "Engagement", Decimal("0.02"), "one qualifying engagement (call-to-action)",
            CLICK),
    Package("lead", "LEAD", "Lead", Decimal("0.25"), "one accepted lead", None,
            not_ready="Lead collection needs an approved retention period and privacy notice before any "
                      "personal data can be stored"),
    Package("daily_local", "DAILY_LOCAL", "Daily Local", Decimal("1.00"), "one booked local-area day", None,
            booking="LOCAL",
            not_ready="No verified local-area boundaries exist inside cities (only countries and cities)"),
    Package("daily_city", "DAILY_CITY", "Daily City", Decimal("5.00"), "one booked city day", None,
            booking="CITY"),
)}

BY_MODEL = {p.pricing_model: p for p in PACKAGES.values()}
PRICING_MODELS = tuple(BY_MODEL)
LEGACY_CODE = "cpm"                     # campaigns written before Phase A have pricing_model 'CPM'


class PackageError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def get(code: Optional[str]) -> Package:
    """A known, current package, or PackageError (unknown and retired codes are refused)."""
    package = PACKAGES.get(str(code or "").strip().lower())
    if package is None:
        raise PackageError("UNKNOWN_PACKAGE", f"Unknown advertising package: {code!r}")
    return package


def of_model(pricing_model: Optional[str]) -> Package:
    return BY_MODEL.get(str(pricing_model or "CPM").upper(), PACKAGES[LEGACY_CODE])


def exact(value) -> Decimal:
    """A money value at the advertising precision (6 decimals), never through float."""
    if isinstance(value, float):
        raise PackageError("INVALID_RATE", "Money must not be a binary float")
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise PackageError("INVALID_RATE", "The rate is not a number") from None
    if not d.is_finite():
        raise PackageError("INVALID_RATE", "The rate is not a number")
    if d != d.quantize(SIX):
        raise PackageError("INVALID_RATE", "Rates have at most 6 decimals")
    return d.quantize(SIX)


def validate_rate(package: Package, rate) -> Decimal:
    """The campaign's rate: at least the approved floor, at most 6 decimals."""
    d = exact(rate)
    if d < package.floor:
        raise PackageError("RATE_BELOW_MINIMUM",
                           f"The minimum {package.name} rate is {package.floor} USD per {package.unit}")
    return d


def unit_charge(package: Package, rate) -> Decimal:
    """The price of ONE billable event at the campaign's rate (6 decimals, rounded down, never up)."""
    d = Decimal(str(rate or 0))
    if d <= 0:
        return Decimal("0")
    if package.per_thousand:
        d = d / Decimal(1000)
    return d.quantize(SIX, rounding=ROUND_DOWN)


def reserve_at_decision(package: Package) -> bool:
    """Packages charged per served-ad event reserve one unit when the ad is served."""
    return package.billable_event is not None


def readiness(package: Package) -> Optional[str]:
    return package.not_ready


def enabled_codes(cfg) -> set:
    """Switched-on package codes. Standard CPM is the existing package (existing switches)."""
    extra = {str(c).lower() for c in (getattr(cfg, "enabled_packages", None) or []) if str(c).lower() in PACKAGES}
    return {LEGACY_CODE} | extra


def threshold_missing(cfg, package: Package) -> bool:
    """Daily City may not run until a minimum delivery threshold is determined (owner decision 1)."""
    return package.booking == "CITY" and not getattr(cfg, "daily_city_min_impressions", None)


THRESHOLD_MESSAGE = "Daily City needs a minimum delivery threshold before it can be offered"


def availability(cfg, package: Package) -> tuple[bool, Optional[str]]:
    """(may a member buy it now, why not). Server-side; the UI only shows this."""
    if package.not_ready:
        return False, "NOT_READY"
    if package.code not in enabled_codes(cfg):
        return False, "PACKAGE_DISABLED"
    if threshold_missing(cfg, package):
        return False, "THRESHOLD_NOT_SET"
    if not getattr(cfg, "campaigns_enabled", False):
        return False, "CAMPAIGNS_DISABLED"
    if not getattr(cfg, "funding_enabled", False):
        return False, "FUNDING_DISABLED"
    return True, None


def require_available(cfg, package: Package) -> None:
    ok, why = availability(cfg, package)
    if not ok:
        detail = (package.not_ready if why == "NOT_READY" else THRESHOLD_MESSAGE if why == "THRESHOLD_NOT_SET"
                  else "This advertising package is not available yet.")
        raise PackageError(why or "PACKAGE_DISABLED", f"{package.name}: {detail}", 409)


def require_creatable(cfg, package: Package) -> None:
    """A draft may be prepared while campaigns are closed (existing CPM behaviour), but never for a
    package that is not ready or not switched on."""
    if package.not_ready:
        raise PackageError("NOT_READY", f"{package.name}: {package.not_ready}", 409)
    if package.code not in enabled_codes(cfg):
        raise PackageError("PACKAGE_DISABLED", f"{package.name} is not available yet.", 409)
    if threshold_missing(cfg, package):
        raise PackageError("THRESHOLD_NOT_SET", THRESHOLD_MESSAGE, 409)


def check_enable(codes, cfg=None) -> list:
    """Validate an administrator's enabled_packages list: known, ready, threshold set where one is needed,
    not Standard CPM (implicit). cfg = the settings as they will be after the change."""
    out = []
    for code in codes or []:
        package = get(code)
        if package.not_ready:
            raise PackageError("NOT_READY", f"{package.name} cannot be switched on: {package.not_ready}", 409)
        if cfg is not None and threshold_missing(cfg, package):
            raise PackageError("THRESHOLD_NOT_SET", THRESHOLD_MESSAGE, 409)
        if package.code != LEGACY_CODE and package.code not in out:
            out.append(package.code)
    return out
