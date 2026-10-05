"""Live lab API. Omnigent and tmux are replaced by fakes, so no Claude credits are spent."""

import io
import json
import zipfile

import pytest
import httpx
from fastapi.testclient import TestClient

from app.api import live
from app import main as main_module
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(live, "_omnigent", lambda path, timeout=5.0: [] if path.startswith("/v1/sessions?") else None)
    return TestClient(app)


@pytest.fixture()
def fake_tmux(monkeypatch):
    """Record tmux calls; every new session reports ready at once and stays alive."""
    calls, alive = [], set()

    class Done:
        def __init__(self, stdout="", returncode=0):
            self.stdout, self.returncode = stdout, returncode

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["tmux", "new-session"]:
            alive.add(cmd[cmd.index("-s") + 1])
        if cmd[:2] == ["tmux", "kill-session"]:
            alive.discard(cmd[-1])
        if cmd[:2] == ["tmux", "has-session"]:
            return Done(returncode=0 if cmd[-1] in alive else 1)
        if cmd[:2] == ["tmux", "capture-pane"]:
            return Done(stdout="radiative cooling lab · ready")
        return Done()

    monkeypatch.setattr(live.subprocess, "run", run)
    monkeypatch.setattr(live.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(live, "_sandbox_works", lambda: True)
    monkeypatch.setenv("LAB_ALLOW_START", "1")
    return calls


PROBLEM = "Design a coating of at most 5 layers that beats the Stanford control."


def test_starting_is_off_by_default(client, monkeypatch):
    monkeypatch.delenv("LAB_ALLOW_START", raising=False)
    status = client.get("/api/lab/status").json()
    assert status["can_start"] is False and "LAB_ALLOW_START" in status["reasons"][0]
    assert client.post("/api/lab/runs", json={"problem": PROBLEM}).status_code == 403


def test_a_server_without_omnigent_refuses_to_start_instead_of_faking_a_run(client, monkeypatch):
    monkeypatch.setenv("LAB_ALLOW_START", "1")
    monkeypatch.setattr(live.shutil, "which", lambda name: None)
    monkeypatch.setattr(live, "_sandbox_works", lambda: True)
    status = client.get("/api/lab/status").json()
    assert status["can_start"] is False
    assert any("omni" in r for r in status["reasons"]) and any("tmux" in r for r in status["reasons"])
    res = client.post("/api/lab/runs", json={"problem": PROBLEM, "run_id": "nope"})
    assert res.status_code == 403 and not (live.RUNS / "nope").exists()


def test_start_sends_the_problem_to_a_new_session(client, fake_tmux, monkeypatch):
    monkeypatch.setenv("LAB_ACCESS_CODE", "secret")
    assert client.post("/api/lab/runs", json={"problem": PROBLEM}).status_code == 401
    assert client.post("/api/lab/runs", json={"problem": "too short"}, headers={"X-Lab-Code": "secret"}).status_code == 422

    res = client.post("/api/lab/runs", json={"problem": PROBLEM + "\nSecond line.", "cycles": 2, "run_id": "demo1"},
                      headers={"X-Lab-Code": "secret"})
    assert res.status_code == 200, res.text
    task = res.json()["task"]
    assert task.startswith("Run ID: demo1. Cycles: up to 2.") and "\n" not in task
    new_session = next(c for c in fake_tmux if c[:2] == ["tmux", "new-session"])
    assert "physio-demo1" in new_session and "omni run backend/app/agents" in new_session[-1]
    assert " -p " not in new_session[-1]
    assert ["tmux", "send-keys", "-t", "physio-demo1", "-l", task] in fake_tmux
    saved = json.loads((live.RUNS / "demo1" / "problem.json").read_text())
    assert saved["problem"].startswith("Design a coating") and saved["cycles"] == 2

    busy = client.post("/api/lab/runs", json={"problem": PROBLEM}, headers={"X-Lab-Code": "secret"})
    assert busy.status_code == 429
    assert client.post("/api/lab/runs/demo1/stop").status_code == 401
    assert client.post("/api/lab/runs/demo1/stop", headers={"X-Lab-Code": "secret"}).json()["stopped"] is True


def test_run_data_endpoints(client):
    run = live.RUNS / "r1"
    (run / "logs" / "literature").mkdir(parents=True)
    (run / "experiments" / "E1").mkdir(parents=True)
    (run / "record.jsonl").write_text(json.dumps({"id": "L1", "kind": "literature", "agent": "literature_lead", "t": 2, "content": {}}) + "\n")
    (run / "logs" / "literature" / "department.jsonl").write_text(
        json.dumps({"id": "literature.department.1", "t": 1, "department": "literature", "level": "department", "payload": {}}) + "\n")
    (run / "experiments" / "E1" / "results.csv").write_text(
        "design_id,materials,thicknesses_nm,substrate,n_layers,p_net_w_m2,solar_reflectance,window_emissivity,valid,reason,seed\n"
        "E1-001,SiO2,500.0,Ag,1,12.5,0.96,0.4,true,ok,0\n")
    (run / "final_report.md").write_text("# Final report\n")

    runs = client.get("/api/lab/runs").json()
    assert runs[0]["id"] == "r1" and runs[0]["records"] == 1 and runs[0]["experiments"] == 1
    events = client.get("/api/lab/runs/r1/activity").json()["events"]
    assert [e["kind"] for e in events] == ["log:department", "record"]
    exp = client.get("/api/lab/runs/r1/experiments").json()
    assert exp["experiments"][0]["rows"][0]["p_net_w_m2"] == 12.5 and exp["experiments"][0]["finished"] is True

    (run / "experiments" / "E2").mkdir()
    (run / "experiments" / "E2" / "evaluations.jsonl").write_text(
        json.dumps({"evaluation": 1, "t": 3, "materials": ["SiO2"], "valid": True, "p_net_w_m2": 9.0}) + "\n")
    running = client.get("/api/lab/runs/r1/experiments").json()["experiments"][1]
    assert running["finished"] is False and running["evaluations"][0]["p_net_w_m2"] == 9.0
    assert client.get("/api/lab/runs/r1/report").json()["file"] == "final_report.md"
    zipped = client.get("/api/lab/runs/r1/download")
    assert zipped.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert "r1/record.jsonl" in names and "r1/experiments/E1/results.csv" in names


def test_run_ids_cannot_escape_the_runs_folder(client):
    assert client.get("/api/lab/runs/..%2F..%2Fetc/activity").status_code in (404, 422)
    assert client.get("/api/lab/runs/bad%20id/download").status_code == 422
    assert client.get("/api/lab/runs/missing/report").status_code == 404


def test_watchdog_tells_the_director_about_a_missed_decision_once(client, fake_tmux, monkeypatch):
    run = live.RUNS / "w1"
    (run / "logs" / "hypothesis").mkdir(parents=True)
    (run / "logs" / "hypothesis" / "department.jsonl").write_text(
        json.dumps({"id": "hypothesis.department.1", "t": 1000.0, "department": "hypothesis", "level": "department"}) + "\n")
    monkeypatch.setattr(live, "_root_session", lambda run_id, run_dir: "root")
    monkeypatch.setattr(live, "_session_tree", lambda sid, agent, depth=0: [("root", "lab_director"), ("c1", "hypothesis")])
    director_t = {"value": 900.0}
    statuses = {"value": "idle"}

    def omnigent(path, timeout=5.0):
        if path.endswith("/items?limit=1&order=desc"):
            return [{"created_at": str(director_t["value"])}]
        return {"status": statuses["value"]}

    monkeypatch.setattr(live, "_omnigent", omnigent)
    monkeypatch.setattr(live.time, "time", lambda: 2000.0)

    statuses["value"] = "running"
    assert live._watchdog_check("w1") is None          # someone is still working
    statuses["value"] = "idle"
    text = live._watchdog_check("w1")
    assert "hypothesis.department.1" in text and "run_id w1" in text
    assert ["tmux", "send-keys", "-t", "physio-w1", "-l", text] in fake_tmux
    assert live._watchdog_check("w1") is None          # only once per log entry
    assert json.loads((run / "runtime.jsonl").read_text())["entry"] == "hypothesis.department.1"

    director_t["value"] = 1500.0                       # Director already acted after the entry
    (run / "live.json").write_text("{}")
    assert live._watchdog_check("w1") is None


def test_forwarding_to_remote_sandbox(client, monkeypatch):
    import httpx
    import app.main as main_module

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["content"] = request.content
        if request.url.path == "/api/lab/runs/r1/download":
            return httpx.Response(200, content=b"PK-fake-zip", headers={"content-type": "application/zip"})
        return httpx.Response(200, json={"can_start": True, "source": "remote_sandbox"})

    class MockAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setenv("LAB_REMOTE_URL", "https://sandbox.example.com")
    monkeypatch.setattr(main_module.httpx, "AsyncClient", MockAsyncClient)

    # 1. GET status forwarded
    res = client.get("/api/lab/status")
    assert res.status_code == 200
    assert res.json() == {"can_start": True, "source": "remote_sandbox"}
    assert captured["url"] == "https://sandbox.example.com/api/lab/status"

    # 2. POST with headers and body forwarded
    res = client.post("/api/lab/runs", json={"problem": "test problem"}, headers={"X-Lab-Code": "mycode"})
    assert res.status_code == 200
    assert captured["method"] == "POST"
    assert captured["url"] == "https://sandbox.example.com/api/lab/runs"
    assert captured["headers"].get("x-lab-code") == "mycode"
    assert b"test problem" in captured["content"]

    # 3. Zip download passed back unchanged
    res = client.get("/api/lab/runs/r1/download")
    assert res.status_code == 200
    assert res.content == b"PK-fake-zip"
    assert res.headers["content-type"] == "application/zip"


def test_forwarding_unreachable_returns_502(client, monkeypatch):
    monkeypatch.setenv("LAB_REMOTE_URL", "http://127.0.0.1:59999")
    res = client.get("/api/lab/status")
    assert res.status_code == 502
    assert "Remote lab sandbox unreachable at http://127.0.0.1:59999" in res.text


def test_forwarding_sanitizes_quoted_or_padded_url(client, monkeypatch):
    captured = {}

    def handler(request: httpx.Request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"can_start": True})

    class MockAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setenv("LAB_REMOTE_URL", '  "sandbox.example.com/ "  ')
    monkeypatch.setattr(main_module.httpx, "AsyncClient", MockAsyncClient)

    res = client.get("/api/lab/status")
    assert res.status_code == 200
    assert captured["url"] == "https://sandbox.example.com/api/lab/status"


