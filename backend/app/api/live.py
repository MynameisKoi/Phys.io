"""Live lab API: start an agent run from a problem statement, watch it, chart it, download it.

Endpoints (all under /api/lab):
  GET  /status                  whether this backend can start runs (local lab mode)
  GET  /runs                    run folders under runs/, newest first
  POST /runs                    start a run: problem statement -> Omnigent session
  POST /runs/{id}/stop          stop a run this backend started
  GET  /runs/{id}/activity      agent tree and a timeline of messages, tool calls, records, logs
  GET  /runs/{id}/experiments   each experiment's simulations live, and its results.csv when done
  GET  /runs/{id}/report        final_report.md, or the latest knowledge/cycle_<n>.md
  GET  /runs/{id}/download      the whole run folder as a zip

Starting runs only works where Omnigent runs with your Claude credentials (LAB_ALLOW_START=1).
/status lists anything missing (omni, tmux, the agent sandbox, the Omnigent server), and Start
is refused until it is there: there is no scripted stand-in for the agents. With LAB_ACCESS_CODE
set, starting and stopping need that code (header X-Lab-Code), and only one run may be active at
a time: they spend Claude credits. The run is a normal interactive Omnigent session in a hidden
tmux window: `omni run -p` is one-shot and would stop the departments after the Director's first
turn. Without Omnigent the same endpoints still serve runs already on disk.
The backend never makes a scientific decision: it starts the Director with the user's
problem statement and reads files and Omnigent's session history. A watchdog tells the
Director when a department logged a decision it was not notified about (see below).
"""
from __future__ import annotations

import functools
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lab.csv_helper import read_results_csv  # noqa: E402

router = APIRouter(prefix="/api/lab")

RUNS = Path(os.getenv("LAB_RUNS_DIR", ROOT / "runs"))
OMNIGENT_URL = os.getenv("OMNIGENT_URL", "http://127.0.0.1:6767").rstrip("/")
AGENT_BUNDLE = "backend/app/agents"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
READY_TIMEOUT_S = 90
TEXT_LIMIT = 600


def _allow_start() -> bool:
    return os.getenv("LAB_ALLOW_START") == "1"


def _check_code(code: str | None) -> None:
    """Starting and stopping runs spends Claude credits: require LAB_ACCESS_CODE when it is set."""
    expected = os.getenv("LAB_ACCESS_CODE", "")
    if expected and (code or "") != expected:
        raise HTTPException(401, "Wrong or missing access code.")


def _active_runs() -> list[str]:
    if not RUNS.is_dir():
        return []
    active = []
    for d in RUNS.iterdir():
        if d.is_dir() and RUN_ID_RE.match(d.name) and _tmux_alive(d.name):
            if (d / "final_report.md").is_file():
                subprocess.run(["tmux", "kill-session", "-t", _tmux_name(d.name)], capture_output=True)
                continue
            active.append(d.name)
    return active


def _run_dir(run_id: str, must_exist: bool = True) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(422, "Run IDs use letters, digits, '-' and '_' only (max 64).")
    path = RUNS / run_id
    if must_exist and not path.is_dir():
        raise HTTPException(404, f"No run '{run_id}'.")
    return path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _omnigent(path: str, timeout: float = 5.0):
    """GET a JSON resource from the local Omnigent server, or None when it is unreachable."""
    try:
        with urllib.request.urlopen(f"{OMNIGENT_URL}{path}", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data.get("data", data) if isinstance(data, dict) and "data" in data else data


def _tmux_name(run_id: str) -> str:
    return f"physio-{run_id}"


@functools.cache
def _sandbox_works() -> bool:
    """Agents with an os_env block run in bwrap on Linux; some containers forbid the namespaces it needs."""
    if not sys.platform.startswith("linux"):
        return True  # macOS uses Seatbelt, which is always available
    if not shutil.which("bwrap"):
        return False
    probe = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--unshare-all", "true"]
    return subprocess.run(probe, capture_output=True).returncode == 0


def _tmux_alive(run_id: str) -> bool:
    if not shutil.which("tmux"):
        return False
    return subprocess.run(["tmux", "has-session", "-t", _tmux_name(run_id)], capture_output=True).returncode == 0


# --------------------------------------------------------------------------- status and runs


@router.get("/status")
def status() -> dict:
    """Whether this backend can start runs, and why not."""
    _ensure_watchdog()
    reasons = []
    if not _allow_start():
        reasons.append("Starting runs is off on this server (set LAB_ALLOW_START=1 on the machine that runs Omnigent).")
    else:
        if not shutil.which("omni"):
            reasons.append("The Omnigent CLI (omni) is not installed here.")
        if not shutil.which("tmux"):
            reasons.append("tmux is not installed here.")
        if not _sandbox_works():
            reasons.append("The agent sandbox (bwrap) cannot run on this machine, so the file-writing agents would fail.")
        if _omnigent("/v1/sessions?limit=1", timeout=2) is None:
            reasons.append(f"The Omnigent server at {OMNIGENT_URL} is not running (start it with `omni start`).")
    return {
        "can_start": not reasons,
        "reasons": reasons,
        "needs_code": bool(os.getenv("LAB_ACCESS_CODE")),
        "active_runs": _active_runs() if not reasons else [],
        "omnigent_url": OMNIGENT_URL,
    }


@router.get("/runs")
def runs() -> list[dict]:
    """Run folders under runs/, newest first."""
    if not RUNS.is_dir():
        return []
    out = []
    for d in RUNS.iterdir():
        if not d.is_dir() or not RUN_ID_RE.match(d.name) or d.name == "example":
            continue
        problem = _read_json(d / "problem.json")
        has_report = (d / "final_report.md").is_file()
        out.append({
            "id": d.name,
            "problem": problem.get("problem"),
            "started_at": problem.get("started_at") or d.stat().st_mtime,
            "records": len(_read_jsonl(d / "record.jsonl")),
            "experiments": len(list((d / "experiments").glob("*/results.csv"))) if (d / "experiments").is_dir() else 0,
            "has_report": has_report,
            "running": _tmux_alive(d.name) and not has_report,
        })
    return sorted(out, key=lambda r: r["started_at"] or 0, reverse=True)


class StartRequest(BaseModel):
    problem: str = Field(..., min_length=20, max_length=4000)
    cycles: int = Field(2, ge=1, le=5)
    run_id: str | None = None


def _task_text(run_id: str, problem: str, cycles: int) -> str:
    one_line = " ".join(problem.split())
    return (
        f"Run ID: {run_id}. Cycles: up to {cycles}. Problem statement from the user: {one_line} "
        "Work through the departments on this problem, and make the final call to Knowledge & Memory "
        "before you stop."
    )


def _send_task_when_ready(run_id: str, name: str, task: str, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _tmux_alive(run_id):
            return
        pane = subprocess.run(["tmux", "capture-pane", "-p", "-t", name], capture_output=True, text=True).stdout
        if "· ready" in pane:
            subprocess.run(["tmux", "send-keys", "-t", name, "-l", task], check=False)
            subprocess.run(["tmux", "send-keys", "-t", name, "Enter"], check=False)
            return
        time.sleep(1)


@router.post("/runs")
def start_run(req: StartRequest, x_lab_code: str | None = Header(default=None)) -> dict:
    """Start the Lab Director on a problem statement, in a new interactive Omnigent session."""
    state = status()
    if not state["can_start"]:
        raise HTTPException(403, " ".join(state["reasons"]))
    _check_code(x_lab_code)
    if state["active_runs"]:
        raise HTTPException(429, f"Run '{state['active_runs'][0]}' is still running; one run at a time.")
    run_id = req.run_id or f"run-{datetime.now():%Y%m%d-%H%M%S}"
    run_dir = _run_dir(run_id, must_exist=False)
    if run_dir.exists():
        raise HTTPException(409, f"Run '{run_id}' already exists.")
    run_dir.mkdir(parents=True)
    task = _task_text(run_id, req.problem, req.cycles)
    (run_dir / "problem.json").write_text(json.dumps({
        "run_id": run_id, "problem": req.problem, "cycles": req.cycles,
        "started_at": time.time(), "task": task,
    }, indent=2), encoding="utf-8")

    name = _tmux_name(run_id)
    env_exports = ""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRIGHTDATA_API_TOKEN", "ANTHROPIC_BASE_URL"):
        val = os.getenv(var)
        if val:
            env_exports += f"export {var}={shlex.quote(val)} && "

    command = (
        f"cd {shlex.quote(str(ROOT))} && {env_exports}env -u TMUX PYTHONPATH={shlex.quote(str(ROOT))} "
        f"omni run {AGENT_BUNDLE}"
    )
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "50", command], check=True)

    # Check for immediate ready signal (e.g. In tests or fast local runs)
    initial_deadline = time.time() + 5.0
    sent = False
    while time.time() < initial_deadline:
        pane = subprocess.run(["tmux", "capture-pane", "-p", "-t", name], capture_output=True, text=True).stdout
        if "· ready" in pane:
            subprocess.run(["tmux", "send-keys", "-t", name, "-l", task], check=True)
            subprocess.run(["tmux", "send-keys", "-t", name, "Enter"], check=True)
            sent = True
            break
        if not _tmux_alive(run_id):
            raise HTTPException(500, "Omnigent exited before it was ready; see ~/.omnigent/logs/cli/.")
        time.sleep(0.5)

    if not sent:
        # Continue waiting asynchronously to avoid HTTP 30s gateway timeout
        threading.Thread(
            target=_send_task_when_ready,
            args=(run_id, name, task, READY_TIMEOUT_S),
            daemon=True,
            name=f"starter-{run_id}",
        ).start()

    return {"run_id": run_id, "task": task}


@router.get("/runs/{run_id}/pane")
def run_pane(run_id: str) -> dict:
    """Live terminal pane text from the tmux session running Omnigent."""
    name = _tmux_name(run_id)
    res = subprocess.run(["tmux", "capture-pane", "-p", "-t", name], capture_output=True, text=True)
    return {
        "run_id": run_id,
        "running": _tmux_alive(run_id),
        "pane": res.stdout if res.returncode == 0 else f"No active tmux session for {run_id}",
    }


@router.get("/runs/{run_id}/logs")
def run_logs(run_id: str) -> dict:
    """Recent Omnigent logs from ~/.omnigent/logs/."""
    log_dir = Path.home() / ".omnigent" / "logs"
    logs = {}
    for sub in ("cli", "runner", "host"):
        p = log_dir / sub
        if p.is_dir():
            files = sorted(p.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                logs[sub] = files[0].read_text(encoding="utf-8", errors="ignore")[-4000:]
    return {"run_id": run_id, "logs": logs}


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, x_lab_code: str | None = Header(default=None)) -> dict:
    """Stop a run this backend started (closes its Omnigent session window)."""
    if not _allow_start():
        raise HTTPException(403, "Stopping runs is off on this server.")
    _check_code(x_lab_code)
    _run_dir(run_id)
    was_running = _tmux_alive(run_id)
    if was_running:
        subprocess.run(["tmux", "kill-session", "-t", _tmux_name(run_id)], capture_output=True)
    return {"run_id": run_id, "stopped": was_running}


# --------------------------------------------------------------------------- watchdog

# A Lead often ends its turn while its specialist is still working ("waiting for the specialist").
# Omnigent then tells the Director the Lead finished, and when the Lead later completes its real
# decision (woken by the specialist, not by the Director), nobody tells the Director. Every agent
# goes idle and the run stalls. The watchdog notices a department decision logged after the
# Director's last action and tells the Director, once per log entry. It makes no scientific
# decision: it only reports a fact the Director can verify in the department logs.
WATCHDOG_INTERVAL_S = 10
WATCHDOG_SETTLE_S = 15
_watchdog_started = False
_watchdog_lock = threading.Lock()


def _latest_department_entry(run_dir: Path) -> dict | None:
    latest = None
    for log in (run_dir / "logs").glob("*/department.jsonl") if (run_dir / "logs").is_dir() else []:
        for entry in _read_jsonl(log):
            if latest is None or entry.get("t", 0) > latest.get("t", 0):
                latest = entry
    return latest


def _watchdog_check(run_id: str) -> str | None:
    """Nudge the Director of one run if it missed a department decision or if a department stalled."""
    run_dir = RUNS / run_id
    if (run_dir / "final_report.md").is_file():
        if _tmux_alive(run_id):
            subprocess.run(["tmux", "kill-session", "-t", _tmux_name(run_id)], capture_output=True)
        return None
    root = _root_session(run_id, run_dir)
    if not root:
        return None
    dir_info = _omnigent(f"/v1/sessions/{root}") or {}
    if (dir_info.get("status") or "idle") != "idle":
        return None
    live = _read_json(run_dir / "live.json")
    last = _omnigent(f"/v1/sessions/{root}/items?limit=1&order=desc") or []
    director_t = float(last[0].get("created_at") or 0) if isinstance(last, list) and last else 0.0

    entry = _latest_department_entry(run_dir)
    if entry and (time.time() - entry.get("t", 0) >= WATCHDOG_SETTLE_S) and (entry.get("t", 0) > director_t):
        if entry.get("id") not in live.get("nudged", []):
            department = entry.get("department", "A department")
            text = (
                f"[Lab runtime] The {department} department logged its decision ({entry.get('id')}) after its "
                f"earlier reply to you, so you were not notified. Read the department logs "
                f"(read_all_department_logs, run_id {run_id}) and the record, then continue the run."
            )
            subprocess.run(["tmux", "send-keys", "-t", _tmux_name(run_id), "-l", text], check=False)
            subprocess.run(["tmux", "send-keys", "-t", _tmux_name(run_id), "Enter"], check=False)
            live["nudged"] = live.get("nudged", []) + [entry.get("id")]
            (run_dir / "live.json").write_text(json.dumps(live), encoding="utf-8")
            with open(run_dir / "runtime.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "kind": "nudge", "entry": entry.get("id"), "text": text}, ensure_ascii=False) + "\n")
            return text

    # Stall recovery: Director has been waiting for > 90s after sending to a department without a department log
    if director_t and (time.time() - director_t > 90):
        # Find which department was targeted in the last interaction
        target_dept = None
        for item in (last if isinstance(last, list) else []):
            for block in item.get("content", []):
                if isinstance(block, dict) and block.get("name") == "sys_session_send":
                    args_raw = block.get("arguments") or "{}"
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        target_dept = args.get("agent")
                    except Exception:
                        pass
        if target_dept and target_dept != "lab_director":
            dept_log = run_dir / "logs" / target_dept / "department.jsonl"
            stall_key = f"stall_{target_dept}_{int(director_t)}"
            if not dept_log.is_file() and stall_key not in live.get("nudged", []):
                text = (
                    f"[Lab runtime] Department '{target_dept}' investigations are complete. "
                    f"Please instruct the {target_dept} Lead to finalize its decision, have {target_dept}_secretary "
                    f"write the department log and provide the 8-heading briefing, then proceed."
                )
                subprocess.run(["tmux", "send-keys", "-t", _tmux_name(run_id), "-l", text], check=False)
                subprocess.run(["tmux", "send-keys", "-t", _tmux_name(run_id), "Enter"], check=False)
                live["nudged"] = live.get("nudged", []) + [stall_key]
                (run_dir / "live.json").write_text(json.dumps(live), encoding="utf-8")
                with open(run_dir / "runtime.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.time(), "kind": "nudge", "text": text}, ensure_ascii=False) + "\n")
                return text

    return None


def _watchdog_loop() -> None:
    while True:
        try:
            for run_id in _active_runs():
                _watchdog_check(run_id)
        except Exception:  # never let the watchdog die; it retries next round
            pass
        time.sleep(WATCHDOG_INTERVAL_S)


def _ensure_watchdog() -> None:
    global _watchdog_started
    if not _allow_start():
        return
    with _watchdog_lock:
        if not _watchdog_started:
            threading.Thread(target=_watchdog_loop, name="lab-watchdog", daemon=True).start()
            _watchdog_started = True


# --------------------------------------------------------------------------- observability


def _item_event(item: dict, agent: str) -> dict | None:
    kind = item.get("type")
    t = float(item.get("created_at") or 0)
    if kind == "message":
        parts = item.get("content") or []
        text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        if not text:
            return None
        return {"t": t, "agent": agent, "kind": f"message:{item.get('role', '')}", "text": text[:TEXT_LIMIT]}
    if kind == "function_call":
        name = (item.get("name") or "").replace("mcp__omnigent__", "")
        if name in ("ToolSearch", "sys_read_inbox"):
            return None
        args = item.get("arguments") or ""
        try:  # show symbols (τ, −, µ) instead of \u escapes
            args = json.dumps(json.loads(args), ensure_ascii=False)
        except ValueError:
            pass
        return {"t": t, "agent": agent, "kind": "tool_call", "tool": name, "text": args[:TEXT_LIMIT]}
    if kind == "function_call_output":
        out = str(item.get("output") or "")
        try:
            out = json.dumps(json.loads(out), ensure_ascii=False)
        except ValueError:
            pass
        return {"t": t, "agent": agent, "kind": "tool_result", "text": out[:TEXT_LIMIT]}
    return None


def _root_session(run_id: str, run_dir: Path) -> str | None:
    live = _read_json(run_dir / "live.json")
    if live.get("session_id"):
        return live["session_id"]
    sessions = _omnigent("/v1/sessions?limit=100&order=desc") or []
    for s in sessions if isinstance(sessions, list) else []:
        if (s.get("title") or "").startswith(f"Run ID: {run_id}."):
            (run_dir / "live.json").write_text(json.dumps({"session_id": s["id"]}), encoding="utf-8")
            return s["id"]
    return None


def _session_tree(session_id: str, agent: str, depth: int = 0) -> list[tuple[str, str]]:
    nodes = [(session_id, agent)]
    if depth >= 3:
        return nodes
    for child in _omnigent(f"/v1/sessions/{session_id}/child_sessions?limit=100") or []:
        child_agent = (child.get("title") or "agent").split(":")[0]
        nodes += _session_tree(child["id"], child_agent, depth + 1)
    return nodes


@router.get("/runs/{run_id}/activity")
def activity(run_id: str, limit: int = 300) -> dict:
    """What the agents are doing: Omnigent messages and tool calls, plus records and logs on disk."""
    run_dir = _run_dir(run_id)
    events: list[dict] = []
    agents: list[dict] = []
    root = _root_session(run_id, run_dir)
    if root:
        for session_id, agent in _session_tree(root, "lab_director"):
            info = _omnigent(f"/v1/sessions/{session_id}") or {}
            agents.append({
                "agent": agent, "session_id": session_id,
                "status": info.get("status"), "error": info.get("last_task_error"),
                "cost_usd": info.get("total_cost_usd"),
            })
            items = _omnigent(f"/v1/sessions/{session_id}/items?limit=200&order=desc") or []
            for item in reversed(items if isinstance(items, list) else []):
                event = _item_event(item, agent)
                if event:
                    events.append(event)
    for entry in _read_jsonl(run_dir / "record.jsonl"):
        events.append({"t": entry.get("t", 0), "agent": entry.get("agent", ""), "kind": "record",
                       "text": f"{entry.get('id')} · {entry.get('kind')} · {json.dumps(entry.get('content'), ensure_ascii=False)[:TEXT_LIMIT]}"})
    for log in sorted((run_dir / "logs").glob("*/*.jsonl")) if (run_dir / "logs").is_dir() else []:
        for entry in _read_jsonl(log):
            events.append({"t": entry.get("t", 0), "agent": f"{entry.get('department')}_secretary",
                           "kind": f"log:{entry.get('level')}",
                           "text": f"{entry.get('id')} · {json.dumps(entry.get('payload'), ensure_ascii=False)[:TEXT_LIMIT]}"})
    for entry in _read_jsonl(run_dir / "runtime.jsonl"):
        events.append({"t": entry.get("t", 0), "agent": "lab_runtime", "kind": "runtime", "text": entry.get("text", "")})
    if not events and _tmux_alive(run_id):
        name = _tmux_name(run_id)
        pane = subprocess.run(["tmux", "capture-pane", "-p", "-t", name], capture_output=True, text=True).stdout
        non_empty = [line.strip() for line in pane.splitlines() if line.strip()]
        last_line = non_empty[-1] if non_empty else "Session initializing..."
        events.append({
            "t": time.time(),
            "agent": "lab_director",
            "kind": "runtime:session",
            "text": f"Agent terminal: {last_line[:140]}",
        })
    events.sort(key=lambda e: e["t"])
    problem = _read_json(run_dir / "problem.json")
    if not agents:
        depts = ["lab_director", "literature", "hypothesis", "planning", "experiment_runner", "analysis", "review_safety", "knowledge_memory"]
        for d in depts:
            agents.append({"agent": d, "status": "working" if _tmux_alive(run_id) else "idle"})
    return {
        "run_id": run_id,
        "problem": problem.get("problem"),
        "running": _tmux_alive(run_id) and not (run_dir / "final_report.md").is_file(),
        "omnigent_connected": root is not None,
        "agents": agents,
        "events": events[-limit:],
    }


# --------------------------------------------------------------------------- data and files


@router.get("/runs/{run_id}/experiments")
def experiments(run_id: str) -> dict:
    """Each experiment's live simulations (evaluations.jsonl) and final results.csv rows, plus the control."""
    run_dir = _run_dir(run_id)
    out = []
    exp_root = run_dir / "experiments"
    for exp_dir in sorted(d for d in exp_root.iterdir() if d.is_dir()) if exp_root.is_dir() else []:
        csv_path = exp_dir / "results.csv"
        rows = []
        if csv_path.is_file():
            try:
                rows = read_results_csv(csv_path)
            except (OSError, KeyError, ValueError):
                rows = []
        # One line per simulation, written live by the simulator while run.py runs.
        evaluations = [
            {k: e.get(k) for k in ("evaluation", "t", "materials", "thicknesses_nm", "substrate", "valid",
                                   "p_net_w_m2", "solar_reflectance", "window_emissivity")}
            for e in _read_jsonl(exp_dir / "evaluations.jsonl")
        ]
        if rows or evaluations:
            out.append({"experiment_id": exp_dir.name, "finished": csv_path.is_file(),
                        "rows": rows, "evaluations": evaluations})
    control = _read_json(ROOT / "results" / "control.json")
    return {
        "run_id": run_id,
        "experiments": out,
        "control": {**control.get("simulated", {}), "target_w_m2": control.get("target_w_m2")},
    }


@router.get("/runs/{run_id}/report")
def report(run_id: str) -> dict:
    """final_report.md, or the latest knowledge/cycle_<n>.md when there is no final report yet."""
    run_dir = _run_dir(run_id)
    final = run_dir / "final_report.md"
    if final.is_file():
        return {"file": "final_report.md", "markdown": final.read_text(encoding="utf-8")}
    cycles = sorted((run_dir / "knowledge").glob("cycle_*.md")) if (run_dir / "knowledge").is_dir() else []
    if cycles:
        return {"file": f"knowledge/{cycles[-1].name}", "markdown": cycles[-1].read_text(encoding="utf-8")}
    return {"file": None, "markdown": None}


@router.get("/runs/{run_id}/download")
def download(run_id: str) -> StreamingResponse:
    """The whole run folder as a zip: record, logs, experiments, knowledge, Common Knowledge."""
    run_dir = _run_dir(run_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(run_id) / path.relative_to(run_dir))
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'},
    )
