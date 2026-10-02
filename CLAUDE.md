# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Purpose

Experimental benchmark: can Jev AI make bounded operational decisions from observations? Two tiers. **Tier 1** feeds Jev synthetic server-state data (severity, action, human review, probable cause) and compares its decision with an independently defined expected outcome. **Tier 2** injects a known fault into the OpenTelemetry Demo (Docker Compose), builds an observation from the real telemetry, and scores detection, localization, diagnosis and action separately against hidden ground truth. This is **not** a production remediation system. Never add code that acts on Jev's recommendation (restart, escalate, and so on). The runners only record it. The only state-changing operations in Tier 2 are the harness's own fault inject and reset.

## Rules that must not be broken

- **Expected outcomes are hand-written** in `scenarios/definitions.py`. Never derive them from Jev or any other LLM, and never make them depend on generated values or the seed.
- **Tests never assert what real Jev answers.** Jev's output is what the experiment measures. Use `FakeClient` from `tests/helpers.py` or canned HTTP responses. Tests must pass offline with no API key.
- **Jev sees only the observations.** Never put the scenario name, expected outcome, or any hint in the request (`test_request_does_not_contain_scenario_or_expected` guards this).
- **PASS/FAIL is the operational decision only** (severity, action, human review). `probable_cause` is a diagnosis, scored separately (`DIAGNOSIS_FIELDS` in `evaluation/evaluator.py`). Do not fold it into `overall`.
- **Never invent cost.** Use a cost Jev reports, or estimate from user-set `JEV_PRICE_*` prices, else `n/a`. Do not add a default price: Jev publishes none.
- **Do not coerce or guess.** An out-of-set Jev reply is `invalid` and counts as incorrect. A failed call is `error` and is excluded from accuracy.
- **Never hard-code or invent results.** Every reported figure is computed from the run records.
- **All randomness comes from `random.Random(seed)`** inside the generator. Never use the global RNG. Logs are generated *after* metrics and services, so adding log kinds never changes a seed's metrics. Keep it that way.
- **Log lines must not leak the answer.** No scenario names, and no wording that tells Jev what to do (`test_logs_do_not_leak_scenario_or_answer`).
- **Secrets stay in `.env`** (git-ignored). Never log, store or commit `JEV_API_KEY`. `Decision` objects and result files must not contain it.
- **All Jev HTTP and API code lives in `jev/client.py`** (transport, retries, usage telemetry; Tier 1 questions and parsing too). Tier 2's question set and answer parsing live in `tier2/jev_adapter.py`, which calls `JevClient.send`. Nothing else may import HTTP or API details. API facts are in `docs/jev-api-notes.md`. Check the current docs at https://thejevai.com/docs before changing request or response handling. Do not guess parameters.

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

## Layout

```
run.py                     CLI, batch runner, per-run output, writes results/
report.py                  Markdown report from a results JSONL
run-all.sh                 venv, install, tests, key check, batch, report
scenarios/definitions.py   scenarios, expected outcomes, rationale, metric profiles
generator/server_state.py  seeded, scenario-correlated observations
generator/app_logs.py      seeded, templated application logs (called by server_state)
jev/client.py              Jev adapter (only Jev-specific code)
evaluation/evaluator.py    compare, aggregate, summary text (pure functions)
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
setup.sh health-check.sh run-experiment run-all-experiments   Tier 2 entry points
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
| Tier 2 setup | `./setup.sh --start` (clones the demo at 3.1.0, pulls, starts) |
| Tier 2 health | `./health-check.sh` |
| Tier 2 one run | `./run-experiment F003` (`list` shows IDs) |
| Tier 2 batch | `./run-all-experiments [--repeats N]` |
| Tier 2 unstick | `python -m tier2 reset-faults` |

`run.py` and `run-all.sh` need `JEV_API_KEY` in `.env`. Each run makes one real API call, so use small `--runs` while developing.

## Conventions

- Python 3.10+. Dependencies: `requests`, `python-dotenv`, `pyyaml`, `pytest`.
- Keep it simple. Do not add Kubernetes. Docker Compose is allowed **only** for the Tier 2 testbed (the OpenTelemetry Demo); Tier 1 stays Python-only. Prometheus, Jaeger, OpenSearch and Grafana are the demo's own components, queried over HTTP, not something this repo deploys.
- Changing a scenario's expected outcome or profile is a change to the experiment, not a bug fix. Update its rationale, the README table and the tests, and say so in the commit.
- Mark tasks done in `openspec/changes/jev-ops-experiment-v1/tasks.md` (Tier 1) and `openspec/changes/otel-demo-tier2/tasks.md` (Tier 2) as work completes.
- `results/*` is git-ignored except `.gitkeep`. Do not commit result files unless deliberately publishing a sample run, and label it as such.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Keep it easy to check out

Other people clone this repo and run it. Keep these working:

- `./run-all.sh --check` on a fresh clone sets up everything and passes with no key and no network access to Jev. It runs the Tier 1 and Tier 2 tests (neither needs Docker). CI runs exactly this on Python 3.10-3.13 (`.github/workflows/tests.yml`).
- New dependencies go in `requirements.txt`, pinned.
- New environment variables go in `.env.example` and the README table.
- Keep code compatible with Python 3.10.

## Status

Everything except the live runs is implemented and tested offline. Still open: the first real-Jev run (needs an API key), then marking `PLAN.md` implemented and tagging v0.1.0.
