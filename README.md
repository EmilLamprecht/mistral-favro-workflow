# mistral-favro-workflow

A Mistral Workflow that wraps the Favro REST API, deployed as a managed deployment. Read + write access (GET/POST/PUT/PATCH); DELETE is blocked.

## Workflow input

```json
{"method": "GET", "path": "/widgets", "query": {}, "body": {}}
```

Note: boards are called "widgets" in the Favro API. There is no /boards endpoint.

Set "debug": true to get a masked shape report of the credential env vars (never the values themselves). Useful after rotating secrets; the worker reads secrets at boot, so restart the deployment after changing secret values.

## Required workspace secrets (bound at deploy time)

- FAVRO_USER_EMAIL - Favro account email (the email you sign in with, NOT your user ID)
- FAVRO_API_TOKEN - token from Favro Profile -> API Tokens
- FAVRO_ORG_ID - Favro organization ID (second segment of the favro.com/organization URL)

## Secret rotation

After changing a secret value in the workspace Secrets Manager, the running worker keeps the value it read at boot. Re-deploy the current revision (or restart from the deployment Settings tab) so a fresh worker picks up the new value.
