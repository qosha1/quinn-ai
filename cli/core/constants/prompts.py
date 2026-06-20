"""Prompt/template constants.

Agent-facing onboarding prompts live as FILES under cli/config/templates/, not
as magic strings in code, so they can be edited and reviewed like any other
content (quinn-ai-58rw). These constants name those files and the kinds the
loader (cli.core.prompts) understands.
"""

# Directory (relative to the cli package root) holding rendered templates.
TEMPLATES_DIR_NAME = "templates"

# Initial-task (kickstart) prompt kinds.
INITIAL_TASK_KIND_CEO = "ceo"
INITIAL_TASK_KIND_CEO_HOST = "ceo_host"
INITIAL_TASK_KIND_WORKER = "worker"

# Kind -> template filename under cli/config/templates/.
INITIAL_TASK_TEMPLATES = {
    INITIAL_TASK_KIND_CEO: "initial_task_ceo.md.jinja2",
    INITIAL_TASK_KIND_CEO_HOST: "initial_task_ceo_host.md.jinja2",
    INITIAL_TASK_KIND_WORKER: "initial_task_worker.md.jinja2",
}
