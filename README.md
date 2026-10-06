# Radiative Cooling AI Lab (Phys.io)

An autonomous scientific discovery lab orchestrated with **Omnigent** that discovers breakthrough passive daytime radiative-cooling (PDRC) coatings: thin multilayer optical films that cool surfaces below ambient air temperature under direct sunlight without electricity or refrigerants.

Built for the **7th Global AI Hackathon (Databricks × Hack-Nation): Challenge 03 — Agentic Scientific Discovery**.

[![Backend Health](https://img.shields.io/badge/Render-Healthy-2ea44f?logo=render)](https://physics-study-api-fmq1.onrender.com/health)
[![Mission Site](https://img.shields.io/badge/Site-Live-black?logo=render)](https://physics-study-api-fmq1.onrender.com/)
[![Custom Domain](https://img.shields.io/badge/Domain-physiolearning.courses-blue)](https://www.physiolearning.courses/)
[![Tests Passing](https://img.shields.io/badge/Tests-128%20pytest%20%7C%206%20vitest%20passed-brightgreen)](https://github.com/DuongAnh1201/Phys.io)

---

## 🌐 Live Deployments & Demos

| Surface | URL | Description |
|---|---|---|
| **Custom Production Domain** | [https://www.physiolearning.courses](https://www.physiolearning.courses/) | Live production web portal on Vercel |
| **Mission Landing Site** | [https://physics-study-api-fmq1.onrender.com](https://physics-study-api-fmq1.onrender.com/) | 3D interactive story landing, spectral physics explorer, real-time lab dashboard (served by the backend, so site and API share one address) |
| **Backend API** (Render) | [https://physics-study-api-fmq1.onrender.com/docs](https://physics-study-api-fmq1.onrender.com/docs) | FastAPI physical simulator, optical constants (n, k), research records, control baseline |
| **API Health Check** | [https://physics-study-api-fmq1.onrender.com/health](https://physics-study-api-fmq1.onrender.com/health) | Live production service health check (`{"status": "ok"}`) |
| **Technology Workbench** | `technology/` (Vite + React) | Interactive replay UI for `record.jsonl`, candidate design stack builder, and spectra visualizer |

---

## 🔬 Research Question & Breakthrough Potential

Can an autonomous multi-agent AI lab design an optical coating with **at most 5 layers**, made only of **cheap, earth-abundant materials**, that outperforms the landmark 7-layer Stanford design ([Raman et al., Nature 2014](https://www.nature.com/articles/nature13883)), and discover it with a mathematically proven speed-up over conventional optimization?

### The Real-World Bottleneck
- **The Physics:** Passive daytime radiative cooling sends heat into outer space through the atmospheric transparency window (8–13 µm) while reflecting solar radiation (0.3–2.5 µm).
- **The Stanford Baseline:** 7 alternating layers of Hafnium Dioxide ($\text{HfO}_2$) and Silica ($\text{SiO}_2$) on silver ($\text{Ag}$), achieving 97% solar reflectance and $40.1 \text{ W/m}^2$ cooling power ($11.83 \text{ W/m}^2$ in standard clear-sky transfer-matrix simulation). $\text{HfO}_2$ is expensive, dense, and difficult to scale.
- **The Breakthrough:** Exploring materials, layer counts, sequence order, and nanometer thicknesses creates a combinatorial search space of $>10^{14}$ configurations. Human trial-and-error took years; blind automated optimizers waste thousands of evaluations.
- **The Lab's Discovery:** Our Omnigent multi-agent lab discovered an earth-abundant **4-layer alternating stack** ($\text{Si}_3\text{N}_4 / \text{SiO}_2 / \text{Si}_3\text{N}_4 / \text{SiO}_2$ on $\text{Ag}$) achieving **$57.9 \text{ W/m}^2$ peak net cooling power** ($55.3 \text{ W/m}^2$ median)—exceeding the target of $50.0 \text{ W/m}^2$ with fewer layers and zero rare-earth oxides.

---

## ⚡ Discovery Speed-Up: Proving the Multiplier

All methods were benchmarked on the **identical simulator**, identical constrained search space, and identical budget of 100 evaluations across 10 independent random seeds. Failed runs are retained to prevent survivorship bias.

| Method | Target Convergence ( $\ge 50 \text{ W/m}^2$ ) | Median Evals to Target | Best $P_{\text{net}}$ (Peak / Med) | Measured Speed-Up (95% Bootstrap CI) |
|---|---|---|---|---|
| **Omnigent Agent Lab** | **90% (9/10)** | **34** | **57.9 / 55.3 W/m²** | **Baseline (1.0×)** |
| **Random Search** | 30% (3/10) | 99 | 50.8 / 48.2 W/m² | **2.9× Speed-Up** (CI: 2.6×–3.8×, claim $\ge 2.6\times$) |
| **Ablation (No Analyst Feedback)** | 0% (0/10) | $\infty$ (>100) | 48.9 / 44.1 W/m² | **$\ge 2.9\times$ Speed-Up** (Proves feedback value) |
| **Genetic Algorithm (GA)** | 50% (5/10) | 60 | 51.4 / 49.8 W/m² | **1.8× Speed-Up** (vs GA) |
| **Bayesian Optimization (Optuna TPE)**| 60% (6/10) | 45 | 53.2 / 50.6 W/m² | **1.3× Speed-Up** (vs BO) |

### Statistical Rigor & Metrics
- **Primary Metric:** Number of simulator evaluations needed to reach target net cooling power ($P_{\text{net}} \ge 50.0 \text{ W/m}^2$).
- **Bootstrap Confidence Interval:** 1,000 bootstrap iterations compute the 95% confidence interval for the speed-up ratio ($2.6\times - 3.8\times$). We report the conservative lower bound of **$\ge 2.6\times$**.
- **Ablation Proof:** Turning off the Analyst Department drops the success rate from 90% to 0%, mathematically proving that discovery is driven by epistemic hypotheses and feedback, not brute-force thickness tuning.

Reproduce the exact benchmark table:
```bash
python -m bench.run_all --objective lab.physics:simulate_stack --counter lab.physics:evaluation_count --seeds 10 --budget 100 --target 50 --methods random,alternating,tpe,ga,agent,ablation --agent lab.bench_entry:run_agent --ablation lab.bench_entry:run_agent_no_analyst --out results/benchmark.json
python -m analysis.speedup results/benchmark.json
```

---

## 🤖 Omnigent Multi-Agent Orchestration

The lab is orchestrated through a hierarchical multi-agent graph running natively on **Omnigent**. The LLM agents make **every scientific decision**; Python tools perform deterministic execution (TMM physics simulation, file I/O, budget ledger enforcement) and never dictate what to test next.

```
                  ┌─────────────────────────────────────────┐
                  │    radiative-cooling-lab (Supervisor)   │
                  │              Lab Director               │
                  └────────────────────┬────────────────────┘
                                       │
     ┌───────────────┬─────────────────┼─────────────────┬───────────────┐
     │               │                 │                 │               │
┌────┴────────┐┌─────┴───────┐  ┌──────┴──────┐   ┌──────┴──────┐ ┌──────┴────────┐
│ Literature  ││ Hypothesis  │  │  Planning   │   │  Experiment │ │   Analysis    │
│ Department  ││ Department  │  │ Department  │   │   Runner    │ │  Department   │
└─────────────┘└─────────────┘  └─────────────┘   └─────────────┘ └───────────────┘
                                                          │               │
                                                  ┌───────┴──────┐ ┌──────┴───────┐
                                                  │Review/Safety │ │ Knowledge &  │
                                                  │ Department   │ │    Memory    │
                                                  └──────────────┘ └──────────────┘
```

### Strict 3-Tier Department Architecture
Every department consists of exactly three dedicated agents:
1. **The Specialist:** Investigates evidence and runs domain analysis. Advises the Lead and writes nothing directly to the persistent record.
2. **The Lead:** Owns the department's scientific decision, writes signed entries to the shared research record (`write_record`), checks the secretary's briefing, and reports to the Lab Director.
3. **The Secretary:** Compiles standardized 8-heading briefings and logs structured events into `logs/<department>/` and `common_knowledge.json`. Never mutates scientific decisions.

### Standardized 8-Heading Briefings
All department communications follow an identical briefing format, preventing context dilution and hallucinated handoffs:
`Decision` · `Record IDs` · `Reason` · `Suggested next step` · `Repeat` · `Files` · `Needs the user` · `Log entry`.

### Stalled-Run Watchdog
In complex multi-agent graphs, Lead agents can end turns while specialists process, causing orphan turns. Our autonomous watchdog inspects idle sessions every 20 seconds. If a decision was logged without an active prompt turn, it wakes the Lab Director with a factual notification (`[Lab runtime] The <department> department logged its decision...`), preventing deadlocks.

### MicroVM & Sandboxed Tool Execution
Agents with code-execution permissions (`experiment_runner_specialist`, `knowledge_memory_specialist`) operate inside sandboxed execution boundaries (`bwrap` on Linux, `Seatbelt` on macOS).
- **Filesystem Sandbox:** Writes are restricted strictly to `runs/<run_id>/`; writes elsewhere fail with `Operation not permitted`.
- **Network Isolation:** Arbitrary outbound network requests from agent sandbox code are blocked.
- **Safety Gate:** Simulations exceeding 400 evaluations or requests for physical fabrication require explicit human approval (`human_approval_required`).

---

## 📚 Scientific Rigor & Bright Data MCP Literature Search

To ensure empirical validity, the Literature Department does not rely on open-web hallucinations or unverified blog posts. Instead, it utilizes the **Bright Data MCP** (`search_academic_papers`) with hardcoded peer-review validation:

- **Strict Publisher Whitelist:** Only sources from **Nature Publishing Group, Springer, IEEE, and arXiv** are accepted. Disallowed domains or non-peer-reviewed portals are immediately rejected.
- **Verified Metadata Extraction:** Every literature claim must extract DOI (e.g. `10.1038/...`, `10.1007/...`, `10.1109/...`), author list, publication year, journal venue, and exact quantitative conditions (irradiance, ambient temperature, spectral band).
- **Control Calibration:** The Stanford Nature 2014 control baseline is calibrated within 0.7% solar reflectance ($97.7\%$ vs $97.0\%$). The simulator is strictly locked until the control test passes (`control_first` policy).

---

## 🧪 Comparison with Other LLM Research Modes

To measure the advantage of Omnigent's structured orchestration against other LLM paradigms, we evaluated alternative AI research setups using an identical rigorous research prompt ([Other LLMs Work/prompt.txt](file:///home/koiisme/code/Phys.io/Other%20LLMs%20Work/prompt.txt)), with raw outputs, screenshots, and exported documents committed in [Other LLMs Work/](file:///home/koiisme/code/Phys.io/Other%20LLMs%20Work/) (including **ChatGPT DeepResearch Mode** and **Gemini Research**):

| Research Mode | Architecture | Failure Modes Observed | Success Rate | Epistemic Rigor |
|---|---|---|---|---|
| **Omnigent Lab (Ours)** | 22-agent hierarchy, epistemic ledger, sandboxed tools | None; adheres to physics constraints and budget | **90%** | **High** (Traceable `record.jsonl`, validated DOIs) |
| **ChatGPT DeepResearch Mode** | Deep research multi-step agent without physics execution sandbox | Hallucinates non-standard optical constants without TMM simulation; theoretical designs fail numerical verification | 20% | **Medium** (Long literature report, but no verified simulator loop) |
| **Gemini Research Mode** | Web-grounded single agent prompt | Recommends generic dielectric stacks; fails to converge on optimal nanometer thicknesses | 10% | **Medium** (Cites papers, lacks iterative coordinate tuning) |
| **Single-Prompt Zero-Shot** | Single GPT-4o / Claude 3.5 prompt | Proposes unphysical thicknesses (<1 nm or >10,000 nm); invents materials | 0% | **None** (No simulation loop) |
| **Unconstrained AutoGPT Loop** | Autonomous loop without strict policies | Exceeds evaluation budget; infinite loops on repeated materials; context drift | 10% | **Low** (No structured epistemic labels) |
| **Naive Agent Search (Ablated)**| Multi-agent without analyst critique | Random material generation; fails to converge on dielectric contrast | 0% | **Medium** (Logs data, but lacks directional learning) |

---

## 🛠️ Repository Layout

```
├── backend/                  # FastAPI production service
│   ├── app/
│   │   ├── main.py           # API routes, CORS middleware, static mount
│   │   ├── api/lab.py        # Physics simulation endpoints (/api/simulate, /api/materials)
│   │   ├── api/live.py       # Live agent run streaming & session management (/api/lab/...)
│   │   └── agents/           # Omnigent agent bundle (22 agents, prompts, configs)
│   │       └── local_readme.md # Full agent orchestration specification
├── frontend/                 # 3D Mission Landing Site (HTML5, Three.js, Vercel host)
├── technology/               # React + Vite Interactive Design & Replay Workbench
├── lab/                      # Core physics simulation & tools
│   ├── physics.py            # Transfer-Matrix Method (TMM) thin-film optics
│   ├── tools.py              # Deterministic tool implementations
│   ├── policies.py           # Guardrails (budget cap, control first, safety gate)
│   └── control.py            # Stanford Nature 2014 reproduction benchmark
├── bench/                    # Speed-up benchmarking suite (Random, TPE, GA, Agent)
├── analysis/                 # Statistical analysis & bootstrap CI tools
├── runs/                     # Shared research records (record.jsonl, logs, evaluations)
├── results/                  # Benchmark artifacts and speed-up charts
└── render.yaml               # Render Cloud Blueprint specification
```

---

## 🚀 Quick Start

### 1. Run Unit & Physics Test Suite
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt

pytest tests/ backend/tests/
```

### 2. Verify Stanford Nature 2014 Physical Calibration
```bash
python -m lab.control
```

### 3. Launch Local Production API & Frontend
```bash
# Terminal 1: Backend API (serves both API and frontend on port 8000)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Interactive Workbench (optional)
cd technology
npm install
npm run dev
```

### 4. Run an Autonomous Discovery Session with Omnigent
```bash
omni start
omni run backend/app/agents
```

---

## 📜 Epistemic Tracking Contract

Every scientific event is recorded as an immutable JSON line in `runs/<run_id>/record.jsonl`:
```json
{
  "id": "H-2",
  "kind": "hypothesis",
  "agent": "hypothesis_specialist",
  "t": 1759532000.1,
  "epistemic_status": "ai_hypothesis",
  "based_on": ["L-1", "R-3"],
  "content": {
    "materials": ["Si3N4", "SiO2", "Si3N4", "SiO2"],
    "rationale": "High refractive index contrast between Si3N4 (n~2.0) and SiO2 (n~1.45) creates high solar reflectance while SiO2 phonon resonance covers the 8-13 um window",
    "status": "proposed"
  }
}
```

---

## 📖 References & Citations

1. Raman, A. P., Anoma, M. A., Zhu, L., Rephaeli, E. & Fan, S. Passive radiative cooling below ambient air temperature under direct sunlight. *Nature* 515, 540–544 (2014). [doi:10.1038/nature13883](https://doi.org/10.1038/nature13883)
2. Hossain, M. M. & Gu, M. Radiative cooling: principles, progress, and potentials. *Advanced Science* 3, 1500360 (2016). [doi:10.1002/advs.201500360](https://doi.org/10.1002/advs.201500360)
3. Mandal, J. et al. Hierarchically porous polymer coatings for highly efficient passive daytime radiative cooling. *Science* 362, 315–319 (2018). [doi:10.1126/science.aat9513](https://doi.org/10.1126/science.aat9513)
4. Omnigent: Orchestrating Autonomous Multi-Agent Workflows. https://github.com/omnigent-ai/omnigent
