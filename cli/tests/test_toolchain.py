"""Toolchain contract + preflight (quinn-ai-a3pg.1.2).

check_toolchain is pure (PATH lookup injected) so it tests without touching
the real environment. load_toolchain reads the persisted contract.
"""

from cli.core.toolchain import ToolchainReport, check_toolchain


def test_all_present_is_ok():
    report = check_toolchain(["node", "pnpm"], ["docker"], which=lambda t: f"/usr/bin/{t}")
    assert isinstance(report, ToolchainReport)
    assert report.ok
    assert report.missing_required == []
    assert report.missing_optional == []


def test_missing_required_not_ok():
    present = {"node"}
    report = check_toolchain(
        ["node", "pnpm"],
        ["docker"],
        which=lambda t: t if t in present else None,
    )
    assert not report.ok
    assert report.missing_required == ["pnpm"]
    assert report.missing_optional == ["docker"]


def test_optional_missing_still_ok():
    report = check_toolchain(
        ["git"],
        ["vercel"],
        which=lambda t: f"/bin/{t}" if t == "git" else None,
    )
    assert report.ok
    assert report.missing_optional == ["vercel"]


def test_empty_contract_is_ok():
    report = check_toolchain([], [], which=lambda t: None)
    assert report.ok


def test_load_toolchain_reads_persisted_contract(tmp_path):
    from cli.core.toolchain import load_toolchain

    config = tmp_path / "config"
    config.mkdir()
    (config / "toolchain.yaml").write_text(
        "require: [node, pnpm]\noptional: [docker]\n"
    )
    require, optional = load_toolchain(tmp_path)
    assert require == ["node", "pnpm"]
    assert optional == ["docker"]


def test_load_toolchain_absent_returns_empty(tmp_path):
    from cli.core.toolchain import load_toolchain

    assert load_toolchain(tmp_path) == ([], [])


def test_preflight_fails_fast_on_missing_required(tmp_path):
    import click
    import pytest

    from cli.core.org_start_controller import _verify_required_toolchain

    config = tmp_path / "config"
    config.mkdir()
    # A binary that cannot exist on PATH.
    (config / "toolchain.yaml").write_text(
        "require: [definitely-not-a-real-binary-xyz]\noptional: []\n"
    )
    with pytest.raises(click.ClickException) as exc:
        _verify_required_toolchain(tmp_path)
    assert "definitely-not-a-real-binary-xyz" in str(exc.value)


def test_preflight_passes_when_required_present(tmp_path):
    from cli.core.org_start_controller import _verify_required_toolchain

    config = tmp_path / "config"
    config.mkdir()
    # 'git' is present in the dev/CI environment; should not raise.
    (config / "toolchain.yaml").write_text("require: [git]\noptional: []\n")
    _verify_required_toolchain(tmp_path)  # no exception
