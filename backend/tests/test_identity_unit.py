import time
import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.modules.identity.passwords import (
    MAX_LENGTH,
    MIN_LENGTH,
    PasswordService,
    normalize_password,
    validate_password,
)
from app.modules.identity.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_token,
    new_opaque_token,
)

CHEAP = {"memory_kib": 1024, "time_cost": 1, "parallelism": 1}


# ---------------- passwords ----------------


async def test_hash_is_argon2id_with_unique_salts() -> None:
    svc = PasswordService(**CHEAP)
    a, b = await svc.hash("correct horse battery"), await svc.hash("correct horse battery")
    assert a.startswith("$argon2id$")
    assert a != b
    assert await svc.verify(a, "correct horse battery")
    assert not await svc.verify(a, "correct horse batterY")


async def test_default_production_parameters_are_owasp_aligned() -> None:
    s = Settings()
    assert (s.argon2_memory_kib, s.argon2_time_cost, s.argon2_parallelism) == (65536, 3, 1)
    svc = PasswordService(
        memory_kib=s.argon2_memory_kib,
        time_cost=s.argon2_time_cost,
        parallelism=s.argon2_parallelism,
    )
    h = await svc.hash("a-long-enough-password")
    assert "m=65536,t=3,p=1" in h


async def test_verify_never_raises_on_garbage_hash() -> None:
    svc = PasswordService(**CHEAP)
    assert not await svc.verify("not-a-hash", "whatever-password")
    assert not await svc.verify("", "whatever-password")


async def test_needs_rehash_when_parameters_strengthen() -> None:
    weak = PasswordService(**CHEAP)
    strong = PasswordService(memory_kib=2048, time_cost=2, parallelism=1)
    h = await weak.hash("some-long-password")
    assert strong.needs_rehash(h)
    assert not weak.needs_rehash(h)


async def test_unicode_normalisation_makes_equivalent_inputs_match() -> None:
    svc = PasswordService(**CHEAP)
    composed = "café-password-1"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    h = await svc.hash(composed)
    assert await svc.verify(h, decomposed)
    # Arabic: presentation-form vs base letters normalise to the same secret
    assert normalize_password("ﻡﺳﺧﻮﻣ") == normalize_password("مسخوم")


def test_normalisation_does_not_fold_arabic_indic_digits_in_secrets() -> None:
    assert normalize_password("١٢٣٤٥٦٧٨٩٠") != "1234567890"


@pytest.mark.parametrize(
    ("password", "email", "reason"),
    [
        ("short", None, "TOO_SHORT"),
        ("x" * (MAX_LENGTH + 1), None, "TOO_LONG"),
        ("Password123", None, "TOO_COMMON"),
        ("aaaaaaaaaaaa", None, "TOO_COMMON"),
        ("ababababab", None, "TOO_COMMON"),
        ("layla.haddad-2026!", "layla.haddad@example.com", "CONTAINS_EMAIL"),
    ],
)
def test_policy_rejects(password: str, email: str | None, reason: str) -> None:
    result = validate_password(password, email=email)
    assert not result.ok
    assert reason in result.reasons


def test_policy_accepts_reasonable_passwords_including_arabic() -> None:
    assert validate_password("rivers-flow-quietly-9").ok
    assert validate_password("كلمة-مرور-طويلة-وآمنة").ok
    assert validate_password("x" * MAX_LENGTH, email=None).reasons == ("TOO_COMMON",)
    assert MIN_LENGTH == 10


async def test_dummy_verification_consumes_work() -> None:
    svc = PasswordService(memory_kib=16384, time_cost=2, parallelism=1)
    await svc.verify_dummy("warm up")  # builds the dummy hash
    started = time.perf_counter()
    await svc.verify_dummy("pw")
    assert time.perf_counter() - started > 0.002  # real argon2 work happened, not a no-op


# ---------------- tokens ----------------


def _settings() -> Settings:
    return Settings(app_env="test")


def test_access_token_roundtrip() -> None:
    s, uid, sid = _settings(), uuid4(), uuid4()
    token, _ = create_access_token(s, user_id=uid, session_id=sid)
    claims = decode_access_token(s, token)
    assert (claims.user_id, claims.session_id) == (uid, sid)


def test_expired_token_rejected() -> None:
    s = _settings()
    token, _ = create_access_token(
        s, user_id=uuid4(), session_id=uuid4(), now=datetime.now(UTC) - timedelta(hours=2)
    )
    with pytest.raises(TokenError):
        decode_access_token(s, token)


def test_tampered_signature_and_wrong_secret_rejected() -> None:
    s = _settings()
    token, _ = create_access_token(s, user_id=uuid4(), session_id=uuid4())
    head, payload, sig = token.split(".")
    with pytest.raises(TokenError):
        decode_access_token(s, f"{head}.{payload}.{sig[:-2]}AA")
    other = Settings(app_env="test", jwt_secret="y" * 40)  # type: ignore[arg-type]
    with pytest.raises(TokenError):
        decode_access_token(other, token)


def test_alg_none_and_algorithm_confusion_rejected() -> None:
    s = Settings(app_env="test", jwt_secret="k" * 64)  # type: ignore[arg-type]
    now = int(time.time())
    claims = {
        "iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(uuid4()), "sid": str(uuid4()),
        "jti": "x", "typ": "access", "iat": now, "exp": now + 600,
    }  # fmt: skip
    unsigned = jwt.encode(claims, key="", algorithm="none")
    with pytest.raises(TokenError):
        decode_access_token(s, unsigned)
    hs512 = jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm="HS512")
    with pytest.raises(TokenError):
        decode_access_token(s, hs512)


@pytest.mark.parametrize("missing", ["sid", "sub", "exp", "iat", "jti", "iss", "aud"])
def test_required_claims_enforced(missing: str) -> None:
    s = _settings()
    now = int(time.time())
    claims = {
        "iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(uuid4()), "sid": str(uuid4()),
        "jti": "x", "typ": "access", "iat": now, "exp": now + 600,
    }  # fmt: skip
    del claims[missing]
    token = jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(s, token)


def test_wrong_audience_issuer_and_type_rejected() -> None:
    s = _settings()
    now = int(time.time())
    base = {
        "iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(uuid4()), "sid": str(uuid4()),
        "jti": "x", "typ": "access", "iat": now, "exp": now + 600,
    }  # fmt: skip
    key = s.jwt_secret.get_secret_value()
    for patch in ({"aud": "other"}, {"iss": "other"}, {"typ": "refresh"}):
        with pytest.raises(TokenError):
            decode_access_token(s, jwt.encode({**base, **patch}, key, algorithm="HS256"))


def test_opaque_tokens_are_long_unique_and_hashed_one_way() -> None:
    a, b = new_opaque_token(), new_opaque_token()
    assert a != b
    assert len(a) >= 43  # 256 bits base64url
    assert hash_token(a) != a
    assert len(hash_token(a)) == 64
    assert hash_token(a) == hash_token(a)
