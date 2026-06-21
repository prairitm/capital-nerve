"""API surface checks for the production-only v1 migration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    "path",
    [
        "/cards",
        "/cards/summary",
        "/cards/1",
        "/signals",
        "/signals/1",
        "/events/1",
        "/companies",
        "/companies/RELIANCE",
    ],
)
def test_legacy_routes_are_removed(client: TestClient, path: str) -> None:
    """Flat routers were deleted; only `/v1/*` serves intelligence data."""
    response = client.get(path)
    assert response.status_code == 404


def test_v1_health_and_summary_routes_exist(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    # Auth required — expect 401, not 404.
    assert client.get("/v1/intelligence-objects/summary").status_code == 401


def test_v1_metric_registry_routes_exist(client: TestClient) -> None:
    """The new metric-registry endpoints must be wired and auth-guarded."""
    assert client.get("/v1/metrics/registry").status_code == 401
    assert client.get("/v1/metrics/registry/pat_margin").status_code == 401


def test_v1_reproducibility_route_exists(client: TestClient) -> None:
    """Analyst-reproducibility export endpoint must be wired and auth-guarded."""
    assert (
        client.get("/v1/intelligence-objects/1/reproducibility").status_code == 401
    )


def test_production_rejects_weak_jwt() -> None:
    settings = Settings(
        APP_ENV="production",
        JWT_SECRET="dev-secret-change-me",
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="test-key",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.assert_production_ready()


def test_production_rejects_mock_llm() -> None:
    settings = Settings(
        APP_ENV="production",
        JWT_SECRET="a" * 40,
        LLM_PROVIDER="mock",
    )
    with pytest.raises(RuntimeError, match="LLM_PROVIDER=mock"):
        settings.assert_production_ready()
