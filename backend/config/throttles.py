from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class _DynamicRateMixin:
    """
    Reads the throttle rate from api_settings at request time, not at class
    definition time.

    DRF sets `THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES` as a class
    attribute once on import. Django's `override_settings` fires `setting_changed`
    → `api_settings.reload()`, which clears the api_settings cache — but the
    stale class attribute still points at the old dict.

    Overriding `get_rate()` to call `api_settings.DEFAULT_THROTTLE_RATES` at
    request time means we always read the current (possibly overridden) value.
    This is required for `override_settings` in tests to work correctly.
    """

    scope: str

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)


class ProductLookupAnonThrottle(_DynamicRateMixin, AnonRateThrottle):
    """
    Rate: 20/minute per IP for anonymous product lookups.

    Rationale: barcode enumeration is the main scraping risk here — a bot
    iterating the UPC space to harvest our halal/haram classification data.
    20/minute allows realistic shopping (5–10 items per trip) while making
    bulk enumeration impractical.

    AnonRateThrottle returns None (no-op) for authenticated requests, so
    authenticated users are governed only by ProductLookupUserThrottle.
    """

    scope = "product_lookup_anon"


class ProductLookupUserThrottle(_DynamicRateMixin, UserRateThrottle):
    """
    Rate: 100/minute per authenticated user for product lookups.

    More generous than anonymous because authenticated users are accountable
    by user ID. 100/minute ≈ 1.7 scans/second — already beyond any human
    scanning pattern but allows generous app-side retry logic.
    """

    scope = "product_lookup_user"


class ScanCreateThrottle(_DynamicRateMixin, UserRateThrottle):
    """
    Rate: 30/minute per authenticated user for scan logging.

    Write endpoint — protects the DB against scan-spam abuse. No legitimate
    user creates more than one scan every two seconds.
    """

    scope = "scan_create"


class ScanHistoryThrottle(_DynamicRateMixin, UserRateThrottle):
    """Rate: 60/minute per authenticated user for scan history reads."""

    scope = "scan_history"


class AppleAuthThrottle(_DynamicRateMixin, SimpleRateThrottle):
    """
    Rate: 5/minute per IP for Apple auth token exchange.

    Strictest throttle in the app. Auth endpoints are the primary target
    for brute-force and credential-stuffing attacks. Uses SimpleRateThrottle
    (always IP-based) rather than AnonRateThrottle so the IP limit applies
    even if the caller carries an existing Bearer token — auth bootstrapping
    should always be IP-gated regardless of existing auth state.

    5/minute covers the legitimate case (one auth per device per session)
    with a small burst budget for retries, while blocking automation.
    """

    scope = "apple_auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
