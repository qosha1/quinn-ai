"""
Unit tests for config loading.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from core.config import (
    load_providers_config,
    load_worker_templates_config,
    load_org_config,
    get_org_config_path,
    ProvidersConfig,
    WorkerTemplatesConfig,
    OrgConfig,
)


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestLoadProvidersConfig:
    """Test providers config loading."""

    def test_load_basic_config(self, temp_config_dir):
        """Should load basic providers config."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: test-key
    timeout: 30
""")
        config = load_providers_config(config_path)
        assert config.default == "anthropic"
        assert "anthropic" in config.providers
        assert config.providers["anthropic"].api_key == "test-key"
        assert config.providers["anthropic"].timeout == 30

    def test_load_thresholds(self, temp_config_dir):
        """Should load skill thresholds from config."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers: {}
thresholds:
  coding: 90
  reasoning: 70
  research: 85
""")
        config = load_providers_config(config_path)
        assert config.thresholds.coding == 90
        assert config.thresholds.reasoning == 70
        assert config.thresholds.research == 85

    def test_default_thresholds(self, temp_config_dir):
        """Should use default thresholds if not specified."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers: {}
""")
        config = load_providers_config(config_path)
        assert config.thresholds.coding == 80
        assert config.thresholds.reasoning == 60
        assert config.thresholds.research == 80

    def test_env_var_expansion(self, temp_config_dir, monkeypatch):
        """Should expand environment variables."""
        monkeypatch.setenv("TEST_API_KEY", "secret-key-123")
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: ${TEST_API_KEY}
""")
        config = load_providers_config(config_path)
        assert config.providers["anthropic"].api_key == "secret-key-123"

    def test_missing_env_var(self, temp_config_dir, monkeypatch):
        """Should handle missing env vars gracefully."""
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: ${NONEXISTENT_VAR}
""")
        config = load_providers_config(config_path)
        assert config.providers["anthropic"].api_key == ""

    def test_disabled_provider(self, temp_config_dir):
        """Should skip disabled providers."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: key1
  openai:
    enabled: false
    api_key: key2
""")
        config = load_providers_config(config_path)
        assert "anthropic" in config.providers
        assert config.providers["openai"].enabled is False

    def test_missing_config_raises(self, temp_config_dir):
        """Should raise FileNotFoundError for missing config."""
        with pytest.raises(FileNotFoundError):
            load_providers_config(temp_config_dir / "nonexistent.yaml")

    def test_empty_config_raises(self, temp_config_dir):
        """Should raise ValueError for empty config."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("")
        with pytest.raises(ValueError):
            load_providers_config(config_path)


class TestLoadWorkerTemplatesConfig:
    """Test worker templates config loading."""

    def test_load_templates(self, temp_config_dir):
        """Should load worker templates."""
        config_path = temp_config_dir / "worker-templates.yaml"
        config_path.write_text("""
templates:
  engineer:
    description: "Software engineer"
    skills:
      coding: 80
      reasoning: 70
    cost: 50
""")
        config = load_worker_templates_config(config_path)
        assert "engineer" in config.templates
        template = config.templates["engineer"]
        assert template.description == "Software engineer"
        assert template.skills["coding"] == 80
        assert template.cost == 50

    def test_multiple_templates(self, temp_config_dir):
        """Should load multiple templates."""
        config_path = temp_config_dir / "worker-templates.yaml"
        config_path.write_text("""
templates:
  senior:
    skills:
      coding: 90
    cost: 70
  junior:
    skills:
      coding: 60
    cost: 30
""")
        config = load_worker_templates_config(config_path)
        assert len(config.templates) == 2
        assert config.templates["senior"].cost == 70
        assert config.templates["junior"].cost == 30

    def test_missing_config_raises(self, temp_config_dir):
        """Should raise FileNotFoundError for missing config."""
        with pytest.raises(FileNotFoundError):
            load_worker_templates_config(temp_config_dir / "nonexistent.yaml")


class TestLoadOrgConfig:
    """Test complete org config loading."""

    def test_load_complete_config(self, temp_config_dir):
        """Should load all config files."""
        # Create providers.yaml
        providers_path = temp_config_dir / "providers.yaml"
        providers_path.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: test-key
""")
        # Create worker-templates.yaml
        templates_path = temp_config_dir / "worker-templates.yaml"
        templates_path.write_text("""
templates:
  engineer:
    cost: 50
""")
        config = load_org_config(temp_config_dir)
        assert isinstance(config, OrgConfig)
        assert config.providers.default == "anthropic"
        assert "engineer" in config.worker_templates.templates
        assert config.config_path == temp_config_dir

    def test_optional_templates(self, temp_config_dir):
        """Should handle missing templates file gracefully."""
        # Create only providers.yaml
        providers_path = temp_config_dir / "providers.yaml"
        providers_path.write_text("""
default: anthropic
providers: {}
""")
        config = load_org_config(temp_config_dir)
        assert len(config.worker_templates.templates) == 0

    def test_missing_directory_raises(self):
        """Should raise FileNotFoundError for missing directory."""
        with pytest.raises(FileNotFoundError):
            load_org_config(Path("/nonexistent/path"))

    def test_file_instead_of_directory_raises(self, temp_config_dir):
        """Should raise ValueError if path is file not directory."""
        file_path = temp_config_dir / "not_a_dir"
        file_path.write_text("content")
        with pytest.raises(ValueError):
            load_org_config(file_path)


class TestGetOrgConfigPath:
    """Test config path helper."""

    def test_returns_config_subdir(self):
        """Should return config subdirectory of org path."""
        org_path = Path("/some/org")
        config_path = get_org_config_path(org_path)
        assert config_path == Path("/some/org/config")
