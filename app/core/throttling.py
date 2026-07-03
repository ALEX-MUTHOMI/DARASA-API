"""Scoped throttle classes for public, unauthenticated endpoints.

Public endpoints that exist before authentication (e.g. parent login) cannot
rely on per-user throttling, only per-client-address throttling. Each public
endpoint gets its own named scope so one abusive flow cannot exhaust another
endpoint's rate budget, and so `DEFAULT_THROTTLE_RATES` stays legible.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle


class ParentLoginRateThrottle(AnonRateThrottle):
    scope = "parent_login"
