"""Per-layer credential scoping (quinn-ai-a3pg.1.5).

Default-deny: a worker only gets the credential env vars its team is scoped
for. Scopes are env var NAMES; values come from the orchestrator environment.
"""

from cli.core.secrets_scope import (
    collect_credentials,
    load_secrets_policy,
    resolve_scope,
    scoped_env_for_team,
)

POLICY = {
    "*": ["ANTHROPIC_API_KEY"],
    "raise": ["SIMPLI_API_TOKEN", "VERCEL_TOKEN"],
    "core-infra": ["DJANGO_SECRET_KEY"],
}


def test_resolve_scope_includes_wildcard_and_team():
    assert resolve_scope("raise", POLICY) == [
        "ANTHROPIC_API_KEY",
        "SIMPLI_API_TOKEN",
        "VERCEL_TOKEN",
    ]


def test_resolve_scope_team_without_entry_gets_wildcard_only():
    assert resolve_scope("market", POLICY) == ["ANTHROPIC_API_KEY"]


def test_resolve_scope_none_team():
    assert resolve_scope(None, POLICY) == ["ANTHROPIC_API_KEY"]


def test_collect_credentials_reads_only_set_vars():
    environ = {"SIMPLI_API_TOKEN": "tok", "VERCEL_TOKEN": ""}
    got = collect_credentials(["SIMPLI_API_TOKEN", "VERCEL_TOKEN", "MISSING"], environ)
    assert got == {"SIMPLI_API_TOKEN": "tok"}  # empty + missing excluded


def test_core_infra_does_not_get_app_tokens():
    environ = {"SIMPLI_API_TOKEN": "tok", "DJANGO_SECRET_KEY": "djk"}
    names = resolve_scope("core-infra", POLICY)
    got = collect_credentials(names, environ)
    assert "SIMPLI_API_TOKEN" not in got
    assert got["DJANGO_SECRET_KEY"] == "djk"


def test_load_policy_absent_is_empty(tmp_path):
    assert load_secrets_policy(tmp_path) == {}


def test_scoped_env_for_team_end_to_end(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "secrets-scope.yaml").write_text(
        "'*': [ANTHROPIC_API_KEY]\nraise: [SIMPLI_API_TOKEN]\n"
    )
    environ = {"ANTHROPIC_API_KEY": "ak", "SIMPLI_API_TOKEN": "st", "OTHER": "x"}
    got = scoped_env_for_team(tmp_path, "raise", environ=environ)
    assert got == {"ANTHROPIC_API_KEY": "ak", "SIMPLI_API_TOKEN": "st"}
    # a different team only gets the wildcard credential
    assert scoped_env_for_team(tmp_path, "market", environ=environ) == {
        "ANTHROPIC_API_KEY": "ak"
    }


def test_no_policy_returns_empty(tmp_path):
    # no secrets-scope.yaml -> default behavior: no extra credentials
    assert scoped_env_for_team(tmp_path, "raise", environ={"SIMPLI_API_TOKEN": "x"}) == {}
