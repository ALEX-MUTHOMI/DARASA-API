"""
tests/conftest.py — Shared fixtures for the DARASA-API top-level test suite.
"""

import io
import os
import uuid
import logging
import tempfile
from pathlib import Path

import factory
import pytest
from factory.django import DjangoModelFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
FIXTURES_DIR = Path(
    os.environ.get(
        "PHOTOBOX_TEST_FIXTURES_DIR",
        str(Path(tempfile.gettempdir()) / "photobox_fixtures"),
    )
)
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODEL FACTORIES — Database Fixtures
# ─────────────────────────────────────────────────────────────────────────────

class UserFactory(DjangoModelFactory):
    class Meta:
        model = "core.User"

    email = factory.Sequence(lambda n: f"factory_user_{n}@test.test")
    name = factory.Sequence(lambda n: f"Factory User {n}")
    accepted_terms = True
    password = factory.PostGenerationMethodCall("set_password", "StrongTestPass!99")


class WorkspaceFactory(DjangoModelFactory):
    class Meta:
        model = "core.Workspace"
        django_get_or_create = ("user",)

    class Params:
        owner = None

    user = factory.LazyAttribute(lambda obj: obj.owner or UserFactory())
    business_name = factory.Sequence(lambda n: f"Factory Workspace {n}")


# ─────────────────────────────────────────────────────────────────────────────
# PYTEST FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def photographer_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email=f"test_{uuid.uuid4().hex[:6]}@test.test",
        password="StrongTestPass!99",
    )


@pytest.fixture
def second_photographer_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email=f"other_{uuid.uuid4().hex[:6]}@test.test",
        password="AnotherStrongPass!77",
    )


@pytest.fixture
def authenticated_client(api_client, photographer_user) -> APIClient:
    refresh = RefreshToken.for_user(photographer_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


@pytest.fixture
def second_authenticated_client(second_photographer_user) -> APIClient:
    client = APIClient()
    refresh = RefreshToken.for_user(second_photographer_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


# ─────────────────────────────────────────────────────────────────────────────
# CELERY FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def celery_config():
    return {
        "task_always_eager": True,
        "task_eager_propagates": True,
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
    }


@pytest.fixture
def live_celery_config():
    return {
        "broker_url": os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0"),
        "result_backend": os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
        "task_always_eager": False,
    }
