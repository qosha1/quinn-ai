"""Constants for the declarative org.yml spec (quinn-ai-a3pg.4.2).

All magic strings used by the org-spec loader live here, per the
'No Magic Values' principle (see constants/__init__.py).
"""

# Schema versioning — the only apiVersion the v1 loader accepts.
ORG_SPEC_API_VERSION = "quinnai/v1"

# The pointer key used inside org.yml to reference an external config file
# (e.g. `providers: { $ref: config/providers.yaml }`).
ORG_SPEC_REF_KEY = "$ref"

# Built-in team-template names the hybrid topology relies on.
TEMPLATE_CORE_INFRA = "core-infra"
TEMPLATE_APP_GROUP = "app-group"

# Worker handles in org.yml are written as "<team>/<Name>" (e.g. core-infra/Dana).
WORKER_HANDLE_SEP = "/"

# Top-level keys recognised in org.yml.
ORG_SPEC_KEY_API_VERSION = "apiVersion"
ORG_SPEC_KEY_METADATA = "metadata"
ORG_SPEC_KEY_HOST = "host"
ORG_SPEC_KEY_TOOLCHAIN = "toolchain"
ORG_SPEC_KEY_PROVIDERS = "providers"
ORG_SPEC_KEY_ROLES = "roles"
ORG_SPEC_KEY_TEAM_TEMPLATES = "teamTemplates"
ORG_SPEC_KEY_CEO = "ceo"
ORG_SPEC_KEY_STRUCTURE = "structure"
ORG_SPEC_KEY_DELEGATIONS = "delegations"
ORG_SPEC_KEY_OKRS = "okrs"

# Default CEO role when org.yml omits ceo.role.
ORG_SPEC_DEFAULT_CEO_ROLE = "CEO"
