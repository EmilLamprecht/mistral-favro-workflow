# mistral-wordpress-workflow

A Mistral Workflow that wraps the WordPress REST API for the portfolio
WordPress sites. Deployed as its own managed deployment ("wordpress")
from the wordpress/ build directory of this repo. Read + write access
(GET/POST/PUT/PATCH); DELETE is blocked by design.

## Workflow input

    {"site": "treatlyme", "method": "GET", "path": "wp/v2/posts", "environment": "auto", "query": {"per_page": 5}, "body": {}}

- site: martyrossmd, treatlyme, pared, growth-mechanics, liveutifree
- environment: auto (default) resolves to staging for treatlyme, pared,
  liveutifree; production for martyrossmd, growth-mechanics. Pass
  "production" explicitly to target a live site.
- path is relative to /wp-json. Common paths: wp/v2/posts, wp/v2/pages,
  wp/v2/media/<id>, wp/v2/plugins, wp/v2/themes, wp/v2/settings,
  wp/v2/users/me
- Set "debug": true for a masked shape report of all credential env vars
  (never the values). The worker reads secrets at boot, so restart the
  deployment after rotating a secret.

## Site and environment map

| site             | production                | staging (default target)                              |
|------------------|---------------------------|-------------------------------------------------------|
| martyrossmd      | https://martyrossmd.com   | (none, always production)                             |
| treatlyme        | https://treatlyme.com     | https://gm-rebuild.treatlyme.com                     |
| pared            | https://paredinsights.org | https://env-paredinsights-premstaging.kinsta.cloud   |
| growth-mechanics | https://growth-mechanics.com | (none, always production)                          |
| liveutifree      | https://liveutifree.com   | https://prem-staging.liveutifree.com                 |

Staging-first policy: treatlyme, pared, and liveutifree are always called
on staging unless environment is explicitly "production".

femologist.com is Shopify and tuttu is not WordPress; neither is covered.

## Required workspace secrets (bound at deploy time)

Workspace secret names are lowercase; the deploy binding maps each to the
uppercase env var the worker reads (same pattern as the favro deployment).

| workspace secret (lowercase)   | env var in worker           | what it is                                  |
|--------------------------------|-----------------------------|---------------------------------------------|
| wp_agent_username              | WP_AGENT_USERNAME           | shared agent login, mistral@growth-mechanics.com |
| wp_pass_martyrossmd            | WP_PASS_MARTYROSSMD        | app password, martyrossmd.com               |
| wp_pass_treatlyme_prod         | WP_PASS_TREATLYME_PROD     | app password, treatlyme.com                 |
| wp_pass_treatlyme_staging      | WP_PASS_TREATLYME_STAGING  | app password, gm-rebuild.treatlyme.com      |
| wp_pass_pared_prod             | WP_PASS_PARED_PROD         | app password, paredinsights.org             |
| wp_pass_pared_staging          | WP_PASS_PARED_STAGING      | app password, env-paredinsights-premstaging.kinsta.cloud |
| wp_pass_growth_mechanics       | WP_PASS_GROWTH_MECHANICS   | app password, growth-mechanics.com          |
| wp_pass_liveutifree_prod       | WP_PASS_LIVEUTIFREE_PROD   | app password, liveutifree.com               |
| wp_pass_liveutifree_staging    | WP_PASS_LIVEUTIFREE_STAGING| app password, prem-staging.liveutifree.com  |

Each WordPress install has its own users: the agent user and its
Application Password must be created on every site and staging site
separately.

## Creating the credentials on each site

1. Log in at https://<site>/totes-yeah (fallback: /wp-admin if that fails)
2. Users > Add New: username mistral@growth-mechanics.com, role Administrator
3. As that user: Users > Profile > Application Passwords, add one named
   "mistral-workflow"
4. Copy the generated password into the matching workspace secret. Spaces
   in the password are stripped by the worker automatically.

## Known caveats

- Kinsta staging (env-paredinsights-premstaging.kinsta.cloud) may sit behind
  an extra HTTP auth layer. If so, WP Basic Auth cannot pass through and
  requests return 401 with no WP JSON. Disable staging protection or adapt.
- Security plugins (Wordfence, iThemes) can block /wp-json or Application
  Passwords. If the smoke test fails, check those settings first.
- DELETE is blocked in the workflow. To unpublish content, PATCH the status
  field instead (e.g. status: draft).
- robots.txt, functions.php, and llms.txt are not editable via the WP REST
  API; those fixes stay on the Favro board as manual actions.

## Secret rotation

After changing a secret value in the workspace Secrets Manager, the running
worker keeps the value it read at boot. Re-deploy the current revision (or
restart from the deployment Settings tab) so a fresh worker picks it up.
