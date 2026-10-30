# mistral-favro-workflow

Mistral Workflows deployed as managed deployments from this repo.

- Favro REST API workflow: read + write access (GET/POST/PUT/PATCH);
  DELETE is blocked by design. Built from the repo root.

- WordPress REST API workflow (wordpress/): wraps the WP REST API for the
  portfolio WordPress sites, staging-first for treatlyme, pared, and
  liveutifree. DELETE is blocked. Built from the wordpress/ subdirectory
  as its own managed deployment ("wordpress"). See wordpress/README.md.

## Workflow input

    {"method": "GET", "path": "/widgets", "query": {}, "body": {}}

Note: boards are called "widgets" in the Favro API. There is no /boards endpoint.

Set "debug": true on either workflow to get a masked shape report of the
credential env vars (never the values themselves). Useful after rotating
secrets; the worker reads secrets at boot, so restart the deployment after
changing secret values.

## Required workspace secrets

Favro deployment:

- FAVRO_USER_EMAIL - Favro account email (the email you sign in with, NOT your user ID)
- FAVRO_API_TOKEN - token from Favro Profile -> API Tokens
- FAVRO_ORG_ID - Favro organization ID (second segment of the favro.com/organization URL)

WordPress deployment:

- WP_AGENT_USERNAME and the WP_PASS_* set, see wordpress/README.md

## Secret rotation

After changing a secret value in the workspace Secrets Manager, the running
worker keeps the value it read at boot. Re-deploy the current revision (or
restart from the deployment Settings tab) so a fresh worker picks up the
new value.
