"""Constants for the sanctioned worker git/PR flow (quinn-ai-a3pg.1.3)."""

# Branch namespace for worker-created branches: quinnai/<bead-id>[-<slug>].
GIT_BRANCH_PREFIX = "quinnai"

# Default remote NAME workers push to. Must be a configured remote name — never
# an arbitrary URL/path (enforced in git_pr._validate_remote, the trust boundary).
GIT_DEFAULT_REMOTE = "origin"

# Default PR base branch.
GIT_DEFAULT_BASE = "main"

# Max length of the title slug appended to a branch name.
GIT_BRANCH_SLUG_MAX_LEN = 40
