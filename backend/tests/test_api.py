import uuid

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from app.crawler.crawl import CrawledPage, CrawlResult


def signed_in_client(name: str = "Asha Menon") -> TestClient:
    client = TestClient(main.app)
    email = f"{uuid.uuid4().hex[:8]}@agency.in"
    resp = client.post("/auth/register", json={"name": name, "email": email, "password": "correct horse battery"})
    assert resp.status_code == 201, resp.text
    return client


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    fake = CrawlResult(
        site_files={"/llms.txt": {"url": "https://example.com/llms.txt", "found": False, "status": 404}},
        pages=[CrawledPage(url="https://example.com/", status_code=200, metrics={"title": "Example"})],
    )
    monkeypatch.setattr("app.pipeline.crawl", lambda url, out_dir: fake)
    monkeypatch.setattr("app.config.settings.pagespeed_enabled", False)
    monkeypatch.setattr("app.config.settings.llm_api_key", None)


def test_create_and_fetch_audit():
    with signed_in_client() as client:
        resp = client.post("/audits", json={"url": "https://example.com", "tasks": ["find opening hours"]})
        assert resp.status_code == 202
        audit_id = resp.json()["id"]

        # TestClient runs background tasks before returning, so the audit is already finished.
        audit = client.get(f"/audits/{audit_id}").json()
        assert audit["status"] == "done", audit
        assert audit["page_count"] == 1
        assert client.get(f"/audits/{audit_id}/pages").json()[0]["metrics"]["title"] == "Example"
        assert client.get(f"/audits/{audit_id}/site-files").json()["/llms.txt"]["found"] is False
        assert client.get("/audits/nope").status_code == 404

        scores = {s["category"]: s for s in client.get(f"/audits/{audit_id}/scores").json()}
        assert {"seo", "readability", "actionability", "agent_ready"} <= set(scores)
        assert scores["agent_ready"]["details"]["missing"] == ["task_success", "visibility"]
        assert isinstance(client.get(f"/audits/{audit_id}/findings").json(), list)


def test_audits_are_private_to_their_owner():
    with signed_in_client("Owner") as owner, signed_in_client("Other") as other:
        audit_id = owner.post("/audits", json={"url": "https://example.com"}).json()["id"]
        assert other.get(f"/audits/{audit_id}").status_code == 404
        assert other.get(f"/audits/{audit_id}/fixes").status_code == 404
        assert other.get("/audits").json() == []
        assert [a["id"] for a in owner.get("/audits").json()] == [audit_id]


def test_auth_flow():
    client = TestClient(main.app)
    assert client.get("/audits").status_code == 401
    assert client.get("/auth/me").status_code == 401

    email = f"{uuid.uuid4().hex[:8]}@agency.in"
    assert client.post("/auth/register", json={"name": "A", "email": email, "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={"name": "Asha", "email": email, "password": "correct horse battery"}).status_code == 201
    assert client.get("/auth/me").json()["email"] == email
    assert client.post("/auth/register", json={"name": "Asha", "email": email.upper(), "password": "correct horse battery"}).status_code == 409

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401

    assert client.post("/auth/login", json={"email": email, "password": "wrong password!"}).status_code == 401
    resp = client.post("/auth/login", json={"email": email.upper(), "password": "correct horse battery"})
    assert resp.status_code == 200 and resp.json()["name"] == "Asha"
    assert auth.COOKIE in resp.cookies or client.cookies.get(auth.COOKIE)
    assert client.get("/audits").status_code == 200


def test_login_lockout_after_repeated_failures():
    client = TestClient(main.app)
    email = f"{uuid.uuid4().hex[:8]}@agency.in"
    client.post("/auth/register", json={"name": "Asha", "email": email, "password": "correct horse battery"})
    for _ in range(5):
        assert client.post("/auth/login", json={"email": email, "password": "nope nope nope"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": "correct horse battery"}).status_code == 429


def test_password_hashing():
    stored = auth.hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert auth.verify_password("correct horse battery", stored)
    assert not auth.verify_password("correct horse batterz", stored)
    assert not auth.verify_password("x", "garbage")


def test_projects_scope_audits():
    with signed_in_client() as client:
        starter = client.get("/projects").json()
        assert [p["name"] for p in starter] == ["My websites"]

        assert client.post("/projects", json={"name": "  ", "color": "teal"}).status_code == 422
        assert client.post("/projects", json={"name": "Rosa", "color": "purple"}).status_code == 422
        rosa = client.post("/projects", json={"name": "Rosa Trattoria", "description": "Client", "color": "rose"}).json()
        assert rosa["color"] == "rose" and rosa["audit_count"] == 0

        in_rosa = client.post("/audits", json={"url": "https://example.com", "project_id": rosa["id"]}).json()
        default = client.post("/audits", json={"url": "https://example.org"}).json()
        assert in_rosa["project_name"] == "Rosa Trattoria"
        assert default["project_id"] == starter[0]["id"]

        listed = client.get(f"/audits?project_id={rosa['id']}").json()
        assert [a["id"] for a in listed] == [in_rosa["id"]]
        detail = client.get(f"/projects/{rosa['id']}").json()
        assert detail["audit_count"] == 1 and detail["sites"][0]["url"] == "https://example.com/"
        assert detail["sites"][0]["status"] == "done"

        renamed = client.patch(f"/projects/{rosa['id']}", json={"name": " Rosa ", "color": "green"}).json()
        assert renamed["name"] == "Rosa" and renamed["color"] == "green"
        assert client.delete(f"/projects/{rosa['id']}").status_code == 409
        empty = client.post("/projects", json={"name": "Empty"}).json()
        assert client.delete(f"/projects/{empty['id']}").status_code == 204

    with signed_in_client("Other") as other:
        # an audit from before projects existed is adopted by the first project when projects are listed
        orphan = other.post("/audits", json={"url": "https://example.net"}).json()
        from app.db import SessionLocal
        from app.models import Audit
        with SessionLocal() as s:
            s.get(Audit, orphan["id"]).project_id = None
            s.commit()
        projects = other.get("/projects").json()
        assert projects[0]["audit_count"] == 1
        assert other.get(f"/audits/{orphan['id']}").json()["project_id"] == projects[0]["id"]

        assert other.get(f"/projects/{rosa['id']}").status_code == 404
        assert other.post("/audits", json={"url": "https://example.com", "project_id": rosa["id"]}).status_code == 404
