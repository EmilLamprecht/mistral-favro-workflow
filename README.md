# mistral-favro-workflow

A Mistral Workflow that wraps the Favro REST API, deployed as a managed deployment. Read + write access (GET/POST/PUT/PATCH); DELETE is blocked.

## Workflow input

```json
{"method": "GET", "path": "/boards", "query": {}, "body": {}}
```

## Required workspace secrets (bound at deploy time)

- FAVRO_USER_EMAIL - Favro account email
- FAVRO_API_TOKEN - token from Favro Profile -> API Tokens
- FAVRO_ORG_ID - Favro organization ID (from the Favro URL)
