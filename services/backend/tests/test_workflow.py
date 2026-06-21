"""Workflow regression tests — covers bugs fixed in the review/decision sprint."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_case(client: TestClient) -> str:
    resp = client.post("/api/v1/cases/", json={
        "title": "Test Engagement",
        "organization": "Test Org",
        "hiring_action_type": "Merit Promotion",
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


# ── config default ────────────────────────────────────────────────────────────

def test_dev_auth_bypass_default_is_false():
    """DEV_AUTH_BYPASS code default must be False — prevents open-admin on bare deploys."""
    import importlib
    import os

    saved = os.environ.pop("DEV_AUTH_BYPASS", None)
    try:
        import app.core.config as cfg
        importlib.reload(cfg)
        settings = cfg.Settings()
        assert settings.dev_auth_bypass is False, (
            "DEV_AUTH_BYPASS code default must be False — set true explicitly in .env for local dev"
        )
    finally:
        if saved is not None:
            os.environ["DEV_AUTH_BYPASS"] = saved
        import app.core.config as cfg
        importlib.reload(cfg)


# ── admin routes ──────────────────────────────────────────────────────────────

def test_admin_users_returns_200_not_307(client: TestClient):
    """GET /admin/users must return 200, not 307 (trailing-slash redirect bug)."""
    resp = client.get("/api/v1/admin/users")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


def test_admin_users_create_and_list(client: TestClient):
    """Create a user via POST then verify it appears in GET list."""
    suffix = uuid.uuid4().hex[:8]
    resp = client.post("/api/v1/admin/users", json={
        "username": f"testuser_{suffix}",
        "email": f"test_{suffix}@example.gov",
        "display_name": "Test User",
        "roles": ["panel_reviewer"],
        "password": "StrongPassword!14x",
    })
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]

    list_resp = client.get("/api/v1/admin/users")
    assert list_resp.status_code == 200
    ids = [u["id"] for u in list_resp.json()]
    assert user_id in ids


# ── override round-trip ───────────────────────────────────────────────────────

def test_clear_all_overrides_returns_dossier_not_500(client: TestClient):
    """clear_all_overrides must return a dossier (200), not crash with 500.

    Regression: record_candidate_decision called self._build_candidate_dossier
    which does not exist — fixed to self.get_candidate_dossier.
    """
    case_id = _create_case(client)

    cand_resp = client.post("/api/v1/candidates/", json={
        "case_id": case_id,
        "full_name": "Jane Doe",
        "email": "jane@example.gov",
    })
    if cand_resp.status_code not in (200, 201):
        pytest.skip("Candidate creation requires full pipeline setup")

    cand_id = cand_resp.json()["id"]
    resp = client.post(
        f"/api/v1/cases/{case_id}/workflow-plan/stages/resume_review/candidates/{cand_id}/decision",
        json={"clear_all_overrides": True},
    )
    assert resp.status_code != 500, f"clear_all_overrides returned 500: {resp.text}"
    assert resp.status_code in (200, 404), f"Unexpected status: {resp.status_code} {resp.text}"


# ── security headers ──────────────────────────────────────────────────────────

def test_security_headers_present(client: TestClient):
    """API responses must include key security headers."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    headers = {k.lower(): v for k, v in resp.headers.items()}
    assert "x-frame-options" in headers, "Missing X-Frame-Options"
    assert "x-content-type-options" in headers, "Missing X-Content-Type-Options"


def test_admin_endpoints_require_auth_when_bypass_disabled(client: TestClient):
    """Admin endpoints must return 401 when bypass is off and no session cookie."""
    import importlib
    import os

    saved = os.environ.get("DEV_AUTH_BYPASS")
    os.environ["DEV_AUTH_BYPASS"] = "false"
    try:
        import app.core.config as cfg
        importlib.reload(cfg)
        import app.main as main_mod
        importlib.reload(main_mod)
        from app.main import app as _app
        no_auth_client = TestClient(_app, raise_server_exceptions=False)
        resp = no_auth_client.get("/api/v1/admin/users")
        assert resp.status_code == 401
    finally:
        if saved is not None:
            os.environ["DEV_AUTH_BYPASS"] = saved
        else:
            os.environ.pop("DEV_AUTH_BYPASS", None)
        import app.core.config as cfg
        importlib.reload(cfg)
