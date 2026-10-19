# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Purpose

Experimental benchmark: can Jev AI make bounded operational decisions from observations? Four tiers. **Tier 1** feeds Jev synthetic server-state data (severity, action, human review, probable cause) and compares its decision with an independently defined expected outcome. **Tier 2** injects a known fault into the OpenTelemetry Demo (Docker Compose), builds an observation from the real telemetry, and scores detection, localization, diagnosis and action separately against hidden ground truth. **Tier 3** injects the LF Edge AIOps group's ten Kubernetes faults into the demo on a local kind cluster, polls Jev for time-to-detect, and reports in the group's scorecard terms. **Tier 4** runs the Tier 3 faults again but carries out Jev's recommended action once per run, from a fixed allowlist, and measures recovery and MTTR. This is **not** a production remediation system. Only Tier 4 acts on an engine's recommendation, only on the local kind testbed, and only through `tier4/executor.py` (see Tier 4 rules). Tiers 1, 2 and 3 only record the recommendation; their only state-changing operations are the harness's own fault inject and reset.

## Rules that must not be broken

- **Expected outcomes are hand-written** in `scenarios/definitions.py`. Never derive them from Jev or any other LLM, and never make them depend on generated values or the seed.
- **Tests never assert what real Jev answers.** Jev's output is what the experiment measures. Use `FakeClient` from `tests/helpers.py` or canned HTTP responses. Tests must pass offline with no API key.
- **Jev sees only the observations.** Never put the scenario name, expected outcome, or any hint in the request (`test_request_does_not_contain_scenario_or_expected` guards this). The same holds for every baseline engine (`test_prompt_does_not_leak_scenario_or_expected` in `tests/test_llm.py`).
- **PASS/FAIL is the operational decision only** (severity, action, human review). `probable_cause` is a diagnosis, scored separately (`DIAGNOSIS_FIELDS` in `evaluation/evaluator.py`). Do not fold it into `overall`.
- **Never invent cost.** Use a cost the engine reports, or estimate from user-set `JEV_PRICE_*` / `CLAUDE_*_PRICE_*` prices, else `n/a`. Do not build in a default price, not even a published one.
- **Do not coerce or guess.** An out-of-set Jev reply is `invalid` and counts as incorrect. A failed call is `error` and is excluded from accuracy.
- **Never hard-code or invent results.** Every reported figure is computed from the run records.
- **All randomness comes from `random.Random(seed)`** inside the generator. Never use the global RNG. Logs are generated *after* metrics and services, so adding log kinds never changes a seed's metrics. Keep it that way.
- **Log lines must not leak the answer.** No scenario names, and no wording that tells Jev what to do (`test_logs_do_not_leak_scenario_or_answer`).
- **Secrets stay in `.env`** (git-ignored). Never log, store or commit `JEV_API_KEY`. `Decision` objects and result files must not contain it.
- **All Jev HTTP and API code lives in `jev/client.py`** (transport, retries, usage telemetry; Tier 1 questions and parsing too). Tier 2's question set and answer parsing live in `tier2/jev_adapter.py`, which calls `JevClient.send`. Baseline LLM engines (Claude API, `claude -p` fallback, Ollama) live in `llm/` and are the only other code that calls a model; they reuse `QUESTIONS` and `Decision` from `jev/client.py`, so every engine gets the same questions. The one exception is `tier3/claude_engine.py`, the Tier 3/4 Claude baseline: it asks Tier 3's questions (`tier3/questions.py`, shared with the Jev adapter) and reuses `llm/claude.py`'s settings, with no direct `jev` import. Nothing else may import HTTP or API details. API facts are in `docs/jev-api-notes.md`. Check the current docs at https://docs.typesafe.ai/api before changing request or response handling. Do not guess parameters.

## Tier 2 rules (OpenTelemetry Demo)

- **Ground truth never reaches the engine.** `tier2/observation.py` takes only collector output and scrub terms. It must not import or accept `Scenario`, `FaultSpec` or `GroundTruth` (`test_observation_module_does_not_import_scenarios`, `test_builder_signature_has_no_scenario_types`). The leak test in `tests/tier2/test_runner.py` runs every scenario through the whole path and must keep passing.
- **The scrubber is required.** The demo puts flag evaluations on spans and logs (`feature_flag` attributes, `flagd.evaluation.*` spans). Keep the scrubber, the `EXCLUDED_SERVICES` list and the leak test in step with any new telemetry you collect.
- **Four verdicts, no composite.** Detection, localization, diagnosis and action are PASS, FAIL or UNKNOWN, scored independently. Never add an overall score. UNKNOWN is only for an invalid or failed engine reply or a missing field.
- **Reset always runs.** Fault reset sits in a `finally` block. A run that does not return to baseline is `contaminated` and stops the batch.
- **Null, not invented.** A timing value that cannot be measured is `null`.
- **Only the adapter touches Jev.** `tier2/jev_adapter.py` is the only Tier 2 module that imports `jev.client`. Everything else uses `tier2/engine.py` (`AIOpsEngine`, `Decision`).
- **Faults are flagd flags only**, verified against the pinned demo version (3.1.0). Do not invent other fault mechanisms. Scenario expected outcomes are hand-written with a rationale, as in Tier 1. Note `docs/otel-demo-notes.md` when a flag behaves differently from the demo's docs.
- **Do not modify the demo checkout** (`tier2/testbed/opentelemetry-demo`, git-ignored). The pinned images come from `DEMO_VERSION=3.1.0` set as an environment variable, not from editing its `.env`. One expected exception: flagd-ui rewrites `src/flagd/demo.flagd.json` on every toggle, so `git status` there shows it modified after any run (formatting and a dropped `$schema` key only; flag values are restored). `git -C tier2/testbed/opentelemetry-demo checkout src/flagd/demo.flagd.json` restores it exactly.
- Tier 2 tests are offline: fake flag store, fake collectors, fake engine, virtual clock. Never start Docker or call Jev from a test.

## Tier 3 rules (Kubernetes faults on kind)

- **Kubernetes is allowed only for the Tier 3 testbed**: a local kind cluster created by `tier3/testbed/`. Nothing in Tier 1 or Tier 2 may depend on it.
- **Still recommendation-only.** The harness never carries out Jev's recommended action. Remediation executed, MTTR and recovery verified are reported as "not measured (recommendation only)".
- **Faults are the LF Edge harness's ten Kubernetes fault types, with their names** (`tier3/vocab.py` `FAULT_TYPES`), injected through the Kubernetes API in `tier3/faults.py`. Do not invent other fault types here. Real node faults on VMs are a separate, later change.
- **No self-describing markers.** An injected fault must not add a label, annotation, variable or object name that names the fault or the experiment. Harness objects and taints use the `jev-fault` prefix, which the scrubber always removes (`test_no_self_describing_marker`).
- **Save before you change, restore exactly.** Every inject writes the saved state to `results/tier3/.active-fault.json` first, reads the change back, and reset restores the saved state (not fixed values) and reads it back. `node_taint` only targets an application worker and only removes its own taint. The dead-man timer (`tier3/deadman.py`) and `python -m tier3 reset-faults` must keep working from the ledger alone.
- **Ground truth never reaches the engine.** `tier3/observation.py`, `tier3/collect.py` and `tier3/collectors/kube.py` must not import `tier3.scenarios` or `tier3.faults`. The observation shows effects only: no pod specs, environment variables, resource limits, NetworkPolicy objects or taint keys. The whole-path leak test in `tests/tier3/test_runner.py` covers every scenario and every poll.
- **Polling is scored once.** In `poll` mode the first poll that reports an incident is scored (else the last poll); every poll is stored. On the healthy control every detecting poll is a false-positive poll.
- **Only the adapter touches Jev.** `tier3/jev_adapter.py` is the only Tier 3 module that imports `jev.client` (`test_only_the_adapter_imports_jev_client`). The question set lives in `tier3/questions.py` so the Claude baseline (`tier3/claude_engine.py`, `--engine claude-opus` on `python -m tier3` and `python -m tier4`) asks exactly the same questions; every run record says which engine answered (`engine`).
- **No Kubernetes Python client.** The API is reached with `requests` (`tier3/collectors/kube.py`); pod exec uses `kubectl`. Versions are pinned in `tier3/testbed/pins.env`; facts verified on the cluster go in `docs/k8s-testbed-notes.md`.
- Tier 3 tests are offline: `FakeKube`, fake collectors, fake engine, virtual clock. Never start kind or Docker, or call Jev, from a test.

## Tier 4 rules (closed-loop remediation on kind)

- **Only Tier 4 acts, only through the allowlist.** `tier4/executor.py` is the only code that carries out an engine's recommendation: `scale_up` (replicas to baseline if below it, else one more, never above 3), `restart_service` (rollout restart), `rollback_change` (`kubectl rollout undo` from the cluster's own revision history). `investigate`, `escalate` and `no_action` do nothing. Never add an operation, a resource kind, a namespace or a parameter the engine can choose.
- **Deployments in the demo namespace only.** Never nodes, Services, NetworkPolicies, StatefulSets, the load generator or the observability stack (`is_infra`). Anything else is `not_executable` with a reason, and nothing changes.
- **One action per run, after the last poll.** The engine is not asked again after acting, so nothing from the executor or the recovery check can reach a request. The whole-path leak test in `tests/tier4/test_runner.py` covers every scenario.
- **Rollback never reads the harness's state.** `rollback_change` uses only the cluster's rollout history, never the fault ledger, saved state or scenario.
- **Save before act, restore exactly, in reverse order.** The target's replicas and pod template go to an `action` entry in the Tier 3 ledger before acting and are read back after. Reset restores the action first, then the fault. `python -m tier3 reset-faults`, `python -m tier4 reset-faults` and the dead-man timer handle a ledger with an action.
- **Isolation.** Only `tier4/runner.py` and `tier4/cli.py` import the executor; nothing outside `tier4/` imports Tier 4; no Tier 4 module imports `jev.client` (`tests/tier4/test_isolation.py`). Tier 4 hooks into Tier 3's runner (`Deps.after_scored`, `Deps.on_reset`); with them unset, Tier 3 stays recommendation-only.
- **MTTR in the group's terms.** `mttr_seconds` is fault to remediation written; `mttr_verified_seconds` is fault to the start of the final run of passing service-level checks (at least 60 s, lasting to the end of the 360 s watch), for `recovered_by_action` only. A system that recovers on its own is `recovered_without_action`, never Jev's MTTR. Null, not invented.
- Tier 4 tests are offline: `FakeKube`, fake undo, fake engine, virtual clock. Never call `kubectl`, kind or Jev from a test.

## Layout

```
run.py                     CLI, batch runner, per-run output, writes results/
report.py                  Markdown report from a results JSONL
run-all.sh                 venv, install, tests, key check, batch, report
scenarios/definitions.py   scenarios, expected outcomes, rationale, metric profiles
generator/server_state.py  seeded, scenario-correlated observations
generator/app_logs.py      seeded, templated application logs (called by server_state)
jev/client.py              Jev adapter (only Jev-specific code)
llm/                       baseline engines: prompt.py (shared questions), claude.py, ollama.py, engines.py
evaluation/evaluator.py    compare, aggregate, summary text (pure functions)
evaluation/metrics.py      F1, detection, latency percentiles, reliability, cost (pure); metrics_report.py renders them
tests/                     offline unit tests
docs/jev-api-notes.md      Jev API notes with sources
openspec/                  proposal, design, specs, tasks for the project
tier2/                     Tier 2 (OpenTelemetry Demo)
  scenarios/*.yaml         one experiment per file, with hidden ground truth
  scenarios.py vocab.py    scenario model, loader, Tier 2 vocabularies
  faults.py workload.py    flagd injection and reset, Locust control
  collectors/ collect.py   Prometheus, Jaeger, OpenSearch -> Telemetry
  observation.py           Observation builder, caps, byte budget, scrubber
  engine.py jev_adapter.py AIOpsEngine + Decision; the Jev adapter
  evaluate.py              pure per-dimension verdicts, aggregates, timing
  runner.py cli.py         lifecycle, batch, command line
  testbed/                 setup.sh, stop.sh, demo checkout (git-ignored)
tests/tier2/               offline Tier 2 tests
tier3/                     Tier 3 (LF Edge Kubernetes faults on kind)
  scenarios/K*.yaml vocab.py scenarios.py   catalogue K000-K010, vocabularies, loader
  faults.py deadman.py     ten fault types, ledger, exact restore; dead-man timer
  collectors/kube.py collect.py   thin Kubernetes API client; Tier 2 collectors + cluster state
  observation.py manifest.py      observation builder and scrubber; manifestation and recovery checks
  engine.py jev_adapter.py AIOpsEngine + Decision; the Jev adapter
  questions.py claude_engine.py   shared question set; Claude Opus baseline engine (API or claude -p)
  runner.py evaluate.py report.py cli.py   lifecycle and polling; verdicts; scorecard and exports
  testbed/                 pins.env, kind.yaml, values/, create/install/health/stop/start/delete/rebalance scripts, probe_fault.py
tests/tier3/               offline Tier 3 tests
tier4/                     Tier 4 (closed-loop remediation on the Tier 3 cluster)
  executor.py recovery.py  the allowlist and save/restore; service-level recovery, MTTR
  runner.py report.py cli.py   Tier 3 lifecycle plus one action; scorecard and export
tests/tier4/               offline Tier 4 tests
setup.sh health-check.sh run-experiment run-all-experiments   Tier 2 entry points
setup-k8s.sh health-check-k8s.sh run-k8s-experiment run-all-k8s-experiments   Tier 3 entry points
run-remediation-experiment run-all-remediation-experiments   Tier 4 entry points (Tier 3 setup and health)
```

## Commands

| Task | Command |
|---|---|
| Install | `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| Tests (offline) | `pytest` |
| One run | `python run.py --scenario degraded --seed 1234` |
| Batch | `python run.py --runs 70` (multiple of 7 = balanced) |
| Metrics only | `python run.py --runs 70 --no-logs` |
| Everything (Tier 1) | `./run-all.sh [runs]` |
| Report | `python report.py [results/file.jsonl]` |
| Baseline LLM batch | `python run.py --runs 70 --seed 1000 --engine claude-sonnet` (or `claude-opus`, `ollama:qwen3:8b`) |
| Compare engines | `python report.py --compare A.jsonl B.jsonl ...` |
| Metrics (F1, p95, ...) | `python report.py --metrics A.jsonl [B.jsonl ...]` |
| Tier 2 setup | `./setup.sh --start` (clones the demo at 3.1.0, pulls, starts) |
| Tier 2 health | `./health-check.sh` |
| Tier 2 one run | `./run-experiment F003` (`list` shows IDs) |
| Tier 2 batch | `./run-all-experiments [--repeats N]` |
| Tier 2 unstick | `python -m tier2 reset-faults` |
| Tier 3 setup | `./setup-k8s.sh` (pre-check, kind cluster, demo chart, health) |
| Tier 3 health | `./health-check-k8s.sh` |
| Tier 3 one run | `./run-k8s-experiment K001` (`list` shows IDs; `--mode single` for one call) |
| Tier 3 batch | `./run-all-k8s-experiments [--repeats N]`, or `... K000 --repeats 10` for the control |
| Tier 3 unstick | `python -m tier3 reset-faults` |
| Tier 3 scorecard | `python -m tier3 scorecard results/tier3/<run-id>` (also `export-lfedge`, `export-reasoning`) |
| Tier 4 one run | `./run-remediation-experiment K001` |
| Tier 4 batch | `./run-all-remediation-experiments [--repeats N]` |
| Tier 3/4 Opus baseline | add `--engine claude-opus` to `run`/`batch` (API with `ANTHROPIC_API_KEY`, else `claude -p`) |
| Tier 4 scorecard | `python -m tier4 scorecard results/tier4/<run-id>` (also `export-lfedge`) |

`run.py` and `run-all.sh` need `JEV_API_KEY` in `.env` for the default `jev` engine. Each run makes one real model call, so use small `--runs` while developing.

## Conventions

- Python 3.10+. Dependencies: `requests`, `python-dotenv`, `pyyaml`, `pytest`, `anthropic` (baseline engines only).
- Keep it simple. Docker Compose is allowed **only** for the Tier 2 testbed and Kubernetes (a local kind cluster) **only** for the Tier 3 testbed (which Tier 4 reuses); Tier 1 stays Python-only. Prometheus, Jaeger, OpenSearch and Grafana are the demo's own components, queried over HTTP, not something this repo deploys.
- Changing a scenario's expected outcome or profile is a change to the experiment, not a bug fix. Update its rationale, the README table and the tests, and say so in the commit.
- Mark tasks done in `openspec/changes/jev-ops-experiment-v1/tasks.md` (Tier 1), `openspec/changes/otel-demo-tier2/tasks.md` (Tier 2), `openspec/changes/k8s-faults-tier3/tasks.md` (Tier 3) and `openspec/changes/k8s-remediation-tier4/tasks.md` (Tier 4) as work completes.
- `results/*` is git-ignored except `.gitkeep`. Do not commit result files unless deliberately publishing a sample run, and label it as such.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Keep it easy to check out

Other people clone this repo and run it. Keep these working:

- `./run-all.sh --check` on a fresh clone sets up everything and passes with no key and no network access to Jev. It runs the Tier 1 to Tier 4 tests (none needs Docker or a cluster). CI runs exactly this on Python 3.10-3.13 (`.github/workflows/tests.yml`).
- New dependencies go in `requirements.txt`, pinned.
- New environment variables go in `.env.example` and the README table.
- Keep code compatible with Python 3.10.

## Status

v0.1.0 (2026-10-19): all four tiers implemented, tested offline and run live against real Jev. Tier 1: `docs/results-2026-10-05-tier1-baselines.md` and `docs/results-2026-10-18-tier1-jev.md`; `PLAN.md` is marked implemented. Tier 2: `docs/results-2026-10-12-tier2-jev.md`. Tier 3 is done: every fault verified on the kind cluster (`docs/k8s-testbed-notes.md`) and the first full live Jev batch written up in `docs/results-2026-10-18-tier3-jev.md` (2026-10-18). Tier 4 is done: the live Jev batch in `docs/results-2026-10-19-tier4-jev.md` and the Jev vs Claude Opus comparison (Opus through `claude -p`) in `docs/results-2026-10-19-tier4-jev-vs-opus.md` (2026-10-19). The cluster is stopped, not deleted; `tier3/testbed/start.sh` brings it back.
