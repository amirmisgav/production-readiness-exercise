import os
import random
import time

# Feature flag: when PAGERDUTY_ENABLED="false", the integration is skipped.
# This wraps the risky third-party integration point to allow safe degradation.
PAGERDUTY_ENABLED = os.getenv("PAGERDUTY_ENABLED", "true").lower() in ("true", "1", "yes")

# Stand-in for the real PagerDuty client. Do not modify: treat this as a
# third-party system you don't control.


def call_pagerduty_webhook(payload: dict) -> str:
    if not PAGERDUTY_ENABLED:
        return "skipped (feature flag off)"

    if payload.get("environment") == "production":
        time.sleep(3)
        if random.random() < 0.4:
            raise ConnectionError("504 Gateway Timeout: PagerDuty upstream unavailable")
    return "delivered"


def log_to_audit_store(payload: dict) -> None:
    pass
