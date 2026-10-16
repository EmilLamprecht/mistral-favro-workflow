"""Generic Favro REST API wrapper as a Mistral Workflow.

Scope: read + write (GET, POST, PUT, PATCH). DELETE is blocked by design.
Credentials come from environment variables bound as workspace secrets:
  FAVRO_USER_EMAIL, FAVRO_API_TOKEN, FAVRO_ORG_ID

Note: keep module-level imports minimal. The Temporal workflow sandbox
restricts module-level imports; heavy libraries are imported inside the
activity body, which runs unsandboxed.
"""

from typing import Any

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

FAVRO_BASE_URL = "https://favro.com/api/v1"
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH"}


class FavroInput(BaseModel):
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, or PATCH")
    path: str = Field(description="API path relative to /api/v1, e.g. /boards or /cards/<cardId>")
    query: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    body: dict[str, Any] = Field(default_factory=dict, description="JSON request body")
    extra_headers: dict[str, str] = Field(default_factory=dict, description="Additional Favro headers")


@workflows.activity()
async def favro_request(
    method: str,
    path: str,
    query: dict[str, Any],
    body: dict[str, Any],
    extra_headers: dict[str, str],
) -> dict[str, Any]:
    """Call the Favro REST API with credentials from the environment."""
    # Lazy imports: the activity runs unsandboxed, so these are safe here.
    import os

    import httpx

    email = os.environ["FAVRO_USER_EMAIL"]
    token = os.environ["FAVRO_API_TOKEN"]
    org_id = os.environ.get("FAVRO_ORG_ID", "")

    method = method.upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Method {method} not allowed. Allowed: {sorted(ALLOWED_METHODS)}.")
    if not path.startswith("/"):
        path = "/" + path

    headers = {
        "organizationId": org_id,
        "Content-Type": "application/json",
        **extra_headers,
    }

    async with httpx.AsyncClient(base_url=FAVRO_BASE_URL, timeout=60.0) as client:
        resp = await client.request(
            method,
            path,
            params=query or None,
            json=body or None,
            headers=headers,
            auth=(email, token),
        )

    result: dict[str, Any] = {"status": resp.status_code}
    rate = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")}
    if rate:
        result["rate_limit"] = rate
    try:
        result["data"] = resp.json()
    except Exception:
        result["text"] = resp.text[:2000]
    if resp.status_code >= 400:
        result["error"] = True
    return result


@workflows.workflow.define(
    name="favro",
    workflow_display_name="Favro",
    workflow_description="Read and write access to the Favro REST API (no deletes).",
)
class FavroRequestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: FavroInput) -> dict[str, Any]:
        return await favro_request(
            input.method,
            input.path,
            input.query,
            input.body,
            input.extra_headers,
        )
