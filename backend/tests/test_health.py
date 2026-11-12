import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_reports_postgres() -> None:
    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["vendor"] == "postgresql"
    assert body["database"]["server_version"]


def test_api_requires_authentication_by_default() -> None:
    from django.conf import settings

    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]
