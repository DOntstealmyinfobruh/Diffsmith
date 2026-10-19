from fastapi.testclient import TestClient

import diffsmith.server as server
from diffsmith.llm import ScriptedClient
from test_agent import GOOD

client = TestClient(server.app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_edit_endpoint(repo, monkeypatch):
    monkeypatch.setenv("DIFFSMITH_EMBEDDER", "hashing")
    monkeypatch.setattr("diffsmith.agent.make_llm", lambda cfg: ScriptedClient([GOOD]))
    resp = client.post("/edit", json={"repo": str(repo), "request": "validate discount percent"})
    body = resp.json()
    assert resp.status_code == 200, body
    assert body["success"] and body["commit"]


def test_rejects_non_git_dir(tmp_path):
    resp = client.post("/edit", json={"repo": str(tmp_path), "request": "anything"})
    assert resp.status_code == 400


def test_allowed_roots(repo, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("DIFFSMITH_ALLOWED_ROOTS", str(tmp_path_factory.mktemp("other")))
    resp = client.post("/edit", json={"repo": str(repo), "request": "anything"})
    assert resp.status_code == 403
