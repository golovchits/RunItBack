# RunItBack

**Diagnose ML paper reproducibility before you burn a single GPU hour.**

RunItBack takes a machine-learning paper and its companion code repository and returns a diagnostic report telling you whether the code actually implements what the paper claims — with claim-by-claim verification, severity-ranked findings, and suggested fixes as unified diffs. It is a tool for the kind of reproduction work where the failure modes are subtle and the surface area is large: four Claude Opus 4.7 agents running on Claude Managed Agents do the close reading, auditing, runtime validation, and cross-checking that one researcher would otherwise spend a week on. The diagnosis arrives in minutes; the experiments you actually want to run start sooner.

| | |
|---|---|
| **Demo video** | https://drive.google.com/file/d/1c0yJFpPJjAiKCjmJxmjYwY-jLp1eLEur/view?usp=sharing|

---

## Why this exists

**Even top ML PhDs cap out at a 41.4% replication score after 48 hours of dedicated effort per paper** (PaperBench, OpenAI, 2025). Manually checking a single replication attempt can take tens of expert hours. Full reproducibility is, on a per-paper basis, prohibitively expensive — and the gap is not about hardware, it is not about luck, and it is very rarely about needing more compute. It is about **augmentation leaks, train-test overlap, config drift between paper and code, silent broadcasting bugs, missing seed discipline, evaluation metrics that don't match the one the paper reported, and undocumented heuristics that show up in the training loop but never make it into the method section**.

Anyone who has tried to reproduce a baseline knows the shape of the problem: you spend a week setting up the environment, another week trying to match the preprocessing, you launch a full training run, and after two days on an A100 you get a number that is four points below the reported accuracy. Now you have to debug backwards — was it the data, the optimizer, the loss, the eval script? The compute was never the bottleneck. **The diagnosis was.**

RunItBack is built on a single observation: **most of these failures can be caught by reading the code against the paper, without ever retraining.** An augmentation leak is a function call order. A train-test overlap is a `glob` away. A reported-vs-implemented metric mismatch is a `grep`. A missing `model.eval()` before validation is a static check. The work is well-defined; what was missing was an auditor patient enough, meticulous enough, and cross-referenced enough to do all of it on a single paper-and-repo pair, in under an hour, every time.

That is what RunItBack is.

> The full reproducibility-failure taxonomy this tool operationalizes — data contamination, environment decay, silent correctness bugs, hardware non-determinism, state-management pitfalls, evaluation-metric drift — draws on a body of literature on the ML reproducibility crisis (Kapoor & Narayanan; the PaperBench evaluation; framework-bug taxonomies from empirical SE research). The taxonomy is encoded directly inside the Code & Data Auditor's system prompt — see `backend/agents/prompts/code_auditor.md`.

---

## What it does

Given a paper (arXiv URL, direct PDF URL, upload, or raw text) and a code repo (GitHub URL or local path), RunItBack produces a `DiagnosticReport` with:

- **Verdict** — one of `REPRODUCIBLE`, `LIKELY_REPRODUCIBLE`, `QUESTIONABLE`, `NOT_REPRODUCIBLE`, `INCONCLUSIVE`, with a confidence score.
- **Executive summary** — a short, Claude-written narrative a researcher can paste into a Slack message and decide from.
- **Claim-by-claim verification table** — every numeric claim, every training-config claim, every architecture claim pulled out of the paper, mapped to the exact file and line range in the repo that implements it (or doesn't), with a `confirmed / refuted / not_found / partial` status.
- **Findings**, severity-sorted (`critical`, `high`, `medium`, `low`, `info`), each with: file path, line range, the code snippet, a "paper says X / code does Y" comparison, why it matters, and — when the fix is obvious — a suggested change as a unified diff.
- **Configuration diff table** — paper-reported vs code-resolved hyperparameters, mismatches highlighted.
- **Data EDA summary** (when a data path is provided) — sample counts, split distribution, class balance, leakage red flags.
- **Recommendations**, prioritized.
- **Unresolved disagreements** — where the agents could not reach ≥ 2-agent consensus, exposed honestly instead of silently dropped.

The report is a single JSON document, rendered live in the frontend as an interactive pipeline diagram, a verdict banner, a sortable findings table, and a code viewer that jumps to the lines a finding cites.

---

## How it works

RunItBack is a **prompt chain with a verification side-car**. Four Opus 4.7 agents, each with a narrow, well-defined contract, run sequentially and pass structured JSON forward:

```
                   ┌──────────────────────────────────────────┐
User ──▶ React UI  │  Browser                                  │
         │         │                                           │
   POST /audit     │                                           │
         ▼         │                                           │
┌──────────────────┐  SSE progress   ┌──────────────────────┐  │
│ FastAPI backend  │ ◀──────────────▶│  Pipeline            │  │
│                  │                 │                      │  │
│  - fetch arXiv   │   creates 4     │  ┌────────────────┐  │  │
│  - clone repo    │  sessions ──────┼─▶│ Paper Analyst  │──┼──┼──▶ claims.json
│  - build repo    │                 │  └────────────────┘  │  │
│    manifest      │                 │  ┌────────────────┐  │  │
│  - SQLite +      │                 │  │ Code & Data    │──┼──┼──▶ findings.json
│    JSONL event   │                 │  │ Auditor        │  │  │
│    log           │                 │  └────────────────┘  │  │
│                  │                 │  ┌────────────────┐  │  │
│                  │                 │  │ Validator      │──┼──┼──▶ validation.json
│                  │                 │  └────────────────┘  │  │
│                  │                 │  ┌────────────────┐  │  │
│                  │                 │  │ Reviewer       │──┼──┼──▶ report.json
│                  │                 │  └────────────────┘  │  │
└──────────────────┘                 └──────────────────────┘  │
                                   Claude Managed Agents (cloud)
```

### The four agents

1. **Paper Analyst.** Input: the PDF. Output: a `PaperClaims` JSON — every metric, every dataset, every architecture, every hyperparameter, every evaluation-protocol detail, every ablation, each with a citation (page + section + verbatim quote) and an extraction-confidence score. It also emits red flags for ambiguous protocols, hardcoded thresholds, and undocumented heuristics that will bite reproducibility but aren't themselves testable claims. **It reads no code.** Isolation here keeps the claim extraction honest — no leakage from what the code "happens to do" into what the paper "says it does".

2. **Code & Data Auditor.** Input: the `PaperClaims` JSON plus the cloned repo. Output: `AuditFindings` JSON — every place the code diverges from the paper, every place the code does something the paper never mentioned, every place a known reproducibility footgun is present. This is the agent that carries the full failure taxonomy in its system prompt: preprocessing-before-split leakage, SMOTE-before-split leakage, multi-test contamination, temporal contamination, target leakage, tensor-broadcasting silent bugs, train-eval augmentation asymmetry, missing `model.eval()`, non-deterministic CUDA flags, checkpoint-state omission, distributed-sampler `set_epoch` misses, and the rest. It uses `bash` / `grep` / `glob` / `read` aggressively (cheap) and reads full files sparingly (expensive).

3. **Validator.** Input: the findings, plus a sandboxed checkout of the repo. Output: per-finding `confirmed / denied / inconclusive / unvalidated` verdicts with runtime evidence — commands run, stdout/stderr captured, exit codes recorded. It also executes a standing battery of proactive checks (`pip install -r requirements.txt --dry-run`, import smoke test, eval dry-run). Separating this from the Auditor keeps the Auditor's reasoning context clean of runtime noise (pip install transcripts, stack traces) and applies the only reliable tiebreaker in software: _did it actually run_.

4. **Reviewer.** Input: all three prior JSON artifacts plus the repo manifest. Output: the final `DiagnosticReport`. It enforces the **≥ 2-agent agreement rule** — no finding reaches the user unless at least two of {Auditor, Validator, independent Reviewer read} support it — and exposes genuine disagreements as `unresolved_disagreements` instead of hiding them. It computes the verdict, the executive summary, the claim-verification table, and the prioritized recommendation list.

Sessions run sequentially because each one needs the prior one's output. The orchestrator streams every tool call, every thinking block, and every intermediate message back to the frontend over SSE — the UI is a live feed of the agents' work, not a spinner with a final result.

---

## How Opus 4.7 is used

Four of Opus 4.7's capabilities are load-bearing:

### 1. Native multimodal PDF ingestion — Paper Analyst

The Paper Analyst does not use `pdftotext`. It does not use `pdf2image`. It does not use OCR. It does not use an external PDF-parsing library. The orchestrator reads the paper's raw bytes from disk, base64-encodes them, and hands them to Opus 4.7 as a **`document` content block** with `media_type: application/pdf`:

```python
# backend/orchestrator/user_messages.py
pdf_bytes = paper_path.read_bytes()
b64 = base64.b64encode(pdf_bytes).decode("ascii")
return [
    {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": b64,
        },
    },
    {"type": "text", "text": "Extract all verifiable claims…"},
]
```

Opus 4.7 reads the PDF natively — **text, tables, figures, and equations together, in one pass, with layout preserved**. This matters enormously for ML papers. Metric cells live inside tables with merged headers. Hyperparameter grids live inside appendix tables with strikethrough rows. Training schedules are described in one paragraph and quantified in a figure caption three pages later. Loss functions appear as LaTeX equations whose variable names only make sense in the context of the preceding paragraph. A text-only pipeline mangles all of this. Opus 4.7's vision + text fusion reads the whole page the way a human reader does, and the accuracy difference in extracted claims is not small — it is the difference between a claim table with 50 entries and one with 12.

### 2. Long-horizon reasoning across a rich taxonomy — Code & Data Auditor

The Auditor carries **a full ML reproducibility-failure taxonomy inside its system prompt** — hundreds of lines of categorized failure modes, each with diagnostic signatures, static-analysis hints, and severity guidance. On every single file it reads, it is simultaneously asking "does this code exhibit pattern X, or Y, or Z, or …" for dozens of patterns at once, while also cross-referencing against the paper's claims, while also preserving enough context to cite line numbers accurately. Smaller models lose the taxonomy under code-token pressure and start hallucinating categories; Opus 4.7 keeps the whole checklist in working memory across a 60-turn tool-using session and produces findings with citations that survive human review.

### 3. Structured JSON under adversarial conditions — every agent

Each agent's deliverable is a strict Pydantic-validated JSON object with a few dozen required fields, discriminated unions, claim-ID disciplines, and enum values. Every prompt ends with a "FIELD-NAME DISCIPLINE" checklist listing the exact drifts that are known to slip past weaker models (`num_samples_total` vs `n_samples`, `extraction_confidence` as a top-level field vs buried inside a sub-object, lists of objects vs lists of bare strings). Opus 4.7 handles this schema discipline as a first-class output constraint — there is still a defensive `normalize_*` pass on top for safety, but the base rate of schema-clean emissions is what makes the four-agent chain economical.

### 4. Honest uncertainty — Reviewer

The Reviewer's job is the hardest one in the pipeline: when the Auditor says "X is broken" with high confidence, the Validator says "X ran fine" with high confidence, and both have evidence, the Reviewer has to surface the disagreement instead of picking a side. Opus 4.7's tendency to **actually report uncertainty** rather than smoothing it into a confident single answer is what makes the `unresolved_disagreements` section of the report trustworthy. Every finding in the final report carries a confidence score and a provenance trail; when ≥ 2-agent agreement can't be reached, the user sees the conflict and the evidence for both positions rather than a hallucinated consensus.

---

## How Claude Managed Agents is used

The entire agent infrastructure — the sandbox, the toolchain, the session lifecycle, the event streaming — is handled by **Claude Managed Agents**. Zero Dockerfiles written for the primary path. No tool router built. No retry loop built around tool-use turns. Managed Agents was given the "hands" and wrote only the "brain": prompts, orchestration, and schema.

Specifically:

- **Each of the four roles is a persistent Managed Agent** created once via `scripts/create_agents.py` and identified by a durable `agent_id`. Creation uses `client.beta.agents.create(model={"id": "claude-opus-4-7"}, system=…, tools=[…])`. The four agent IDs land in `.env`; the runtime looks them up from the registry.

- **A single shared cloud Environment** is provisioned once via `scripts/create_environment.py`. Each audit-phase spins up a fresh **Session** against that environment with `client.beta.sessions.create(agent=agent_id, environment_id=…)` — so the Paper Analyst, Auditor, Validator, and Reviewer each get a clean sandbox per audit, with zero cross-contamination from the previous run.

- **Tool provisioning is declarative.** Every agent receives the pre-built toolset (`agent_toolset_20260401` — `bash`, `read`, `write`, `edit`, `grep`, `glob`, `web_fetch`, `web_search`) and each agent's system prompt lists the exact disables for its role:

  ```python
  # scripts/create_agents.py
  TOOL_CONFIGS = {
      "paper_analyst": {"configs": [{"name": "web_search", "enabled": False},
                                    {"name": "edit", "enabled": False}]},
      "code_auditor": {"configs": [{"name": "web_search", "enabled": False}]},
      "validator":    {"configs": [{"name": "web_fetch",  "enabled": False},
                                   {"name": "web_search", "enabled": False}]},
      "reviewer":     {"configs": [{"name": "write", "enabled": False},
                                   {"name": "edit",  "enabled": False},
                                   {"name": "web_fetch",  "enabled": False},
                                   {"name": "web_search", "enabled": False}]},
  }
  ```

  The Paper Analyst can't edit files. The Reviewer can't edit files _or_ fetch URLs — it has to reason over the inline JSON. The Validator can't browse the web — if a package won't install, it has to say so in its verdict, not go hunting.

- **Event streaming is first-class.** The orchestrator subscribes to `client.beta.sessions.events.stream(session.id)` and translates every `agent.thinking`, `agent.message`, `agent.tool_use`, `agent.tool_result`, and `span.model_request_end` event into a typed SSE event that the React frontend renders in real time. The user sees the agent's thoughts, the commands it runs, the files it opens, and the tokens it burns — live. Cost telemetry (`usage_input`, `usage_output`, `usage_cache_creation`, `usage_cache_read`) is aggregated per session and returned in the final report.

- **The Messages-API fallback exists but is not the happy path.** `backend/agents/messages_loop.py` implements a custom tool-use loop against a local Docker sandbox if `USE_FALLBACK=true` is set in `.env` — useful for offline dev, but the Managed Agents path is the one demoed, tested against, and shipped. The fallback was written exactly because it _wasn't_ needed for the normal path — a point worth making: Managed Agents was sufficient for production-grade reliability out of the box.

**Why this mattered for a 5-day hackathon:** building a four-agent multi-tool sandboxed pipeline in five days is not possible without a platform that hands you the sandbox, the tools, the session isolation, and the streaming for free. Managed Agents provided all of that on day one, leaving the time to spend on the part that was actually hard: the prompts, the cross-check rules, and the taxonomy.

---

## Local setup

### Prerequisites

- **Python 3.12** (the project declares `requires-python = ">=3.12"`).
- **[uv](https://github.com/astral-sh/uv)** — installs in 5 seconds: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Node.js 20+** and **npm** (for the frontend).
- **Git** (for cloning repos the backend audits).
- **An Anthropic API key** with Managed Agents beta access.

### 1. Clone

```sh
git clone https://github.com/golovchits/RunItBack.git
cd runitback
```

### 2. Backend install

```sh
make install           # equivalent to: uv sync --all-extras
```

This creates `.venv/`, resolves `pyproject.toml` against `uv.lock`, and installs the full dev toolchain (`pytest`, `ruff`, `mypy`).

### 3. Configure the API key

```sh
cp .env.example .env
# open .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
```

The remaining variables (`AGENT_ID_*`, `MANAGED_ENVIRONMENT_ID`) will be populated by the provisioning scripts below.

### 4. Provision the cloud sandbox (one time)

```sh
make create-env
```

Runs `scripts/create_environment.py`, which calls `client.beta.environments.create(...)` and prints a line to paste into `.env`:

```
MANAGED_ENVIRONMENT_ID=env_01...
```

### 5. Provision the four agents (one time)

```sh
make create-agents
```

Runs `scripts/create_agents.py`, which reads each agent's system prompt from `backend/agents/prompts/*.md`, registers the four agents against `claude-opus-4-7`, and prints four lines to paste into `.env`:

```
AGENT_ID_PAPER_ANALYST=agent_011Ca...
AGENT_ID_CODE_AUDITOR=agent_011Ca...
AGENT_ID_VALIDATOR=agent_011Ca...
AGENT_ID_REVIEWER=agent_011Ca...
```

> Both provisioning scripts are safe to re-run but each invocation creates a fresh resource rather than updating in place — rerun only when prompts change, and replace the IDs in `.env` afterwards.

### 6. Start the backend

```sh
make dev
```

Uvicorn listens on `http://localhost:8000`. Sanity-check:

```sh
curl http://localhost:8000/api/v1/readyz
# → {"ready": true, "managed_agents": true, "environment_id": "env_...", ...}
```

If `ready` is `false`, the response tells you which env var is missing.

### 7. Start the frontend

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Vite listens on `http://localhost:5173` and proxies `/api/*` to the backend on `:8000`.

### 8. Run your first audit

Open `http://localhost:5173` in a browser. Paste:

- **Paper**: `https://arxiv.org/pdf/2504.01848` (only arXiv `/pdf/` URLs are supported — `/abs/` and `/html/` variants are rejected)
- **Code**: `https://github.com/<any>/<repo>` (shallow-cloned into `runtime/audits/<id>/repo/`)
- **Data**: leave blank (code-only audit) or supply an absolute local path

Click **Run audit** and watch the pipeline page stream the four agents' work in real time. A typical audit finishes in 3–8 minutes depending on paper length and repo size; the final report opens automatically.

---

## API

Full API contracts live in `backend/api/`. Core routes:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/audit` | Start an audit (JSON body: `paper`, `code`, `data`). Returns `{audit_id}`. |
| `POST` | `/api/v1/audit/upload-pdf` | Upload a PDF for later reference. Returns `{upload_id}`. |
| `GET`  | `/api/v1/audit/{id}/status` | Current phase + running totals. |
| `GET`  | `/api/v1/audit/{id}/stream` | Server-Sent Events: agent started/thinking/message/tool_use/tool_result/finished, audit status, report.partial, report.final. |
| `GET`  | `/api/v1/audit/{id}/report` | Final `DiagnosticReport` JSON. |
| `GET`  | `/api/v1/audit/{id}/file` | Read any file in the cloned repo (sandboxed to the audit's checkout). |
| `DELETE` | `/api/v1/audit/{id}` | Cancel an in-flight audit. |
| `GET`  | `/api/v1/healthz` | Liveness. |
| `GET`  | `/api/v1/readyz` | Readiness — includes Managed Agents provisioning status. |

---

## Development

```sh
make test        # pytest against backend/
make fmt         # ruff format .
make lint        # ruff check + mypy backend
make clean       # remove .venv and all caches
```

Frontend:

```sh
cd frontend
npm run build    # production build → frontend/dist/
npm run lint     # eslint
npx tsc --noEmit # type-check
```

---

## Project layout

```
runitback/
├── backend/                    # FastAPI app + orchestrator + 4 agents
│   ├── main.py                 # app, middleware, CORS, lifespan
│   ├── config.py               # pydantic-settings
│   ├── api/                    # POST /audit, GET /stream, /report, /file, upload
│   ├── schemas/                # Pydantic: inputs, claims, findings, validation, report, events
│   ├── orchestrator/           # pipeline, normalizer, event bus, SQLite + JSONL store
│   ├── agents/                 # Managed Agents runner, prompts, output parsers
│   │   └── prompts/            # system prompts (paper_analyst, code_auditor, validator, reviewer)
│   ├── tools/                  # arXiv, HTTP fetch, GitHub clone, repo index, data walker
│   ├── fallback_runtime/       # Docker sandbox — Messages-API fallback only
│   └── util/                   # diff, hashing, timebox, sanitize
├── frontend/                   # React + Vite + Tailwind
│   └── src/
│       ├── screens/            # Input, LiveAudit, Report
│       ├── components/         # VerdictBanner, FindingsTable, CodeViewer, PipelineDiagram, …
│       ├── state/              # zustand stores
│       └── api/                # typed fetch wrapper + SSE client
├── scripts/                    # create_environment.py, create_agents.py, smoke_audit.py, …
├── tests/                      # pytest against backend/
├── pyproject.toml              # runitback package + dev deps
├── uv.lock
├── Makefile                    # install / dev / test / fmt / lint / create-agents / create-env
└── LICENSE                     # MIT
```

---

## Known limitations

### Output-distribution drift on multi-category JSON

Every agent emits structured JSON with several required category lists (claims by type, findings by stage, validations by finding-id, recommendations by priority). When one category is unusually dense in the input — a paper with 50 metric rows, a repo whose code-quality issues dwarf its evaluation issues — the model's *output* budget can over-allocate to that bucket and under-populate the others. This is an output-balance issue, not a context-loss issue: the taxonomy stays active in working memory, but the long tail gets compressed at write time. Two deterministic post-passes in `backend/agents/output_parsers.py` mitigate this on the hot path — `normalize_*` coerces synonym-drift keys before schema validation, and `_link_claim_verifications` runs a structural claim↔finding join when the Reviewer leaves `linked_finding_ids` empty. The latest production audit shows the mitigations holding: 28 auditor findings spread across the full taxonomy, every one validated, 88% of claim verifications linked to findings, and three validator-promoted findings merged cleanly into the final report. When the failure mode does surface, it is graceful — fewer entries, never wrong entries — and a re-run usually rebalances them.

---

## License

MIT. See `LICENSE`.

---

## Acknowledgements

Built during **Built with Opus 4.7: a Claude Code Hackathon** (April 21–26, 2026).

- Claude Opus 4.7 — the model doing the actual work.
- Claude Managed Agents — the sandbox, toolchain, session lifecycle, and event streaming that didn't need to be built.
