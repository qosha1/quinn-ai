"""Host-mode per-app .beads routing in a monorepo (quinn-ai-a3pg.1.1).

In a pnpm-workspace + git-submodule monorepo, each app (apps/<name>) carries
its own .beads tracker alongside the meta-repo .beads. A worker operating in
apps/raise/ should hit apps/raise/.beads; one at the repo root hits the meta
.beads. resolve_beads_dir walks up from cwd to the nearest .beads, bounded by
the project root — naturally handling submodules and apps without their own
tracker (fall back to the meta .beads).
"""

import cli.core.host_mode as host_mode
from cli.core.bd_wrapper import (
    find_nearest_beads_dir,
    get_org_beads_dir,
    resolve_beads_dir,
)


def _monorepo(tmp_path):
    (tmp_path / ".beads").mkdir(parents=True)  # meta-repo tracker
    (tmp_path / "apps" / "raise" / ".beads").mkdir(parents=True)
    (tmp_path / "apps" / "raise" / "src").mkdir(parents=True)
    (tmp_path / "apps" / "market").mkdir(parents=True)  # no own .beads
    return tmp_path


def test_nearest_from_app_dir(tmp_path):
    root = _monorepo(tmp_path)
    assert find_nearest_beads_dir(root / "apps" / "raise", stop=root) == (
        root / "apps" / "raise" / ".beads"
    )


def test_nearest_from_app_subdir(tmp_path):
    root = _monorepo(tmp_path)
    assert find_nearest_beads_dir(root / "apps" / "raise" / "src", stop=root) == (
        root / "apps" / "raise" / ".beads"
    )


def test_nearest_falls_back_to_meta(tmp_path):
    root = _monorepo(tmp_path)
    # apps/market has no own tracker -> nearest is the meta-repo .beads
    assert find_nearest_beads_dir(root / "apps" / "market", stop=root) == (
        root / ".beads"
    )


def test_nearest_from_root(tmp_path):
    root = _monorepo(tmp_path)
    assert find_nearest_beads_dir(root, stop=root) == root / ".beads"


def test_resolve_host_mode_routes_to_app(tmp_path, monkeypatch):
    root = _monorepo(tmp_path)
    monkeypatch.setattr(host_mode, "is_host_mode", lambda p: True)
    monkeypatch.setattr(host_mode, "get_project_root", lambda p: root)
    meta = root / ".quinnai"  # org metadata root in host mode
    got = resolve_beads_dir(meta, cwd=root / "apps" / "raise" / "src")
    assert got == root / "apps" / "raise" / ".beads"


def test_resolve_host_mode_root_uses_meta(tmp_path, monkeypatch):
    root = _monorepo(tmp_path)
    monkeypatch.setattr(host_mode, "is_host_mode", lambda p: True)
    monkeypatch.setattr(host_mode, "get_project_root", lambda p: root)
    got = resolve_beads_dir(root / ".quinnai", cwd=root)
    assert got == root / ".beads"


def test_resolve_non_host_uses_org_beads(tmp_path, monkeypatch):
    monkeypatch.setattr(host_mode, "is_host_mode", lambda p: False)
    (tmp_path / ".beads").mkdir()
    assert resolve_beads_dir(tmp_path, cwd=tmp_path) == get_org_beads_dir(tmp_path)
