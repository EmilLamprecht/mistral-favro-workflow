"""Generic PostHog REST API wrapper as a Mistral Workflow.

Scope: read + write (GET, POST, PUT, PATCH). DELETE is blocked by design.
Credentials come from environment variables bound as workspace secrets:
  POSTHOG_API_KEY (personal API key, read scope recommended)
Every call is project-addressable: pass e.g. path="/projects/66681/query",
so the active project in the PostHog UI is irrelevant.
An explicit "Authorization" header in extra_headers overrides the env
credentials, which is useful for testing a credential pair directly.

Note: keep module-level imports minimal. The Temporal workflow sandbox
restricts module-level imports; heavy libraries are imported inside the
activity body, which runs unsandboxed.
"""

from typing import Any

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

POSTHOG_BASE_URL = "https://eu.posthog.com/api"
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH"}
WORKER_BUILD = "b1"


class PosthogInput(BaseModel):
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, or PATCH")
    path: str = Field(default="/organizations/me", description="API path relative to /api, e.g. /projects/66681/query")
    query: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    body: dict[str, Any] = Field(default_factory=dict, description="JSON request body")
    extra_headers: dict[str, str] = Field(default_factory=dict, description="Additional headers. An Authorization header overrides the env credentials for this call.")
    debug: bool = Field(default=False, description="Return a masked shape report of the credential env vars instead of calling PostHog. Never exposes secret values.")


def _value_shape(name: str, value: str) -> dict[str, Any]:
    return {
        "env_var": name,
        "set": bool(value),
        "length": len(value),
        "contains_quote": ('"' in value) or ("'" in value),
        "contains_whitespace": any(ch.isspace() for ch in value),
        "needs_trim": value != value.strip(),
    }


@workflows.activity()
async def posthog_request(
    method: str,
    path: str,
    query: dict[str, Any],
    body: dict[str, Any],
    extra_headers: dict[str, str],
    debug: bool,
) -> dict[str, Any]:
    """Call the PostHog REST API with credentials from the environment."""
    import os

    import httpx

    api_key = os.environ.get("POSTHOG_API_KEY", "")

    if debug:
        return {
            "debug": True,
            "POSTHOG_API_KEY": _value_shape("POSTHOG_API_KEY", api_key),
        }

    auth_override = any(k.lower() == "authorization" for k in extra_headers)

    if not auth_override and not api_key:
        return {
            "status": 0,
            "error": True,
            "data": {
                "message": "Missing credential env var POSTHOG_API_KEY in worker",
                "POSTHOG_API_KEY": _value_shape("POSTHOG_API_KEY", api_key),
            },
        }

    method = method.upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Method {method} not allowed. Allowed: {sorted(ALLOWED_METHODS)}.")
    if not path.startswith("/"):
        path = "/" + path

    headers = {
        "Content-Type": "application/json",
        **extra_headers,
    }
    if not auth_override:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(base_url=POSTHOG_BASE_URL, timeout=60.0) as client:
        resp = await client.request(
            method,
            path,
            params=query or None,
            json=body or None,
            headers=headers,
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
    name="posthog",
    workflow_display_name="PostHog",
    workflow_description="Read and write access to the PostHog REST API (no deletes). Project-addressable: path includes the project id.",
)
class PosthogRequestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: PosthogInput) -> dict[str, Any]:
        return await posthog_request(
            input.method,
            input.path,
            input.query,
            input.body,
            input.extra_headers,
            input.debug,
        )
