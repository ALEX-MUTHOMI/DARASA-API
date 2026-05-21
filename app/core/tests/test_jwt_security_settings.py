from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured

from darasa_project import settings


@pytest.mark.security
def test_jwt_algorithm_is_explicit_and_none_is_rejected():
    assert settings.SIMPLE_JWT["ALGORITHM"] == "HS256"
    assert settings.SIMPLE_JWT["ALGORITHM"].lower() != "none"

    with pytest.raises(ImproperlyConfigured):
        settings._get_jwt_signing_key(
            configured_key="x" * settings.JWT_MIN_HS_SECRET_LENGTH,
            secret_key="unused",
            testing=False,
            algorithm="none",
        )


@pytest.mark.security
def test_unexpected_jwt_algorithm_is_rejected():
    with pytest.raises(ImproperlyConfigured):
        settings._get_jwt_signing_key(
            configured_key="x" * settings.JWT_MIN_HS_SECRET_LENGTH,
            secret_key="unused",
            testing=False,
            algorithm="HS384",
        )


@pytest.mark.security
def test_weak_jwt_signing_key_is_rejected_outside_tests():
    with pytest.raises(ImproperlyConfigured):
        settings._get_jwt_signing_key(
            configured_key="short",
            secret_key="unused",
            testing=False,
            algorithm="HS256",
        )

    with pytest.raises(ImproperlyConfigured):
        settings._get_jwt_signing_key(
            configured_key="ci-secret-key-not-for-runtime-use",
            secret_key="unused",
            testing=False,
            algorithm="HS256",
        )


@pytest.mark.security
def test_strong_jwt_signing_key_is_required_and_accepted():
    signing_key = "runtime-jwt-signing-key-at-least-32-bytes"

    assert (
        settings._get_jwt_signing_key(
            configured_key=signing_key,
            secret_key="unused",
            testing=False,
            algorithm="HS256",
        )
        == signing_key
    )


@pytest.mark.security
def test_jwt_lifetimes_and_rotation_are_sane():
    assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=15)
    assert settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] <= timedelta(days=7)
    assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
    assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True


@pytest.mark.security
def test_jwt_claim_configuration_excludes_raw_pii_and_roles():
    assert settings.SIMPLE_JWT["USER_ID_CLAIM"] == "user_id"
    configured_claim_names = {settings.SIMPLE_JWT["USER_ID_CLAIM"]}

    assert "email" not in configured_claim_names
    assert "learner_name" not in configured_claim_names
    assert "guardian_phone" not in configured_claim_names
    assert "role" not in configured_claim_names
