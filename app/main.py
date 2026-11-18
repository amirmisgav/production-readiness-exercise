import json
import logging
import uuid
from fastapi import FastAPI, Request, Header
from pydantic import BaseModel, Field

from app.downstream import call_pagerduty_webhook, log_to_audit_store

APP_VERSION = "0.1.0"

# Structured logger outputting JSON lines, including trace_id
logger = logging.getLogger("deploy-notifier")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)

app = FastAPI(title="Deploy Notifier Service", version=APP_VERSION)


class DeploymentPayload(BaseModel):
    service: str = Field(..., description="Name of the service being deployed")
    environment: str = Field(..., description="Deployment environment (staging/production)")
    commit_sha: str | None = Field(None, description="Git commit SHA")
    author: str | None = Field(None, description="Author of the commit")


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Extract or generate a trace_id and attach it to the request state."""
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/v1/deployments", response_model=dict)
async def trigger_deployment_notification(
    payload: DeploymentPayload,
    x_trace_id: str = Header(None),
    request: Request = None,
):
    # Determine the trace_id: header > request-state > new UUID
    trace_id = x_trace_id or getattr(request.state, "trace_id", str(uuid.uuid4())) if request else str(uuid.uuid4())

    # Log structured JSON with trace_id visible in the log line
    logger.info(
        json.dumps(
            {
                "event": "deployment_notification_started",
                "trace_id": trace_id,
                "service": payload.service,
                "environment": payload.environment,
            }
        )
    )

    # Feature-flagged PagerDuty integration (safety item)
    pd_status = call_pagerduty_webhook(payload.dict())

    log_to_audit_store(payload.dict())

    response = {
        "status": "dispatched",
        "service": payload.service,
        "environment": payload.environment,
        "delivery_status": pd_status,
    }
    return response