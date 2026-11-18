# ADR-0002: PagerDuty Integration - Real-time Notifications vs. System Resilience

* **Status**: Accepted
* **Date**: 2026-11-18
* **Deciders**: Team

## Context and Problem Statement

The application integrates with PagerDuty via a webhook to notify on deployment events. The current implementation (`app/downstream.py`) calls the PagerDuty webhook synchronously within the request lifecycle. In a production environment, this integration has two significant characteristics:

1. **Artificial latency**: The mock implementation introduces a fixed 3-second sleep for production environments.
2. **Unreliable upstream**: 40% of requests fail with a `ConnectionError: 504 Gateway Timeout` due to PagerDuty upstream unavailability.

Forcing every deployment notification to wait on PagerDuty creates a risk that a slow or unavailable third-party service will degrade or block the entire deployment API.

## Considered Options

### Option 1: Synchronous Call with Retries and Timeouts
- **Description**: Keep the synchronous approach but add request timeouts, exponential backoff retries, and circuit breaker patterns.
- **Pros**: Simple to implement; preserves real-time notification semantics.
- **Cons**: Does not eliminate the fundamental risk of PagerDuty unavailability; retries may add further latency; complexity in managing partial failures.

### Option 2: Asynchronous Queue-based Decoupling
- **Description**: Push the PagerDuty call into a background job queue (e.g., RQ, Celery, or FastAPI background tasks). The API responds immediately, and the notification is sent asynchronously.
- **Pros**: The deployment API remains fast and resilient to PagerDuty downtime; retries can be managed independently in the worker process.
- **Cons**: Added operational complexity (queue infrastructure, worker processes, at-least-once delivery semantics); eventual consistency means the notification is not truly "real-time"; more code to maintain.

### Option 3: Feature-flagged Toggle with Fallback
- **Description**: Wrap the PagerDuty call in a feature flag. When the flag is off, skip the integration entirely or route to a fallback (e.g., log-only mode). When on, use synchronous calls with timeouts.
- **Pros**: Allows gradual rollout; provides an off-ramp if PagerDuty causes issues; no immediate infrastructure changes required.
- **Cons**: Requires a feature flag framework; may encourage "flag rot" where the fallback path is less tested; does not inherently solve latency.

## Decision Outcome

**Chosen Option: Option 2 – Asynchronous Queue-based Decoupling**

We will move the PagerDuty webhook call into a background task. The `/api/v1/deployments` endpoint will accept the request and return immediately, while the PagerDuty notification is sent as a background task. This ensures the deployment API remains fast and resilient to PagerDuty unavailability.

**Positive consequences:**
- The HTTP API latency is no longer dominated by the 3s PagerDuty sleep.
- If PagerDuty is unavailable, deployment notifications are queued and retried independently, without blocking inbound deployment events.
- The system degrades gracefully: a PagerDuty outage does not cause the deployment API to return errors.

**Negative consequences:**
- Deployment notifications are no longer guaranteed to be delivered in real-time; there is a brief delay before the PagerDuty webhook is invoked.
- Additional operational components are required (message queue/worker infrastructure).
- At-least-once delivery semantics must be handled in the worker, introducing potential duplicate notifications.

**What would make us revisit this decision?**
- If the organization mandates that PagerDuty notifications must be delivered within a strict SLA of the API call completion.
- If the queue infrastructure proves too operationally costly to maintain.
- If a simpler feature-flagged fallback (Option 3) proves sufficient for the team's risk tolerance.

## Consequences

* **API latency**: Reduced from ~3s to sub-100ms for the happy path (subject to background task enqueue latency).
* **Reliability**: Improved – the deployment API is no longer coupled to PagerDuty uptime.
* **Operational overhead**: Increased – requires background task infrastructure and monitoring.
* **Observability**: Background task success/failure must be logged and alerted separately from the API layer.