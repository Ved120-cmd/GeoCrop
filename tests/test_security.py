"""Security regression tests: SQL injection, CSRF, SSRF."""
import ast
import re
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from geocrop.common import safe_http
from geocrop.common.safe_http import BlockedRequest, check_url

ROOT = Path(__file__).resolve().parents[1]
GOOD = {"X-GeoCrop-Client": "web"}


@pytest.fixture(scope="module")
def client():
    from geocrop.api.main import app
    return TestClient(app)


def _db_up():
    try:
        from geocrop.db import engine
        with engine.connect():
            return True
    except Exception:
        return False


# ------------------------------------------------------------------ SQL injection
def test_no_raw_sql_in_api_code():
    """All DB access must go through the ORM (bound parameters). No text(), exec_driver_sql or SQL built from strings."""
    pat = re.compile(r"\btext\(|exec_driver_sql|\.execute\(\s*f?[\"'](SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)", re.I)
    files = list((ROOT / "geocrop/api").glob("*.py")) + [ROOT / "geocrop/db.py"]
    hits = [f"{f.name}:{i}" for f in files for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if pat.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("bad", ["1' OR '1'='1", "x'; DROP TABLE farmers;--", "00000000-0000-0000-0000-00000000000g", "%27%20OR%201%3D1"])
def test_injection_strings_in_ids_are_just_not_found(client, bad):
    for path in (f"/profiles/{bad}", f"/farms/{bad}/nowcast"):
        r = client.get(path)
        assert r.status_code == 404, (path, r.status_code)


@pytest.mark.skipif(not _db_up(), reason="PostgreSQL not running")
def test_api_runs_as_least_privilege_role():
    from sqlalchemy import text
    from geocrop.db import engine, uses_app_role
    if not uses_app_role():
        pytest.skip("app role not configured (run scripts/db/create_app_role.py)")
    with engine.connect() as c:
        su = c.execute(text("select rolsuper, rolcreaterole, rolcreatedb from pg_roles where rolname = current_user")).one()
        assert su == (False, False, False)
    for ddl in ("drop table farmers", "create table evil(x int)", "copy (select 1) to program 'whoami'"):
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text(ddl))


@pytest.mark.skipif(not _db_up(), reason="PostgreSQL not running")
def test_injection_text_is_stored_literally(client):
    payload = {"name": "Robert'); DROP TABLE farmers;--", "language": "en",
               "farm": {"district_id": 26, "area_unit": "acre", "irrigation_source": "rainfed", "soil_type_reported": "unknown", "crops": []}}
    r = client.post("/profiles", json=payload, headers=GOOD)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    try:
        assert client.get(f"/profiles/{pid}").json()["name"] == payload["name"]
    finally:
        assert client.delete(f"/profiles/{pid}", headers=GOOD).status_code == 204


# ------------------------------------------------------------------ CSRF
def test_unsafe_request_without_client_header_is_rejected(client):
    r = client.post("/simulator/run", json={})
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]


def test_cross_site_origin_is_rejected_even_with_header(client):
    r = client.post("/simulator/run", json={}, headers={**GOOD, "Origin": "https://evil.example"})
    assert r.status_code == 403 and "origin" in r.json()["detail"]
    r = client.delete("/profiles/00000000-0000-0000-0000-000000000000", headers={**GOOD, "Referer": "https://evil.example/page"})
    assert r.status_code == 403


def test_html_form_post_is_rejected(client):
    # what a hostile page can send without a preflight: form-encoded, no custom header
    r = client.post("/profiles", data={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_allowed_origin_with_header_passes_csrf(client):
    r = client.delete("/profiles/00000000-0000-0000-0000-000000000000", headers={**GOOD, "Origin": "http://localhost:5173"})
    assert r.status_code in (404, 503)   # reached the route (no such profile / DB down), not blocked


def test_safe_methods_need_no_header(client):
    assert client.get("/health").status_code == 200


def test_cors_preflight_only_for_our_origin(client):
    ok = client.options("/profiles", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "content-type,x-geocrop-client"})
    assert ok.status_code == 200 and ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/profiles", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                               "Access-Control-Request-Headers": "x-geocrop-client"})
    assert "access-control-allow-origin" not in bad.headers


def test_security_headers(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"


# ------------------------------------------------------------------ SSRF
@pytest.mark.parametrize("url", [
    "http://power.larc.nasa.gov/api",                 # not https
    "https://evil.example/x",                         # host not allowed
    "https://127.0.0.1/admin",                        # IP literal
    "https://169.254.169.254/latest/meta-data/",      # cloud metadata
    "https://[::1]/",                                 # IPv6 loopback
    "https://user:pw@power.larc.nasa.gov/",           # embedded credentials
    "https://power.larc.nasa.gov.evil.example/",      # suffix trick
    "file:///etc/passwd", "gopher://localhost:25/",
])
def test_blocked_urls(url):
    with pytest.raises(BlockedRequest):
        check_url(url)


def test_allowed_host_resolving_to_private_ip_is_blocked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))])
    with pytest.raises(BlockedRequest, match="non-public"):
        check_url("https://power.larc.nasa.gov/api/x")


def test_redirect_to_internal_host_is_blocked(monkeypatch):
    class R:
        status_code, is_redirect, headers = 302, True, {"Location": "https://localhost/admin"}
        def close(self): pass
    class S:
        def request(self, *a, **k): return R()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    with pytest.raises(BlockedRequest):
        safe_http.safe_get("https://power.larc.nasa.gov/x", session=S())


def test_all_outbound_http_goes_through_the_guard():
    """No direct requests.get/post/Session.get, urllib or httpx calls outside geocrop/common/safe_http.py."""
    pat = re.compile(r"\brequests\.(get|post|put|delete|head|request)\(|urlopen\(|urllib\.request|httpx\.|\bS\.(get|post|request)\(")
    offenders = []
    for d in ("geocrop", "scripts"):
        for f in (ROOT / d).rglob("*.py"):
            if f.name == "safe_http.py" or "__pycache__" in f.parts:
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pat.search(line.split("#")[0]):
                    offenders.append(f"{f.relative_to(ROOT)}:{i}")
    assert not offenders, offenders
