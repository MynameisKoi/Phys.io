# Agents: Radiative Cooling Lab

The Omnigent bundle for the lab. The LLM agents make every scientific decision. Python tools only
run deterministic work (simulation, record I/O, logging, budget counting) and never choose what to
do next. Do not add a LangChain, LangGraph or Python loop that decides for the agents.

## Hierarchy

Every department has exactly three agents: a Lead, a specialist and a secretary.

```
radiative-cooling-lab (Lab Director / Supervisor)
|
+-- literature          Literature Lead  -> literature_specialist,       literature_secretary
+-- hypothesis          Hypothesis Lead  -> hypothesis_specialist,       hypothesis_secretary
+-- planning            Planning Lead    -> planning_specialist,         planning_secretary
+-- experiment_runner   Runner Lead      -> experiment_runner_specialist, experiment_runner_secretary
+-- analysis            Analysis Lead    -> analysis_specialist,         analysis_secretary
+-- review_safety       Review Lead      -> review_safety_specialist,    review_safety_secretary
+-- knowledge_memory    Knowledge Lead   -> knowledge_memory_specialist, knowledge_memory_secretary
```

1 Lab Director, 7 Leads, 7 specialists, 7 secretaries. The Director only talks to Leads, and each
Lead only talks to its own specialist and secretary.

## Cycles

A cycle is one pass through the departments, from new evidence to a reviewed verdict. The Director
numbers the cycles and gives the cycle number in every task; every log entry records it.

- **Analysis** and **Review & Safety** look only at the current cycle.
- **Knowledge & Memory** merges all cycles so far. The Director calls it at the end of a cycle and
  before stopping, and uses its report to plan the next cycle and to decide whether to stop.

## Run output: one folder, downloaded as a zip

The log database is set aside for now. Everything a run produces is a file in one run folder, and
at the end the user downloads that folder as a zip.

```
runs/<run_id>/
  record.jsonl                      the research record (shared contract)
  common_knowledge.json             this run's Common Knowledge, across all its cycles
  logs/<department>/department.jsonl   Lead decisions and reports
  logs/<department>/specialist.jsonl   specialist results
  experiments/<experiment_id>/      run.py, results.csv, output.log
  knowledge/merge.py                code that merges every results.csv
  knowledge/all_results.csv         all experiments' data in one table
  knowledge/cycle_<n>.md            Knowledge & Memory report per cycle
  final_report.md                   written by Knowledge & Memory on the final call, for the user
```

At the end of the process:

1. The Director decides to stop and calls Knowledge & Memory for the final merged report.
2. A packaging tool zips `runs/<run_id>/` into `runs/<run_id>.zip`. This is deterministic Python:
   it copies files and makes no decisions.
3. The Director tells the user the run is finished, gives a short summary, and prompts them to
   download the zip.

Not decided yet: how Omnigent offers the zip for download (a link in the web session, or a path on
disk). `package_run` exists in `lab/tools.py`, but no agent has it yet and the Director's prompt
does not mention the zip: until it does, make the zip by hand with
`python -c "from lab.tools import package_run; print(package_run('<run_id>'))"`.

## Website: live lab

Section 06 of the website (`frontend/index.html`, "Live lab") lets a user type a problem statement,
start a run, watch the agents, see the experiments charted and download the run as a zip. The
backend routes are in `backend/app/api/live.py` (`/api/lab/...`). The backend never makes a
scientific decision: it starts the Lab Director with the problem statement and reads files and
Omnigent's session history.

| Part of the page | Where the data comes from |
|---|---|
| Start run | `POST /api/lab/runs` writes `runs/<run_id>/problem.json`, opens a new interactive Omnigent session (`omni run backend/app/agents`) in a hidden tmux window, and types `Run ID: <run_id>. Cycles: up to <n>. Problem statement from the user: …`. Not `omni run -p`, which stops the run after the Director's first turn |
| Agents and activity | Omnigent's session tree (Director, Leads, specialists, secretaries) with every message and tool call, merged with `record.jsonl` and both log levels, ordered by time. Polled every 3 s while the run is active |
| Charts | Live: `run_experiment` points the simulator's ledger at `experiments/<id>/evaluations.jsonl`, so every `simulate_stack` call appears as it happens. Final: `results.csv` once the experiment finishes. The dashed line and red ring are the Stanford control from `results/control.json` |
| Report | `final_report.md`, or the latest `knowledge/cycle_<n>.md` |
| Download zip | `GET /api/lab/runs/<run_id>/download`: the whole run folder |

**Watchdog (stalled runs).** A Lead often ends its turn while its specialist is still working
("waiting for the specialist"). Omnigent then tells the Director the Lead finished, and when the
Lead later completes its decision (woken by its specialist, not by the Director), the Director is
never notified: every agent goes idle and the run stalls (seen twice in run `pdrc-01`). The backend
checks active runs every 20 s. When all agents are idle and a department logged a decision at least
45 s ago, after the Director's last action, it types one note into the Director's session:
`[Lab runtime] The <department> department logged its decision (<entry id>) … Read the department
logs … then continue the run.` One note per log entry; each is saved in `runs/<run_id>/runtime.jsonl`
and shown in the activity feed as `lab runtime`. It reports a fact the Director can check; it
never decides what happens next.

The page finds the backend by itself: the same address first (when the backend serves the site),
then the Render backend. `?api=<url>` forces a backend and `?run=<run_id>` opens a run.

**Live demo on your laptop** (agents need Omnigent and your Claude credentials):

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"
omni start
cd backend
LAB_ALLOW_START=1 LAB_ACCESS_CODE=<code> uvicorn app.main:app --port 8000
```

Open `http://localhost:8000/` (the backend serves the website too) and scroll to "Live lab".

**Judges starting runs from their own browser:** expose the same backend with a tunnel while your
laptop is on, e.g. `cloudflared tunnel --url http://localhost:8000` (`brew install cloudflared`),
and give them the printed `https://….trycloudflare.com` address and the access code. Site and API
then share one address, so no CORS setup is needed.

Safety limits for a public link: starting and stopping need `LAB_ACCESS_CODE`, only one run can be
active at a time, run IDs are restricted to letters, digits, `-` and `_`, and agent text is shown
as plain text, never as HTML.

**Public site without your laptop** (Vercel + Render): the same page, with "Start run" disabled.
It shows runs whose folders are on the Render backend. `runs/` is git-ignored, so to publish a
finished demo run, force-add it (`git add -f runs/<run_id>`) or copy it to the server.

**Cloud hosting in a Docker Sandboxes microVM (`sbx --cloud`):**
To host the live lab in an isolated cloud microVM where bubblewrap (`bwrap`) can execute with privileged namespaces and the full agent stack runs autonomously:

1. Sign in to Docker Cloud Sandboxes:
   ```bash
   sbx login
   ```
2. Provision and launch the live lab microVM:
   ```bash
   ./docker/sbx-up.sh
   ```
   This creates a 4-CPU / 8-GiB cloud sandbox with required network egress allowlists (`api.anthropic.com`, `api.openalex.org`, `mcp.brightdata.com`, etc.), builds `physio-live`, runs the container with `--privileged`, and publishes port 8000.
3. Note the generated HTTPS URL (from `sbx --cloud ports physio-live`) and set `LAB_REMOTE_URL` on Render so `/api/lab/*` requests forward directly to the sandbox.
4. Download completed run artifacts or teardown:
   ```bash
   # Download completed run folder
   sbx --cloud cp physio-live:/workspace/runs/<run_id> ./runs/
   # Or terminate the sandbox and save runs
   ./docker/sbx-down.sh
   ```


## Decision ownership

- **The specialist** investigates and advises. It returns its result to the Lead and writes nothing
  to the record or the logs.
- **The Lead** makes the department's decision, writes it to the record (only Leads have
  `write_record`), checks the secretary's briefing, and sends it to the Director.
- **The secretary** writes the department's log entries and the briefing for the Director. It works
  only from what the Lead sends, never changes it, never writes to the record, and decides nothing.
- **The Lab Director** decides which department acts next and when the research stops. It does not
  make the departments' scientific decisions.
- **Every Lead reports back to the Director** with the briefing when its department finishes.
  Leads never call another department, so every handoff goes through the Director.
- **Only the Director talks to the user.** When a Lead needs a human (e.g. a plan the agents cannot
  run), it puts a message for the user in its report, and the Director sends it and passes the
  answer back.

## Secretary: log and brief

This follows the "briefing officer" idea agreed in #18, with one change: the secretary no longer
writes to the record. Only the Lead does.

1. The specialist returns its result to the Lead. The Lead has the secretary log it at the
   `specialist` level.
2. The Lead decides and writes the decision to the record.
3. The Lead sends the decision to the secretary, which logs it at the `department` level and
   writes the briefing.
4. The Lead checks that the briefing matches its decision, sends it back to the secretary if
   anything is wrong, then sends it to the Director as its report.

Every briefing has the same headings, so the Director reads all departments the same way:

| Heading | Content |
|---|---|
| Decision | What the Lead decided, in one or two sentences |
| Record IDs | Entries the decision wrote and is based on |
| Reason | Why, in the Lead's words |
| Suggested next step | The Lead's recommendation; the Director decides |
| Repeat | `no`, or `yes` with the earlier log entry ID |
| Files | Locations of experiment folders or reports, or `none` |
| Needs the user | The message for the user, or `no` |
| Log entry | The ID of the department-log entry |

The secretary writes `not given` for anything the Lead did not send; it never fills gaps itself.

## File access (sandboxed)

Most agents have no file or shell tools: they work only through the lab tools. Omnigent grants
file and shell tools (`sys_os_read`, `sys_os_write`, `sys_os_edit`, `sys_os_shell`) only to agents
whose `config.yaml` has an `os_env` block, and runs them in a sandbox (Seatbelt on macOS, bwrap on
Linux). Six agents have one:

| Agent | Why | Writes | Network |
|---|---|---|---|
| `experiment_runner_specialist` | writes `run.py` | `runs/` only | no |
| `knowledge_memory_specialist` | reads every `results.csv`, writes and runs `merge.py` | `runs/` only | no |
| `knowledge_memory` (Lead) | writes `cycle_<n>.md`, `final_report.md` | `runs/` only | no |
| `experiment_runner` (Lead) | checks `run.py`, `results.csv`, `output.log` | none | no |
| `analysis_specialist` | reads this cycle's `results.csv` | none | no |
| `review_safety_specialist` | checks numbers against the CSV files | none | no |

Tested: writes inside `runs/` succeed, writes elsewhere fail with "Operation not permitted", the
repo can be read, and network requests are blocked. Lab tools (`run_experiment`, `read_paper`, …)
run outside this sandbox. Inside it, `python3` is the system Python without numpy, so `merge.py`
uses only the standard library and `lab.csv_helper`; `run.py` is run by `run_experiment`, which
uses Omnigent's Python.

## Log permissions

Each department has two log levels, stored as files in the run folder:

- **Department log:** the Lead's decisions and reports (`logs/<department>/department.jsonl`).
- **Specialist log:** the specialist's results (`logs/<department>/specialist.jsonl`).

| Agent | Department log | Specialist log | Tool |
|---|---|---|---|
| Lab Director | Read, all departments | No access | `read_all_department_logs` |
| Lead | Read, own department | Read, own department | `read_department_logs` |
| Knowledge Lead | Read, all departments (to merge cycles) | Read, own department | both of the above |
| Secretary | Write, own department | Write, own department | `log_to_common_knowledge` |
| Specialist | No access | No access | none |

No agent can read another department's specialist log. The Director gets detail by asking a Lead.
The tools enforce these limits, not just the prompts:
- each agent gets only the tools in its row (Omnigent loads only the tools in an agent's own
  folder);
- the secretary's and the Lead's wrappers have their department fixed, so they cannot write or
  read another department's log;
- `read_all_department_logs` never returns specialist logs.

The functions are in `lab/tools.py`. `log_to_common_knowledge` also records department-level
entries in the run's Common Knowledge (`runs/<run_id>/common_knowledge.json`). A run is one whole
research project across all its cycles, so each run has its own Common Knowledge, and it is in
that run's zip. The downloaded zip contains every log, because it is for the user, not for the
agents.

## Repeated results

When a specialist returns a result that is already in the specialist log:

1. The secretary logs it again, marked as a repeat of the earlier entry.
2. The Lead decides whether a rerun could give a different result, e.g. the inputs, the evidence or
   the search query changed since the earlier run.
3. **Yes:** the Lead reruns the specialist and says what is different. A rerun with the same inputs
   is not allowed.
4. **No:** the Lead reports the repeat to the Director, and the lab moves to the next cycle.

The Lead checks its own decisions against the department log the same way. The Director applies
the same logic one level up: if a department's report repeats its department log, the Director
calls it again only if something changed elsewhere in the lab; otherwise it moves to the next cycle.

## Defined departments

**Literature:** decides which published evidence the lab accepts.

1. `literature_specialist` searches Springer, Nature, IEEE and arXiv, filters the articles against
   the problem statement, and extracts claims, numbers with units, and conditions.
2. The Lead checks for repeats, then accepts or rejects findings and writes `literature` records.
3. `literature_secretary` logs the specialist's result and the Lead's decision.
4. The Lead reports to the Director, who decides which department acts next (usually Hypothesis).

**Hypothesis:** decides which hypothesis the lab tests next.

1. `hypothesis_specialist` checks earlier hypotheses against the new literature (consistent,
   conflicting or no bearing), scores each from 0 to 1, and proposes new candidates.
2. The Lead checks for repeats, then keeps, revises or replaces hypotheses and writes `hypothesis`
   records (status `proposed`).
3. `hypothesis_secretary` logs the specialist's result and the Lead's decision.
4. The Lead reports to the Director.

**Planning:** decides which experiment tests the hypothesis, why, and who can run it.

1. `planning_specialist` reasons from what the hypothesis predicts, to the measurement that would
   confirm or refute it, to the kind of experiment that produces it. It proposes at least 2
   candidates, each with why, expected gain, cost in simulator evaluations, steps, feasibility and
   cited sources.
2. If the methodology lacks literature support, the Lead reports the gap to the Director, who
   decides whether Literature collects more first.
3. The Lead picks one experiment and decides whether the agents can script and run it with the
   lab's tools. It writes a `plan` record with `runnable_by: agents` or `runnable_by: human`; for
   `human` it adds a message for the user, which the Director sends.
4. `planning_secretary` logs the specialist's result and the Lead's decision.

**Experiment Runner:** decides whether a run went as planned and its data is accepted.

1. `experiment_runner_specialist` writes the code (`run.py`, listing its inputs, tools, packages,
   outputs and the command to reproduce it), following `runs/example/experiments/E0/run.py`. It
   runs it with the `run_experiment` tool, which saves the code, `results.csv` (one row per
   simulation, written with `lab.csv_helper.write_results_csv`, failed designs kept) and
   `output.log` together in one experiment folder. Code is never changed after it produced data;
   a fix gets a new experiment folder.
2. The Lead checks that the run followed the plan, finished, and produced a complete CSV, then
   writes `experiment` and `result` records. It runs only plans marked `runnable_by: agents`.
3. `experiment_runner_secretary` logs where the files are (experiment ID, experiment folder, row
   count, status), not the data itself.
4. The Lead reports to the Director. Whether the result supports the hypothesis is Analysis's
   decision.

**Analysis:** decides the verdict on this cycle's hypothesis, from this cycle's results only.

1. `analysis_specialist` reads this cycle's CSV files, compares the best valid design with the
   benchmark (cooling power, solar reflectance, 8–13 µm emissivity) and with the hypothesis's
   prediction, explains failures, and says whether the evidence is enough.
2. The Lead writes a `verdict` record: `supported`, `refuted` or `inconclusive` (with what data is
   missing).
3. `analysis_secretary` logs the specialist's result and the Lead's decision.
4. The Lead reports the verdict and a recommendation for where to go next to the Director.

**Review & Safety:** decides whether this cycle's claims stand and whether actions need a human.

1. `review_safety_specialist` checks this cycle's records: citations exist and support the claims,
   numbers match the CSV files, hypotheses are labeled as hypotheses, designs respect the
   constraint, and which actions need approval.
2. The Lead writes an `approval` record with `needs_human: yes` or `no`, plus a message for the user
   when it is `yes`. Fabrication, anything outside simulation, and spending beyond the budget always
   need a human.
3. The Lead never fixes another department's record. It reports the problem, and the Director
   decides who fixes it.

**Knowledge & Memory:** collects the data of all cycles, processes it, and reports to the
Director. Called at the end of every cycle, and once more as the final call before the lab stops.

1. `knowledge_memory_specialist` collects `record.jsonl`, every experiment's `results.csv`, and the
   department logs the Lead passes on. It writes and runs `knowledge/merge.py`, which builds
   `knowledge/all_results.csv` (all rows, with `cycle` and `experiment_id` columns, failed designs
   kept), and computes the best design and evaluations used per cycle. It then merges findings,
   tracks how hypotheses changed, finds conflicts, and drafts the report.
2. The Lead checks that every experiment is included and row counts match the `result` entries,
   decides what becomes common knowledge, and writes `knowledge/cycle_<n>.md` (Established,
   Refuted, Best so far, Progress, Conflicts, Open questions). Outdated findings are marked, never
   deleted.
3. On the final call the Lead also writes `final_report.md` for the user: the question, findings,
   best design against the benchmark, refuted hypotheses, limitations, and the next experiment.
   That file goes into the downloaded zip.
4. `knowledge_memory_secretary` logs where the files are.
5. The Lead sends the Director a summary and the file locations.

Files from runs: see "Run output" above. Each experiment can be rerun with `python run.py` from
its folder.

Open questions:
- Agents pass `run_id` to the record and log tools themselves; it defaults to `"default"`. The
  Director should state the run ID in every task.
- The shared record has no field for the cycle number or kind for common knowledge. For now the
  cycle number goes in each entry's `content`, and the knowledge report is a file.
- Reruns have no hard limit. A budget policy could cap them.

## Folder layout

Every agent is a folder with two files. The folder nesting is the reporting line.

```
agents/                          <- this folder is the Lab Director's bundle
  config.yaml                    Director: which departments it may call
  prompt.md                      Director instructions
  agents/
    literature/                  Department Lead
      config.yaml                its specialist and secretary
      prompt.md
      agents/
        literature_specialist/   (no sub-agents)
          config.yaml
          prompt.md
        literature_secretary/    (no sub-agents)
          config.yaml
          prompt.md
```

Why prompts sit next to each config: Omnigent finds sub-agents at `agents/<name>/config.yaml`, and
`instructions: prompt.md` is only read from inside that agent's own folder. A path like
`../prompts/x.md` falls back to literal text, so a shared `prompts/` folder does not work.

Folder names are globally unique (`<department>_specialist`, `<department>_secretary`), so logs and
the record show which department an agent belongs to. Keep the folder name and the `name:` in
`config.yaml` the same.

## Rollout status

We bring the hierarchy up one department at a time, and only after nested delegation is proven.

| Step | Wired | Check |
|---|---|---|
| 1 | Director -> `literature` -> its specialist and secretary | The Lead's report reaches the Director in the Omnigent web session |
| 2 | + `hypothesis`, `planning`, `experiment_runner`, `analysis` | One full loop with a refuted hypothesis |
| 3 | + `review_safety` | Fabrication proposals ask a human |
| 4 | + `knowledge_memory` | Next cycle reads common knowledge |

**Current: step 1.** All folders exist, but only the departments listed in the Director's
`tools.agents` can be called. The rest are commented out in [config.yaml](config.yaml).

## Common changes

**Enable a department:** uncomment its line under `tools.agents` in [config.yaml](config.yaml).

**Change what a specialist does:** edit its `prompt.md`. Nothing else changes.

**Add an agent to a department:**
1. Copy the department's specialist folder, e.g. `agents/literature/agents/literature_specialist/`,
   to a new folder name in the same department.
2. Set `name:` and `description:` in the copy's `config.yaml`, and rewrite its `prompt.md`.
3. Add the folder name to the Lead's `tools.agents`, and mention it in the Lead's `prompt.md`.

**Remove an agent:** delete its folder and its line in the Lead's `tools.agents`.

None of these change the Director or the other departments.

## Prompt template

Lead prompts have: Decision you own, How you work, What to read from the record, What to write,
Logs, Repeated results, Rules. Specialist and secretary prompts state what they do, their log
access, and their rules. Every agent that writes to the record must "Cite the record IDs you based
this on."

Record kinds (shared contract): `literature`, `hypothesis`, `plan`, `experiment`, `result`,
`verdict`, `approval`.

## Check the bundle

Run this from the repo root or this folder to verify the entire hierarchy and discovered tools:

```bash
~/.local/share/uv/tools/omnigent/bin/python3 -c "
from pathlib import Path
from omnigent.spec.parser import parse
def show(s, d=0):
    lt = [t.name for t in s.local_tools]
    ag = s.tools.agents if s.tools else []
    print('  '*d + s.name, '->', ag, f'[local tools: {lt}]')
    for c in s.sub_agents: show(c, d+1)
show(parse(Path('backend/app/agents')))"
```

A malformed `config.yaml` makes this fail and names the file. If an agent prints its prompt path
instead of the prompt text, its `prompt.md` is missing or misnamed.

The simulator (`simulate_stack`, `optimize_thicknesses`), the record tools (`read_record`,
`write_record`), paper search (`search_papers`), material properties (`list_materials`, `material_properties`),
and the log tools (`log_to_common_knowledge`, `read_department_logs`, `read_all_department_logs`)
are deterministic tools implemented in [lab/tools.py](../../../lab/tools.py).

Omnigent finds local tools in `tools/python/*.py` inside each agent's folder, which is also how tool
permissions are enforced:
- **Specialists** carry domain tools: `literature_specialist` uses `search_papers` and
  `read_paper` (reads a found paper's page through Bright Data; only allowed publishers);
  `hypothesis_specialist` uses `list_materials` and `material_properties`;
  `experiment_runner_specialist` uses `simulate_stack`, `optimize_thicknesses` and
  `run_experiment`; `analysis_specialist` uses `compare_to_benchmark`.
- **Secretaries** carry only `log_to_common_knowledge`, fixed to their own department.
- **Department Leads** carry `read_record`, `write_record` and `read_department_logs`.
- **The Director** carries `read_record` and `read_all_department_logs`; the Knowledge Lead also
  has `read_all_department_logs`.

### What the agent-facing tools guarantee

Tools return data and never decide. These rules are covered by `tests/test_tools.py`:

- **`search_papers`** (`search_academic_papers`): only Springer, Nature, IEEE and arXiv. Every
  result has `origin`: `openalex` (live) or `offline_fallback` (built-in list, used when OpenAlex
  fails or returns too little). Fallback entries pass the same publisher filter, and each one's DOI
  was checked against OpenAlex. Results are not ranked; the Literature department decides.
- **`run_experiment(experiment_id, run_id, timeout_s)`**: runs the agent-written
  `runs/<run_id>/experiments/<experiment_id>/run.py` inside its folder, saves everything printed
  to `output.log`, and returns the exit code, a timeout flag, the paths and the row count of
  `results.csv`. It never writes or changes `run.py`. (`execute_experiment_script`, which built
  the script from a template, stays in `lab/tools.py` but no agent has it.)
- **`compare_to_benchmark(p_net_w_m2, solar_reflectance, window_emissivity)`**: compares cooling
  power with the Stanford control in our simulator (11.83 W/m²), and the two optional metrics with
  the control's values in `results/control.json`. Reports numbers only; Analysis decides the
  verdict.
- **`log_to_common_knowledge(payload, level, run_id, repeat_of)`**: appends to
  `runs/<run_id>/logs/<department>/<level>.jsonl`; `department` entries also go into the run's
  `common_knowledge.json`. Entry IDs look like `literature.specialist.3`.
- **`read_department_logs` / `read_all_department_logs`**: see "Log permissions".
- **`read_paper(url, max_chars)`**: reads a paper's page as text through Bright Data's
  `scrape_as_markdown`. Only arXiv, Nature, Springer and IEEE pages, or doi.org links with a
  `10.1038`, `10.1007`, `10.1186`, `10.1109` or `10.48550` DOI, are opened; anything else is
  refused, so it cannot search or browse the wider web. Returns the text with
  `origin: brightdata`, or an `error`, never a guess.
- **`package_run(run_id)`**: zips `runs/<run_id>/` into `runs/<run_id>.zip`, including the record,
  logs, experiments, knowledge reports and `common_knowledge.json`.

## Setup

From the repo root, once per machine:

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install numpy scipy optuna pyyaml pytest
uv pip install -e .
```

`uv pip install -e .` makes `lab`, `bench`, `analysis` and `physics_lab` importable from any
folder, which the agents' `run.py` and `merge.py` need. `pyproject.toml` lists those packages
explicitly; without that, setuptools stops with "Multiple top-level packages discovered".

Omnigent, from the repo root:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"
omni stop
omni start
omni run backend/app/agents
```

Then type the task at the prompt, starting with a run ID, e.g. `Run ID: smoke01. Cycle 1 only. …`.

Why each step matters:
- **`PYTHONPATH`:** Omnigent runs agent tools with its own Python, not `.venv`. Without the repo
  root on `PYTHONPATH`, every lab tool fails with `No module named 'lab'`.
- **Secrets and the environment:** Omnigent passes only an allowlist of variables (`PATH`,
  `PYTHONPATH`, `HOME`, …) to the processes that run agents and tools; API keys exported in your
  shell are dropped on purpose. So tools that need a key read it from the repo's `.env` file
  (`read_paper` does this for `BRIGHTDATA_API_TOKEN`), and `${VAR}` in an agent config will not
  see shell exports. The server keeps running in the background, so restart it (`omni stop`,
  `omni start`) after changing `PYTHONPATH`.
- **No `-p`:** `omni run -p "…"` is one-shot. It stops the whole run as soon as the Director's
  first turn ends, which kills the departments still working. Type the task in the interactive
  session instead and keep it open until the Director reports.
- `omni config list` shows the Claude credential; `omni usage` shows the cost of runs.

Checks:
- Bright Data MCP reachable with your token:
  `curl -s -o /dev/null -w "%{http_code}\n" -X POST https://mcp.brightdata.com/mcp -H "Authorization: Bearer $BRIGHTDATA_API_TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}'`
  prints `200`.
- `read_paper` works from a clean environment like Omnigent's:
  `env -i PATH="$PATH" HOME="$HOME" PYTHONPATH="$PWD" ~/.local/share/uv/tools/omnigent/bin/python3 -c "from lab.tools import read_paper; print(read_paper('https://arxiv.org/abs/2102.02965', 300))"`.
- A run's output: `ls -R runs/<run_id>`.
- Omnigent's own logs: `~/.omnigent/logs/` (`runner`, `server`, `host`, `cli`).

Keep secrets (`ANTHROPIC_API_KEY`, `BRIGHTDATA_API_TOKEN`, …) in `.env`, never in issues, configs
or code. Reference them as `${VAR}` in agent configs.

## Change log

Newest first.

- **Watchdog for stalled runs.** The backend tells the Director when a department logged a decision
  it was not notified about, once per log entry. See "Website: live lab".

- **Website live lab.** Section 06 of `frontend/index.html` and `backend/app/api/live.py`: problem
  statement box, agent activity feed, live experiment charts, report and zip download. The backend
  serves the website at `/`. Every simulation inside `run_experiment` is now also written to
  `experiments/<id>/evaluations.jsonl` (with reflectance and emissivity), so charts update during a
  run. See "Website: live lab".

- **Sandboxed file access for six agents.** Tonight's runs showed that no agent had file or shell
  tools, so the Experiment Runner could not write `run.py` and Knowledge & Memory could not write
  `merge.py` or its reports. Those agents, plus the three that read CSV files, now have an
  `os_env` block; see "File access (sandboxed)". Their prompts have a "File tools" section.

- **Literature specialist reads papers with `read_paper`.** The smoke test (run `smoke01`)
  could not verify any design because the specialist had no access to abstracts or full text.
  A first attempt declared the Bright Data MCP server in the specialist's config, but Omnigent
  drops shell secrets from agent processes, so the token never arrived (`401 Invalid API Token
  Format`, runs `smoke02` and `smoke03`). `read_paper` in `lab/tools.py` now calls Bright
  Data's `scrape_as_markdown` itself, reads the token from `.env`, and only opens allowed
  publisher pages, so the publisher rule is enforced in code. The prompt also warns that
  `offline_fallback` summaries are not published abstracts.
- **Tools that take a `dict` now accept fields.** In strict mode Omnigent made `write_record`'s
  `content` and `log_to_common_knowledge`'s `payload` reject every field; those wrappers now use
  `@tool(strict=False)`, checked by `tests/test_agent_tool_schemas.py`.
- **Prompts say how to call sub-agents and pass the run ID.** Sub-agents are called with
  `sys_session_send` (`agent` = folder name), and replies come back through `sys_read_inbox`.

- **One Common Knowledge per run.** `runs/<run_id>/common_knowledge.json` replaces the single
  `runs/common_knowledge.json` shared by all runs. A run is one whole research project across all
  its cycles; its Common Knowledge is in its zip. `CommonKnowledgeHub` and `MicroVMManager` take
  a `run_id`.
- **Secretaries log in two levels and brief the Director.** Follows #18, except that secretaries
  no longer write to the record: their `write_record` was removed. New tools
  `read_department_logs` (Leads) and `read_all_department_logs` (Director, Knowledge Lead); log
  wrappers are fixed to their own department. See "Secretary: log and brief".
- **Agent tools aligned with this design (#48, PR #49).** Search fallback cleaned (one fabricated
  paper and three papers from disallowed publishers removed) and labelled with `origin`;
  `run_experiment` replaces the template script tool for the Experiment Runner specialist;
  `compare_to_benchmark` also compares reflectance and emissivity; `pip install -e .` fixed.
- **Run output as one folder, downloaded as a zip.** The log database was set aside; everything a
  run produces is a file under `runs/<run_id>/`.
- **Seven departments, each Lead + specialist + secretary,** with decision ownership, log
  permissions, repeated-result checks and cycles.

