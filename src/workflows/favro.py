"""Generic Favro REST API wrapper as a Mistral Workflow.

Scope: read + write (GET, POST, PUT, PATCH). DELETE is blocked by design.
Credentials come from environment variables bound as workspace secrets:
  FAVRO_USER_EMAIL, FAVRO_API_TOKEN, FAVRO_ORG_ID
An explicit "Authorization" header in extra_headers overrides the env
credentials, which is useful for testing a credential pair directly.

Note: keep module-level imports minimal. The Temporal workflow sandbox
restricts module-level imports; heavy libraries are imported inside the
activity body, which runs unsandboxed.
"""

from typing import Any

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

FAVRO_BASE_URL = "https://favro.com/api/v1"
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH"}
WORKER_BUILD = "b4-auth-override"


class FavroInput(BaseModel):
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, or PATCH")
    path: str = Field(default="/organizations", description="API path relative to /api/v1, e.g. /widgets or /cards/<cardId>")
    query: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    body: dict[str, Any] = Field(default_factory=dict, description="JSON request body")
    extra_headers: dict[str, str] = Field(default_factory=dict, description="Additional Favro headers. An Authorization header overrides the env credentials for this call.")
    debug: bool = Field(default=False, description="Return a masked shape report of the credential env vars instead of calling Favro. Never exposes secret values.")


def _value_shape(name: str, value: str, is_email: bool) -> dict[str, Any]:
    """Describe a secret env value without revealing it."""
    has_at = "@" in value
    shape: dict[str, Any] = {
        "env_var": name,
        "set": bool(value),
        "length": len(value),
        "contains_quote": ('"' in value) or ("'" in value),
        "contains_whitespace": any(ch.isspace() for ch in value),
        "needs_trim": value != value.strip(),
    }
    if is_email:
        local, _, domain = value.partition("@")
        shape["masked"] = (local[:2] + "***@" + domain) if has_at else value[:2] + "*** (no @ sign)"
    return shape


@workflows.activity()
async def favro_request(
    method: str,
    path: str,
    query: dict[str, Any],
    body: dict[str, Any],
    extra_headers: dict[str, str],
    debug: bool,
) -> dict[str, Any]:
    """Call the Favro REST API with credentials from the environment."""
    # Lazy imports: the activity runs unsandboxed, so these are safe here.
    import os
    import time

    import httpx

    email = os.environ.get("FAVRO_USER_EMAIL", "")
    token = os.environ.get("FAVRO_API_TOKEN", "")
    org_id = os.environ.get("FAVRO_ORG_ID", "")

    if debug:
        meta: dict[str, Any] = {"worker_build": WORKER_BUILD}
        try:
            with open("/proc/uptime") as f:
                host_uptime_s = float(f.read().split()[0])
            with open("/proc/self/stat") as f:
                start_ticks = float(f.read().rsplit(") ", 1)[1].split()[19])
            boot_wall = time.time() - host_uptime_s
            meta["worker_started_at"] = boot_wall + (start_ticks / 100.0)
        except Exception as exc:
            meta["worker_meta_error"] = str(exc)[:120]
        return {
            "debug": True,
            **meta,
            "FAVRO_USER_EMAIL": _value_shape("FAVRO_USER_EMAIL", email, True),
            "FAVRO_API_TOKEN": _value_shape("FAVRO_API_TOKEN", token, False),
            "FAVRO_ORG_ID": _value_shape("FAVRO_ORG_ID", org_id, False),
        }

    auth_override = any(k.lower() == "authorization" for k in extra_headers)

    if not auth_override and (not email or not token):
        return {
            "status": 0,
            "error": True,
            "data": {
                "message": "Missing credential env var in worker",
                "FAVRO_USER_EMAIL": _value_shape("FAVRO_USER_EMAIL", email, True),
                "FAVRO_API_TOKEN": _value_shape("FAVRO_API_TOKEN", token, False),
            },
        }

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
            auth=None if auth_override else (email, token),
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
            input.debug,
        )
