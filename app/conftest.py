import os

import django
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "darasa_project.settings")
django.setup()


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = str(item.fspath).replace("\\", "/").lower()
        name = item.name.lower()

        if "/curriculum/" in path:
            item.add_marker(pytest.mark.curriculum)
        if "/grading/" in path:
            item.add_marker(pytest.mark.grading)
        if "/events/" in path:
            item.add_marker(pytest.mark.events)
        if "/core/" in path:
            item.add_marker(pytest.mark.core)
        if "/tenant/" in path:
            item.add_marker(pytest.mark.tenant)

        if "redteam" in path or "adversarial" in path:
            item.add_marker(pytest.mark.redteam)
            item.add_marker(pytest.mark.security)
        if "security" in path or "security" in name:
            item.add_marker(pytest.mark.security)
        if "performance" in path or "performance" in name:
            item.add_marker(pytest.mark.performance)
        if "boundary" in path or "phase_boundaries" in path:
            item.add_marker(pytest.mark.boundary)
        if (
            path.endswith("test_cct_fortification_control_plane.py")
            or path.endswith("test_phase6a_cbe_cct_binding.py")
        ):
            item.add_marker(pytest.mark.turbo)


@pytest.fixture(autouse=True)
def clear_shared_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user_factory(db):
    user_model = get_user_model()

    def create_user(**overrides):
        defaults = {
            "email": "admin@darasa.test",
            "password": "StrongPassword123!",
            "first_name": "Darasa",
            "last_name": "Admin",
        }
        defaults.update(overrides)
        password = defaults.pop("password")
        return user_model.objects.create_user(password=password, **defaults)

    return create_user
