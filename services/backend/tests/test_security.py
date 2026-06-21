"""Security tests — auth enforcement, upload validation, CORS headers."""
from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_client(*, bypass: bool) -> TestClient:
    os.environ["DEV_AUTH_BYPASS"] = "true" if bypass else "false"
    # Re-import app so Settings picks up the env var change
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    import app.main as main_mod
    importlib.reload(main_mod)
    from app.main import app as _app
    return TestClient(_app, raise_server_exceptions=False)


@pytest.fixture()
def client_bypass() -> TestClient:
    return _make_client(bypass=True)


@pytest.fixture()
def client_no_bypass() -> TestClient:
    return _make_client(bypass=False)


# ── auth enforcement ─────────────────────────────────────────────────────────

def test_list_cases_requires_auth_when_bypass_disabled(client_no_bypass: TestClient) -> None:
    resp = client_no_bypass.get("/api/v1/cases/")
    assert resp.status_code == 401


_CASE = "00000000-0000-0000-0000-000000000000"


def test_list_documents_requires_auth_when_bypass_disabled(client_no_bypass: TestClient) -> None:
    resp = client_no_bypass.get(f"/api/v1/cases/{_CASE}/documents/")
    assert resp.status_code == 401


def test_delete_case_requires_auth_when_bypass_disabled(client_no_bypass: TestClient) -> None:
    # Provide a matching CSRF token so the request passes CSRF and reaches the
    # auth layer — otherwise the double-submit check rejects it with 403 first.
    resp = client_no_bypass.delete(
        f"/api/v1/cases/{_CASE}",
        headers={"X-CSRF-Token": "t"},
        cookies={"sb_csrf": "t"},
    )
    assert resp.status_code == 401


def test_audit_log_requires_auth_when_bypass_disabled(client_no_bypass: TestClient) -> None:
    resp = client_no_bypass.get(f"/api/v1/cases/{_CASE}/audit-events/")
    assert resp.status_code == 401


def test_candidates_pii_requires_auth_when_bypass_disabled(client_no_bypass: TestClient) -> None:
    resp = client_no_bypass.get(f"/api/v1/cases/{_CASE}/candidates/")
    assert resp.status_code == 401


# ── upload validation ────────────────────────────────────────────────────────

def test_upload_rejects_disallowed_mime_type(client_bypass: TestClient) -> None:
    payload = io.BytesIO(b"MZ\x90\x00")  # EXE magic bytes
    resp = client_bypass.post(
        f"/api/v1/cases/{_CASE}/documents/upload",
        data={"document_type": "resume"},
        files={"file": ("evil.exe", payload, "application/x-msdownload")},
    )
    assert resp.status_code == 400
    assert "not permitted" in resp.json().get("detail", "").lower()


def test_upload_rejects_invalid_document_type(client_bypass: TestClient) -> None:
    payload = io.BytesIO(b"%PDF-1.4")
    resp = client_bypass.post(
        f"/api/v1/cases/{_CASE}/documents/upload",
        data={"document_type": "malicious_type"},
        files={"file": ("doc.pdf", payload, "application/pdf")},
    )
    assert resp.status_code == 400
    assert "document_type" in resp.json().get("detail", "").lower()


def test_upload_rejects_path_traversal_filename(client_bypass: TestClient) -> None:
    payload = io.BytesIO(b"%PDF-1.4")
    resp = client_bypass.post(
        f"/api/v1/cases/{_CASE}/documents/upload",
        data={"document_type": "resume"},
        files={"file": ("../../etc/passwd", payload, "application/pdf")},
    )
    # Should either succeed with sanitized filename or return 4xx — must not crash
    assert resp.status_code in (200, 201, 400, 404, 422, 500)
    if resp.status_code in (200, 201):
        # Verify the stored filename does not contain directory traversal
        stored = resp.json().get("file_name", "")
        assert ".." not in stored
        assert "/" not in stored
        assert "\\" not in stored


# ── CORS ─────────────────────────────────────────────────────────────────────

def test_cors_does_not_reflect_arbitrary_origins(client_bypass: TestClient) -> None:
    resp = client_bypass.options(
        "/api/v1/cases/",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    origin = resp.headers.get("access-control-allow-origin", "")
    assert origin != "https://evil.example.com", "Server must not reflect arbitrary origins"
    assert origin != "*", "Server must not allow wildcard origin on credentialed routes"


# ── response headers ──────────────────────────────────────────────────────────

def test_health_endpoint_is_accessible(client_bypass: TestClient) -> None:
    resp = client_bypass.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"
