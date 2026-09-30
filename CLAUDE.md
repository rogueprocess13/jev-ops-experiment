# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Purpose

Experimental benchmark: can Jev AI make bounded operational decisions (severity, action, human review) from synthetic server-state data? Synthetic observations go to Jev, and its decision is compared with an independently defined expected outcome. This is **not** a production remediation system. Never add code that acts on Jev's recommendation (restart, escalate, and so on). The runner only records it.

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
- **All Jev-specific code lives in `jev/client.py`.** Nothing else may import HTTP or API details. API facts are in `docs/jev-api-notes.md`. Check the current docs at https://thejevai.com/docs before changing request or response handling. Do not guess parameters.

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
```

## Commands

| Task | Command |
|---|---|
| Install | `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| Tests (offline) | `pytest` |
| One run | `python run.py --scenario degraded --seed 1234` |
| Batch | `python run.py --runs 70` (multiple of 7 = balanced) |
| Metrics only | `python run.py --runs 70 --no-logs` |
| Everything | `./run-all.sh [runs]` |
| Report | `python report.py [results/file.jsonl]` |

`run.py` and `run-all.sh` need `JEV_API_KEY` in `.env`. Each run makes one real API call, so use small `--runs` while developing.

## Conventions

- Python 3.10+. Dependencies: `requests`, `python-dotenv`, `pytest`.
- Keep it simple. Do not add Kubernetes, Prometheus, Grafana or Docker Compose.
- Changing a scenario's expected outcome or profile is a change to the experiment, not a bug fix. Update its rationale, the README table and the tests, and say so in the commit.
- Mark tasks done in `openspec/changes/jev-ops-experiment-v1/tasks.md` as work completes.
- `results/*` is git-ignored except `.gitkeep`. Do not commit result files unless deliberately publishing a sample run, and label it as such.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Keep it easy to check out

Other people clone this repo and run it. Keep these working:

- `./run-all.sh --check` on a fresh clone sets up everything and passes with no key and no network access to Jev. CI runs exactly this on Python 3.10-3.13 (`.github/workflows/tests.yml`).
- New dependencies go in `requirements.txt`, pinned.
- New environment variables go in `.env.example` and the README table.
- Keep code compatible with Python 3.10.

## Status

Everything except the live runs is implemented and tested offline. Still open: the first real-Jev run (needs an API key), then marking `PLAN.md` implemented and tagging v0.1.0.
