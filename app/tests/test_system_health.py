import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db

class TestSystemHealth:
    def test_user_authentication_flow(self, api_client):
        """Verify the authentication system is healthy."""
        user = User.objects.create_user(
            email="healthcheck@example.com",
            password="StrongPassword123!",
            name="Health Check",
            accepted_terms=True,
        )
        url = reverse("user:token")
        response = api_client.post(url, {"email": user.email, "password": "StrongPassword123!"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_authenticated_user_can_access_profile(self, authenticated_client):
        """Verify an authenticated user can read their own profile."""
        url = reverse("user:me")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "email" in response.data
