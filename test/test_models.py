"""Tests for mcp_generator.models — dataclass behaviour and helpers."""

from mcp_generator.models import ApiMetadata, ModuleSpec, OAuthConfig, SecurityConfig


class TestApiMetadata:
    def test_defaults(self) -> None:
        m = ApiMetadata()
        assert m.title == "Generated API"
        assert m.description == ""
        assert m.version == "0.0.1"
        assert m.backend_url == "http://localhost:3001"

    def test_backend_url_from_servers(self) -> None:
        m = ApiMetadata(servers=[{"url": "https://api.example.com"}])
        assert m.backend_url == "https://api.example.com"

    def test_backend_url_fallback_empty_servers(self) -> None:
        m = ApiMetadata(servers=[])
        assert m.backend_url == "http://localhost:3001"


class TestSecurityConfig:
    def test_has_authentication_false_when_empty(self) -> None:
        sc = SecurityConfig()
        assert sc.has_authentication() is False

    def test_has_authentication_true_with_schemes(self) -> None:
        sc = SecurityConfig(schemes={"bearer": {"type": "http"}})
        assert sc.has_authentication() is True

    def test_has_authentication_true_with_oauth_only(self) -> None:
        sc = SecurityConfig(oauth_config=OAuthConfig(scheme_name="oauth2"))
        assert sc.has_authentication() is True

    def test_jwks_uri_fallback(self) -> None:
        sc = SecurityConfig()
        assert sc.get_jwks_uri("http://localhost") == "http://localhost/.well-known/jwks.json"

    def test_jwks_uri_explicit(self) -> None:
        sc = SecurityConfig(jwks_uri="https://custom.com/jwks")
        assert sc.get_jwks_uri("http://localhost") == "https://custom.com/jwks"

    def test_issuer_fallback(self) -> None:
        sc = SecurityConfig()
        assert sc.get_issuer("http://localhost") == "http://localhost"

    def test_audience_fallback(self) -> None:
        sc = SecurityConfig()
        assert sc.get_audience() == "backend-api"


class TestModuleSpec:
    def test_resource_count_default(self) -> None:
        ms = ModuleSpec(
            filename="test.py",
            api_var_name="test_api",
            api_class_name="TestApi",
            module_name="test",
            tool_count=5,
            code="# code",
        )
        assert ms.resource_count == 0
