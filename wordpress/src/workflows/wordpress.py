"""WordPress REST API wrapper as a Mistral Workflow.

Scope: read + write (GET, POST, PUT, PATCH). DELETE is blocked by design.
One deployment serves the portfolio WordPress sites. Credentials come from
environment variables bound as workspace secrets:

  WP_AGENT_USERNAME            default agent login (used when a site has no
                              baked-in username; WP accepts login or email)
  WP_PASS_MARTYROSSMD          Application Password, martyrossmd.com
  WP_PASS_TREATLYME_PROD       Application Password, treatlyme.com
  WP_PASS_TREATLYME_STAGING    Application Password, gm-rebuild.treatlyme.com
  WP_PASS_PARED_PROD           Application Password, paredinsights.org
  WP_PASS_PARED_STAGING        Application Password, env-paredinsights-premstaging.kinsta.cloud
  WP_PASS_GROWTH_MECHANICS     Application Password, growth-mechanics.com
  WP_PASS_LIVEUTIFREE_PROD     Application Password, liveutifree.com
  WP_PASS_LIVEUTIFREE_STAGING  Application Password, prem-staging.liveutifree.com

Optional outer HTTP auth (htaccess-style basic auth in front of a site,
value format "user:pass"). The fallback is read-only in practice: a request
that clears the outer layer cannot also carry WP app-password credentials,
so authenticated WP operations fail until /wp-json is exempted from the
outer auth in the web server config:

  WP_HTTPAUTH_TREATLYME_STAGING

Per-site usernames: SITES below may carry a baked-in "username" (not a
secret). treatlyme uses the WP login "vibeness". Sites without one use
WP_AGENT_USERNAME; WP core accepts a login name or an email there.

Environment policy: sites with staging (treatlyme, pared, liveutifree) are
always called on staging by default ("environment": "auto"). Pass
"environment": "production" to target production explicitly. martyrossmd
and growth-mechanics have no staging and always target production.

Not covered: femologist.com (Shopify), tuttu (not WordPress).

Note: keep module-level imports minimal. The Temporal workflow sandbox
restricts module-level imports; heavy libraries are imported inside the
activity body, which runs unsandboxed.
"""

from typing import Any

from pydantic import BaseModel, Field

import mistralai.workflows as workflows

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH"}
WORKER_BUILD = "wp-b2-per-site-user-httpauth"

SITES: dict[str, dict[str, Any]] = {
    "martyrossmd": {
        "production": "https://martyrossmd.com",
        "env_var": "WP_PASS_MARTYROSSMD",
    },
    "treatlyme": {
        "username": "vibeness",
        "production": "https://treatlyme.com",
        "staging": "https://gm-rebuild.treatlyme.com",
        "env_var": "WP_PASS_TREATLYME_PROD",
        "staging_env_var": "WP_PASS_TREATLYME_STAGING",
        "staging_http_auth_env_var": "WP_HTTPAUTH_TREATLYME_STAGING",
    },
    "pared": {
        "production": "https://paredinsights.org",
        "staging": "https://env-paredinsights-premstaging.kinsta.cloud",
        "env_var": "WP_PASS_PARED_PROD",
        "staging_env_var": "WP_PASS_PARED_STAGING",
        "staging_http_auth_env_var": "WP_HTTPAUTH_PARED_STAGING",
    },
    "growth-mechanics": {
        "production": "https://growth-mechanics.com",
        "env_var": "WP_PASS_GROWTH_MECHANICS",
    },
    "liveutifree": {
        "production": "https://liveutifree.com",
        "staging": "https://prem-staging.liveutifree.com",
        "env_var": "WP_PASS_LIVEUTIFREE_PROD",
        "staging_env_var": "WP_PASS_LIVEUTIFREE_STAGING",
        "staging_http_auth_env_var": "WP_HTTPAUTH_LIVEUTIFREE_STAGING",
    },
}

ALL_ENV_VARS = ["WP_AGENT_USERNAME"] + sorted(
    {site["env_var"] for site in SITES.values()}
    | {site["staging_env_var"] for site in SITES.values() if site.get("staging_env_var")}
    | {site["staging_http_auth_env_var"] for site in SITES.values() if site.get("staging_http_auth_env_var")}
)


class WordPressInput(BaseModel):
    site: str = Field(description="Site key: martyrossmd, treatlyme, pared, growth-mechanics, liveutifree")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, or PATCH")
    path: str = Field(default="", description="Path relative to /wp-json, e.g. wp/v2/posts, wp/v2/pages/<id>, wp/v2/plugins, wp/v2/settings, wp/v2/media/<id>")
    environment: str = Field(default="auto", description="auto (staging-first policy), staging, or production")
    query: dict[str, Any] = Field(default_factory=dict, description="Query parameters, e.g. {'search': '...', 'per_page': 20}")
    body: dict[str, Any] = Field(default_factory=dict, description="JSON request body")
    debug: bool = Field(default=False, description="Return a masked shape report of the credential env vars instead of calling the site. Never exposes secret values.")


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
async def wordpress_request(
    site: str,
    method: str,
    path: str,
    environment: str,
    query: dict[str, Any],
    body: dict[str, Any],
    debug: bool,
) -> dict[str, Any]:
    """Call the WP REST API for one portfolio site with credentials from the environment."""
    # Lazy imports: the activity runs unsandboxed, so these are safe here.
    import os

    import httpx

    site = site.strip().lower()
    if site not in SITES:
        return {
            "status": 0,
            "error": True,
            "data": {"message": f"Unknown site key: {site}", "available": sorted(SITES)},
        }
    cfg = SITES[site]

    environment = environment.strip().lower()
    if environment == "auto":
        environment = "staging" if cfg.get("staging") else "production"
    if environment not in ("staging", "production"):
        return {
            "status": 0,
            "error": True,
            "data": {"message": "environment must be auto, staging, or production"},
        }
    if environment == "staging" and not cfg.get("staging"):
        return {
            "status": 0,
            "error": True,
            "data": {"message": f"Site {site} has no staging environment"},
        }

    target = cfg["staging"] if environment == "staging" else cfg["production"]
    env_var = cfg["staging_env_var"] if environment == "staging" else cfg["env_var"]
    http_auth_var = cfg.get("staging_http_auth_env_var") if environment == "staging" else cfg.get("http_auth_env_var")

    if debug:
        return {
            "debug": True,
            "worker_build": WORKER_BUILD,
            "credentials": {
                name: _value_shape(name, os.environ.get(name, ""), name == "WP_AGENT_USERNAME")
                for name in ALL_ENV_VARS
            },
        }

    # Username: per-site if baked in, else the shared agent login (login or email both work).
    username = cfg.get("username") or os.environ.get("WP_AGENT_USERNAME", "")
    # Application Passwords are displayed with spaces; the REST API wants them without.
    password = "".join(os.environ.get(env_var, "").split())

    if not username or not password:
        return {
            "status": 0,
            "error": True,
            "data": {
                "message": "Missing credential env var in worker",
                "username_source": "site" if cfg.get("username") else "WP_AGENT_USERNAME",
                "WP_AGENT_USERNAME": _value_shape("WP_AGENT_USERNAME", os.environ.get("WP_AGENT_USERNAME", ""), True),
                env_var: _value_shape(env_var, password, False),
            },
        }

    method = method.upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"Method {method} not allowed. Allowed: {sorted(ALLOWED_METHODS)}.")

    # Normalize: accept "wp/v2/posts", "/wp/v2/posts", "/wp-json/wp/v2/posts".
    clean = path.strip()
    if clean.startswith("/wp-json"):
        clean = clean[len("/wp-json"):]
    clean = clean.strip("/")
    url = target.rstrip("/") + "/wp-json/" + clean

    headers = {"User-Agent": "GrowthMechanics-WordPress-Workflow/1.0"}

    def _is_json(resp: Any) -> bool:
        return "json" in (resp.headers.get("content-type", "") or "")

    async def _attempt(auth: tuple[str, str]) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            return await client.request(
                method,
                url,
                params=query or None,
                json=body or None,
                headers=headers,
                auth=auth,
            )

    auth_mode = "wp_app_password"
    try:
        resp = await _attempt((username, password))
    except httpx.HTTPError as exc:
        return {
            "status": 0,
            "error": True,
            "data": {"message": f"Transport error: {type(exc).__name__}: {str(exc)[:300]}"},
            "site": site,
            "environment": environment,
            "target": target,
        }

    # Outer basic-auth fallback: an htaccess-style 401 returns non-JSON. If
    # outer credentials are configured, retry through that layer. The outer
    # layer consumes the Authorization header, so WP auth cannot ride along:
    # reads of public endpoints work, authenticated WP operations do not.
    if resp.status_code == 401 and not _is_json(resp) and http_auth_var:
        outer = os.environ.get(http_auth_var, "")
        outer_user, _, outer_pass = outer.partition(":")
        if outer_user and outer_pass:
            try:
                resp = await _attempt((outer_user, outer_pass))
                auth_mode = "http_auth_fallback"
            except httpx.HTTPError as exc:
                return {
                    "status": 0,
                    "error": True,
                    "data": {"message": f"Transport error during http-auth fallback: {type(exc).__name__}: {str(exc)[:300]}"},
                    "site": site,
                    "environment": environment,
                    "target": target,
                }

    result: dict[str, Any] = {
        "status": resp.status_code,
        "site": site,
        "environment": environment,
        "target": target,
        "auth_mode": auth_mode,
    }
    if auth_mode == "http_auth_fallback":
        result["warning"] = (
            "Request passed an outer basic-auth layer using the configured "
            "http-auth credentials. WP application-password auth could not be "
            "sent through it, so this response is unauthenticated WP. Exempt "
            "/wp-json from the outer auth in the web server config to restore "
            "authenticated WP access."
        )
    www_auth = resp.headers.get("www-authenticate")
    if www_auth:
        result["www_authenticate"] = www_auth[:200]
    link = resp.headers.get("link")
    if link:
        result["link_header"] = link  # WP REST pagination
    try:
        result["data"] = resp.json()
    except Exception:
        result["text"] = resp.text[:2000]
    if resp.status_code >= 400:
        result["error"] = True
    return result


@workflows.workflow.define(
    name="wordpress",
    workflow_display_name="WordPress",
    workflow_description="Read and write access to portfolio WordPress sites via the WP REST API (staging-first, no deletes).",
)
class WordPressRequestWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, input: WordPressInput) -> dict[str, Any]:
        return await wordpress_request(
            input.site,
            input.method,
            input.path,
            input.environment,
            input.query,
            input.body,
            input.debug,
        )
