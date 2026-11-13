import pytest
from pydantic import SecretStr

from app.core.config import Settings


def test_defaults_are_dev() -> None:
    s = Settings()
    assert s.app_env in {"dev", "test"}
    assert s.log_json is True


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/1")
    s = Settings()
    assert s.app_env == "test"
    assert s.redis_url == "redis://r:6379/1"


def test_invalid_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging-ish")
    with pytest.raises(ValueError):
        Settings()


def test_production_refuses_insecure_defaults() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET must be set"):
        Settings(app_env="prod", cookie_secure=True, app_origin="https://example.test")
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(app_env="prod", jwt_secret=SecretStr("x" * 40), app_origin="https://example.test")
    with pytest.raises(ValueError, match="APP_ORIGIN must be https"):
        Settings(app_env="prod", jwt_secret=SecretStr("x" * 40), cookie_secure=True)


def test_production_accepts_secure_config() -> None:
    s = Settings(
        app_env="prod",
        jwt_secret=SecretStr("x" * 40),
        s3_secret_key=SecretStr("real-secret-value"),
        cookie_secure=True,
        app_origin="https://example.test",
    )
    assert s.cookie_secure


def test_short_jwt_secret_rejected_everywhere() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        Settings(jwt_secret=SecretStr("short"))


def test_production_refuses_the_default_object_store_secret() -> None:
    with pytest.raises(ValueError, match="S3_SECRET_KEY"):
        Settings(
            app_env="prod",
            jwt_secret=SecretStr("x" * 40),
            cookie_secure=True,
            app_origin="https://example.test",
        )
