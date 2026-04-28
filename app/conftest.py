import io
import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
django.setup()


@pytest.fixture(autouse=True)
def clear_shared_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    user_model = get_user_model()

    def create_user(**overrides):
        defaults = {
            "email": "photographer@example.com",
            "password": "StrongPassword123!",
            "name": "PhotoBox User",
            "accepted_terms": True,
        }
        defaults.update(overrides)
        password = defaults.pop("password")
        return user_model.objects.create_user(password=password, **defaults)

    return create_user



