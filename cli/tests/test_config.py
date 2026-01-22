"""
Unit tests for config loading.
"""

import os
import tempfile
import warnings
from pathlib import Path

import pytest
import yaml

from cli.core.config import (
    load_providers_config,
    load_worker_templates_config,
    load_org_config,
    get_org_config_path,
    ProvidersConfig,
    ProviderSettings,
    WorkerTemplatesConfig,
    OrgConfig,
    validate_api_key_format,
    validate_url,
    validate_provider_settings,
    validate_providers_config,
    validate_and_raise,
    is_plaintext_api_key,
    check_plaintext_api_keys,
    warn_plaintext_api_keys,
    mask_secret,
    mask_provider_settings,
    mask_providers_config,
    PlaintextApiKeyWarning,
)
from shared.exceptions import ConfigurationError


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


class TestValidateApiKeyFormat:
    """Test API key format validation."""

    def test_valid_anthropic_key(self):
        """Should accept valid Anthropic API key format."""
        assert validate_api_key_format("anthropic", "sk-ant-api03-abcdefghijklmnopqrstuvwxyz")

    def test_invalid_anthropic_key(self):
        """Should reject invalid Anthropic API key format."""
        assert not validate_api_key_format("anthropic", "invalid-key")
        assert not validate_api_key_format("anthropic", "sk-wrong-prefix")

    def test_valid_openai_key(self):
        """Should accept valid OpenAI API key format."""
        assert validate_api_key_format("openai", "sk-abcdefghijklmnopqrstuvwxyz1234")

    def test_invalid_openai_key(self):
        """Should reject invalid OpenAI API key format."""
        assert not validate_api_key_format("openai", "invalid-key")
        assert not validate_api_key_format("openai", "not-a-key")

    def test_unknown_provider_accepts_any(self):
        """Should accept any key for unknown providers."""
        assert validate_api_key_format("unknown-provider", "any-key-format")


class TestValidateUrl:
    """Test URL validation."""

    def test_valid_https_url(self):
        """Should accept valid HTTPS URLs."""
        assert validate_url("https://api.example.com")
        assert validate_url("https://api.example.com/v1/endpoint")

    def test_valid_http_url(self):
        """Should accept valid HTTP URLs."""
        assert validate_url("http://localhost:8080")

    def test_invalid_urls(self):
        """Should reject invalid URLs."""
        assert not validate_url("not-a-url")
        assert not validate_url("ftp://example.com")  # Wrong scheme
        assert not validate_url("")


class TestValidateProviderSettings:
    """Test provider settings validation."""

    def test_valid_settings(self):
        """Should pass for valid settings."""
        settings = ProviderSettings(
            enabled=True,
            api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            timeout=30,
            max_retries=3,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 0

    def test_missing_api_key(self):
        """Should fail for missing API key when required."""
        settings = ProviderSettings(
            enabled=True,
            api_key="",
            timeout=30,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 1
        assert "api_key" in errors[0].field

    def test_disabled_provider_skips_validation(self):
        """Should skip validation for disabled providers."""
        settings = ProviderSettings(
            enabled=False,
            api_key="",  # Would fail if enabled
            timeout=30,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 0

    def test_invalid_api_key_format(self):
        """Should fail for invalid API key format."""
        settings = ProviderSettings(
            enabled=True,
            api_key="invalid-format",
            timeout=30,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 1
        assert "format" in str(errors[0]).lower()

    def test_invalid_base_url(self):
        """Should fail for invalid base URL."""
        settings = ProviderSettings(
            enabled=True,
            api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            base_url="not-a-valid-url",
            timeout=30,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 1
        assert "url" in errors[0].field.lower()

    def test_negative_timeout(self):
        """Should fail for non-positive timeout."""
        settings = ProviderSettings(
            enabled=True,
            api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            timeout=0,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 1
        assert "timeout" in errors[0].field

    def test_negative_max_retries(self):
        """Should fail for negative max_retries."""
        settings = ProviderSettings(
            enabled=True,
            api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            timeout=30,
            max_retries=-1,
        )
        errors = validate_provider_settings("anthropic", settings)
        assert len(errors) == 1
        assert "max_retries" in errors[0].field


class TestValidateProvidersConfig:
    """Test complete providers config validation."""

    def test_valid_config(self):
        """Should pass for valid config."""
        config = ProvidersConfig(
            default="anthropic",
            providers={
                "anthropic": ProviderSettings(
                    enabled=True,
                    api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
                    timeout=30,
                ),
            },
        )
        errors = validate_providers_config(config)
        assert len(errors) == 0

    def test_no_providers(self):
        """Should fail when no providers configured."""
        config = ProvidersConfig(
            default="anthropic",
            providers={},
        )
        errors = validate_providers_config(config)
        assert len(errors) == 1
        assert "no providers" in str(errors[0]).lower()

    def test_default_not_in_providers(self):
        """Should fail when default provider not in list."""
        config = ProvidersConfig(
            default="nonexistent",
            providers={
                "anthropic": ProviderSettings(
                    enabled=True,
                    api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
                ),
            },
        )
        errors = validate_providers_config(config)
        assert any("default provider" in str(e).lower() for e in errors)

    def test_default_disabled(self):
        """Should fail when default provider is disabled."""
        config = ProvidersConfig(
            default="anthropic",
            providers={
                "anthropic": ProviderSettings(
                    enabled=False,
                    api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
                ),
            },
        )
        errors = validate_providers_config(config)
        assert any("disabled" in str(e).lower() for e in errors)

    def test_no_enabled_providers(self):
        """Should fail when no providers are enabled."""
        config = ProvidersConfig(
            default="anthropic",
            providers={
                "anthropic": ProviderSettings(enabled=False),
                "openai": ProviderSettings(enabled=False),
            },
        )
        errors = validate_providers_config(config, require_default_provider=False)
        assert any("no providers are enabled" in str(e).lower() for e in errors)


class TestValidateAndRaise:
    """Test validate_and_raise convenience function."""

    def test_raises_on_invalid(self):
        """Should raise ConfigurationError for invalid config."""
        config = ProvidersConfig(
            default="anthropic",
            providers={},
        )
        with pytest.raises(ConfigurationError):
            validate_and_raise(config)

    def test_passes_on_valid(self):
        """Should not raise for valid config."""
        config = ProvidersConfig(
            default="anthropic",
            providers={
                "anthropic": ProviderSettings(
                    enabled=True,
                    api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
                ),
            },
        )
        # Should not raise
        validate_and_raise(config)


class TestConfigurationErrorException:
    """Test ConfigurationError exception details."""

    def test_error_includes_provider(self):
        """Should include provider name in error message."""
        error = ConfigurationError("test message", provider="anthropic")
        assert "anthropic" in str(error)

    def test_error_includes_field(self):
        """Should include field name in error message."""
        error = ConfigurationError("test message", provider="anthropic", field="api_key")
        assert "api_key" in str(error)
        assert "anthropic" in str(error)

    def test_error_without_provider(self):
        """Should work without provider specified."""
        error = ConfigurationError("general error")
        assert "general error" in str(error)


class TestIsPlaintextApiKey:
    """Test plaintext API key detection."""

    def test_empty_string(self):
        """Should return False for empty string."""
        assert not is_plaintext_api_key("")

    def test_env_var_reference(self):
        """Should return False for environment variable reference."""
        assert not is_plaintext_api_key("${ANTHROPIC_API_KEY}")
        assert not is_plaintext_api_key("${OPENAI_API_KEY}")

    def test_plaintext_anthropic_key(self):
        """Should detect plaintext Anthropic API key."""
        assert is_plaintext_api_key("sk-ant-api03-abcdefghijklmnopqrstuvwxyz")

    def test_plaintext_openai_key(self):
        """Should detect plaintext OpenAI API key."""
        assert is_plaintext_api_key("sk-abcdefghijklmnopqrstuvwxyz1234")

    def test_generic_sk_key(self):
        """Should detect generic sk- prefixed keys."""
        assert is_plaintext_api_key("sk-some-other-provider-key-12345678901234567890")

    def test_non_key_string(self):
        """Should return False for non-key strings."""
        assert not is_plaintext_api_key("test-key")
        assert not is_plaintext_api_key("short")
        assert not is_plaintext_api_key("not-an-api-key-format")


class TestCheckPlaintextApiKeys:
    """Test config file plaintext key checking."""

    def test_no_plaintext_keys(self, temp_config_dir):
        """Should return empty list when using env vars."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  openai:
    api_key: ${OPENAI_API_KEY}
""")
        result = check_plaintext_api_keys(config_path)
        assert result == []

    def test_detects_plaintext_key(self, temp_config_dir):
        """Should detect plaintext API key."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
providers:
  anthropic:
    api_key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz
""")
        result = check_plaintext_api_keys(config_path)
        assert len(result) == 1
        assert result[0] == ("anthropic", "api_key")

    def test_detects_multiple_plaintext_keys(self, temp_config_dir):
        """Should detect multiple plaintext API keys."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
providers:
  anthropic:
    api_key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz
  openai:
    api_key: sk-abcdefghijklmnopqrstuvwxyz1234
""")
        result = check_plaintext_api_keys(config_path)
        assert len(result) == 2

    def test_missing_file(self, temp_config_dir):
        """Should return empty list for missing file."""
        result = check_plaintext_api_keys(temp_config_dir / "nonexistent.yaml")
        assert result == []

    def test_empty_file(self, temp_config_dir):
        """Should return empty list for empty file."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("")
        result = check_plaintext_api_keys(config_path)
        assert result == []


class TestWarnPlaintextApiKeys:
    """Test plaintext API key warnings."""

    def test_warns_on_plaintext_key(self, temp_config_dir):
        """Should issue warning for plaintext API key."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
providers:
  anthropic:
    api_key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz
""")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_plaintext_api_keys(config_path)
            assert len(w) == 1
            assert issubclass(w[0].category, PlaintextApiKeyWarning)
            assert "anthropic" in str(w[0].message)

    def test_no_warning_with_env_vars(self, temp_config_dir):
        """Should not warn when using env vars."""
        config_path = temp_config_dir / "providers.yaml"
        config_path.write_text("""
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
""")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_plaintext_api_keys(config_path)
            assert len(w) == 0


class TestMaskSecret:
    """Test secret masking."""

    def test_mask_normal_secret(self):
        """Should mask secret showing first few chars."""
        original = "sk-ant-api03-secret-key"
        result = mask_secret(original)
        assert result.startswith("sk-a")
        assert len(result) == len(original)
        assert "*" in result
        # First 4 chars visible, rest masked
        assert result == "sk-a" + "*" * (len(original) - 4)

    def test_mask_empty_string(self):
        """Should handle empty string."""
        assert mask_secret("") == ""

    def test_mask_short_string(self):
        """Should fully mask short strings."""
        assert mask_secret("abc") == "***"
        assert mask_secret("abcd") == "****"

    def test_mask_custom_visible_chars(self):
        """Should respect custom visible chars."""
        result = mask_secret("sk-ant-api03-secret-key", visible_chars=6)
        assert result == "sk-ant*****************"


class TestMaskProviderSettings:
    """Test provider settings masking."""

    def test_masks_api_key(self):
        """Should mask API key in settings."""
        settings = ProviderSettings(
            enabled=True,
            api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
            timeout=30,
            max_retries=3,
        )
        result = mask_provider_settings(settings)
        assert result["enabled"] is True
        assert result["api_key"].startswith("sk-a")
        assert "abcdefg" not in result["api_key"]
        assert result["timeout"] == 30
        assert result["max_retries"] == 3

    def test_handles_empty_api_key(self):
        """Should handle empty API key."""
        settings = ProviderSettings(
            enabled=True,
            api_key="",
            timeout=30,
        )
        result = mask_provider_settings(settings)
        assert result["api_key"] == ""


class TestMaskProvidersConfig:
    """Test full providers config masking."""

    def test_masks_all_providers(self):
        """Should mask all provider API keys."""
        config = ProvidersConfig(
            default="anthropic",
            providers={
                "anthropic": ProviderSettings(
                    enabled=True,
                    api_key="sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
                ),
                "openai": ProviderSettings(
                    enabled=False,
                    api_key="sk-openai-key-1234567890",
                ),
            },
        )
        result = mask_providers_config(config)
        assert result["default"] == "anthropic"
        assert "abcdefg" not in result["providers"]["anthropic"]["api_key"]
        assert "1234567890" not in result["providers"]["openai"]["api_key"]
        assert "thresholds" in result
