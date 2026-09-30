# jev-ops-experiment

This project tests whether Jev AI can make bounded operational decisions from synthetic server-state information. Server conditions are generated from predefined scenarios with independently defined expected outcomes. Jev receives the observations and selects from a bounded set of operational decisions. The experiment then compares Jev's decisions against the expected outcomes and records accuracy and confidence.

> **This is an experimental benchmark, not a production autonomous remediation system.** It only generates data, asks Jev for a decision, and records the answer. It never restarts, changes or escalates anything.

Prepared for discussion in the LF Edge AIOps forum.

[![tests](https://github.com/rogueprocess13/jev-ops-experiment/actions/workflows/tests.yml/badge.svg)](https://github.com/rogueprocess13/jev-ops-experiment/actions/workflows/tests.yml)

## Quick start

You need Python 3.10 or newer and git. Linux and macOS work as shown. On Windows, use WSL or see [Manual setup](#manual-setup).

```bash
git clone https://github.com/rogueprocess13/jev-ops-experiment.git
cd jev-ops-experiment
./run-all.sh --check      # sets up .venv, installs, runs the tests. No key, no API calls.
```

Then get a Jev API key at <https://thejevai.com/settings/apikeys>, put it in `.env` (the check created it for you):

```bash
JEV_API_KEY=your-real-key
```

and run:

```bash
./run-all.sh 7            # one run per scenario: 7 API calls
./run-all.sh              # the full 70-run batch
```

The report is printed at the end and saved in `results/`.

## How it works

```
Known scenario -> Known server state -> Jev -> Decision -> Compare with independent expected outcome
```

- **Scenarios** (`scenarios/definitions.py`): `healthy`, `degraded`, `critical`, `ambiguous`, `contradictory`, `hung_worker`, `log_only_errors`. Each has an expected outcome written by hand in code, with a written rationale. No LLM is used to produce it. It does not depend on the generated numbers or the seed.
- **Generator** (`generator/server_state.py`): builds CPU, memory, disk, load, network errors, application error rate, API latency, service statuses and recent restarts/events. Metrics are derived from a shared stress level for the scenario, so they move together. `contradictory` deliberately breaks this, with two patterns: quiet hosts with a failing service, and a busy host with no symptoms.
- **Application logs** (`generator/app_logs.py`): each run also includes 15 minutes of application log lines (INFO, WARN, ERROR, FATAL) that match the scenario and name the affected service. They are built from fixed templates, so the seed fixes them too. In `contradictory`, the logs can contradict the metrics as well (a service logs crashes and "health check ok").
- **Jev adapter** (`jev/client.py`): the only module that talks to Jev. Jev is asked three typed questions in one request:
  - severity: `normal`, `degraded`, `high`, `critical`
  - action: `observe`, `investigate`, `restart`, `escalate`
  - human review required: `yes` or `no`
  - probable cause: `none`, `resource_exhaustion`, `dependency_failure`, `application_bug`, `configuration`, `network`, `unknown`
- **Evaluator** (`evaluation/evaluator.py`): compares each field, then aggregates accuracy, confidence and latency. Every figure is calculated from the real results.

Jev sees only the server observations. It never sees the scenario name or the expected answer.

The API details used are in [docs/jev-api-notes.md](docs/jev-api-notes.md).

### The expected outcomes, and why

| Scenario | Severity | Action | Human review | Probable cause |
|---|---|---|---|---|
| healthy | normal | observe | no | none |
| degraded | high | investigate | no | resource_exhaustion |
| critical | critical | escalate | yes | resource_exhaustion |
| ambiguous | degraded | investigate | yes | unknown |
| contradictory | degraded | investigate | yes | unknown |
| hung_worker | high | restart | no | application_bug |
| log_only_errors | high | investigate | yes | application_bug |

**Probable cause is scored separately.** A run is PASS when severity, action and human review are all right, because that is the operational decision. The cause is Jev's diagnosis: does it read the logs and metrics correctly? It gets its own accuracy line in the summary and report, and a wrong cause does not turn a PASS into a FAIL. `dependency_failure`, `configuration` and `network` are not the expected answer for any scenario. They are there so Jev has plausible wrong options to choose.

`healthy`, `degraded` and `critical` have fairly clear answers. `ambiguous` and `contradictory` are **judgment calls**: the evidence does not point cleanly to one action, so the expected outcome is our reasoned choice (do not restart or escalate on weak or conflicting evidence, investigate, and ask a human). A different but sensible answer there is not necessarily a model failure. Look at the per-field results and the raw responses, not only the pass rate. The reasoning for each is next to its definition.

`hung_worker` and `log_only_errors` are the scenarios where **the logs carry the evidence**. In `hung_worker` the host looks quiet, but the worker logs show a deadlock, and a restart is the standard fix. It is the only scenario that expects `restart`. In `log_only_errors` every metric looks healthy, but the logs show checkout failing after a deploy. A restart will not fix a code bug, so the answer is investigate plus human review.

### Do the logs help? (`--no-logs`)

`--no-logs` sends Jev the same metrics without the logs. The seed still fixes everything, so you can run the same batch both ways and compare:

```bash
python run.py --runs 70 --seed 1000
python run.py --runs 70 --seed 1000 --no-logs
```

Without logs, Jev cannot see the evidence for `hung_worker` and `log_only_errors`, so expect those to fail. The comparison shows how much the logs contribute. Results from a metrics-only run are saved with a `-nologs` suffix, and the report states which mode was used.

## Prerequisites

- Python 3.10 or newer (CI tests 3.10, 3.11, 3.12 and 3.13)
- A Jev API key from <https://thejevai.com/settings/apikeys>. Not needed for `./run-all.sh --check` or the tests.
- Optional: Docker

## Manual setup

`./run-all.sh` does all of this for you. Do it by hand if you prefer, or on Windows without WSL.

Linux and macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env and set JEV_API_KEY
pytest                    # optional: offline tests
python run.py --runs 7
python report.py
```

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # then edit .env and set JEV_API_KEY
python run.py --runs 7
python report.py
```

Dependencies are pinned in `requirements.txt` to the tested versions.

### Environment variables

| Variable | Required | Default |
|---|---|---|
| `JEV_API_KEY` | yes | none |
| `JEV_API_URL` | no | `https://thejevai.com/v1/systemone` |
| `JEV_MODEL` | no | `jev-latest` |
| `JEV_TIMEOUT_S` | no | `30` |
| `JEV_MAX_RETRIES` | no | `3` |
| `JEV_PRICE_INPUT_PER_MTOK` | no | none (USD per million input tokens, to estimate cost) |
| `JEV_PRICE_OUTPUT_PER_MTOK` | no | none (USD per million output tokens) |

`.env` is git-ignored. Never commit a key.

## Run everything

```bash
./run-all.sh            # 70 runs (10 per scenario)
./run-all.sh 21         # 21 runs
./run-all.sh 70 --no-logs
./run-all.sh 50 --scenario contradictory --seed 1234
```

This creates `.venv`, installs dependencies, runs the offline tests, checks your key, runs the batch, and prints a report. Set `SKIP_TESTS=1` to skip the tests. The report is also saved as `results/<timestamp>-<N>runs-report.md`. You can regenerate it at any time with `python report.py [results/file.jsonl]`.

## Run

```bash
python run.py                                   # one run, random scenario
python run.py --scenario degraded               # one run, named scenario
python run.py --scenario ambiguous --seed 1234  # reproducible input
python run.py --runs 70                         # batch, scenarios in rotation (7 scenarios)
python run.py --runs 70 --no-logs               # same, metrics only
python run.py --runs 50 --scenario contradictory
python run.py --runs 20 --verbose               # full detail for every run
```

One Jev request is sent per run, so `--runs 70` makes 70 API calls. Use a multiple of 7 for equal runs per scenario.

### Reproduce a run with a seed

The base seed is printed at the start of every run. A single run uses that seed as is. In a batch, run *i* uses `base_seed + i`, and each run's scenario and seed are saved in the results file. To replay one run from a batch:

```bash
python run.py --scenario contradictory --seed 1037
```

The seed fixes the **input**: the same scenario and seed always produce the same server observations. Jev's **answers** may still vary between runs, because the model may change (`jev-latest` is an alias) and its outputs are not guaranteed to be identical each time. The model version that answered is saved with every result.

## Results

Each run writes to `results/` (git-ignored):

- `<timestamp>-<N>runs.jsonl`: one JSON line per run: scenario, seed, observations and logs exactly as sent to Jev, expected outcome, Jev's decision, per-field probabilities and confidence, latency, raw response, and match flags.
- `<timestamp>-<N>runs-summary.json`: the aggregate summary, with the base seed and model versions.

The summary reports total, correct and incorrect runs, accuracy by decision type and by scenario, mean confidence (all, correct, incorrect), and telemetry (see below).

### Telemetry

Every run records:

| Field | Meaning |
|---|---|
| `input_tokens`, `output_tokens` | from Jev's `usage` object |
| `cost_usd`, `cost_source` | see below |
| `latency_ms` | round trip of the request that answered |
| `server_elapsed_ms` | Jev's own `elapsedMs` (includes validation, not pure inference) |
| `total_ms` | the whole call, including retries and backoff |
| `attempts`, `http_status` | retries and the final status |
| `request_bytes`, `response_bytes` | payload sizes |
| `log_lines_sent` | how many log lines Jev saw (0 with `--no-logs`) |
| `usage` | Jev's raw usage object, whatever it contains |

The batch summary adds token totals and means, total and per-run cost, round-trip, Jev-elapsed and overhead percentiles, attempts, retries and HTTP status counts. The report has a per-scenario telemetry table, so a `--no-logs` report shows what the logs cost in tokens. The summary file also records start and end time, wall time, runs per minute, git commit, Python version, platform, and the Jev URL and model requested.

**Cost is never invented.** Jev sells credit packs and publishes no per-token price, and its docs say only that usage "may include cost in USD". So:

1. If the response's `usage` has a numeric cost field, that is used, marked `reported:usage.<field>`.
2. Otherwise, if you set `JEV_PRICE_INPUT_PER_MTOK` and `JEV_PRICE_OUTPUT_PER_MTOK`, cost is estimated from tokens, marked `estimated`.
3. Otherwise cost is `n/a`.

How to read it:

- A run counts as correct only if **all three** fields match.
- A reply outside the allowed values is `invalid` and counts as incorrect. It is never adjusted.
- A failed API call is `errored`. It is shown but excluded from accuracy.
- Confidence is the mean of Jev's confidence for severity and action. The cause's own confidence is saved per run but not included. Jev gives no confidence for the yes/no question, only a probability of "yes". That probability is saved, and human review is `yes` when it is 0.5 or more. That threshold is our choice, not part of the Jev API.

## Tests

```bash
pytest
```

The tests need no network and no API key. They cover scenario definitions, generation, seeds, comparison and aggregation, using a fake Jev client. They do not check what real Jev answers, because that is what the experiment measures.

## Docker (optional)

No Python needed on your machine:

```bash
docker build -t jev-ops-experiment .
cp .env.example .env      # then set JEV_API_KEY
docker run --rm --env-file .env -v "$PWD/results:/app/results" jev-ops-experiment --runs 7
docker run --rm -v "$PWD/results:/app/results" --entrypoint python jev-ops-experiment report.py
```

The image contains no credentials; `.env` is excluded from the build. Pass them at run time with `--env-file` or `-e JEV_API_KEY=...`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Python 3.10 or newer is required` | Install a newer Python, or point the script at one: `PYTHON=/usr/bin/python3.12 ./run-all.sh --check` |
| `could not create a virtual environment` | Debian/Ubuntu: `sudo apt install python3-venv` |
| `JEV_API_KEY is not set` / `still the placeholder` | Put your real key in `.env` |
| `ERROR ... HTTP 401` in the results | The key is wrong or revoked |
| `HTTP 429` / `529` | Rate limited or overloaded. The client retries with backoff; lower `--runs` or try later |
| `./run-all.sh: Permission denied` | `chmod +x run-all.sh`, or run `bash run-all.sh` |
| Broken venv after moving the folder | `rm -rf .venv` and run `./run-all.sh --check` again |

## Limitations

- The data is synthetic, and the scenarios are simple. Good results here do not show fitness for real infrastructure.
- Each scenario has a single expected answer. For ambiguous cases more than one answer may be reasonable.
- Log lines come from a small set of templates. Real logs are much noisier and larger.
- Results depend on the Jev model version and on how the questions are worded (`QUESTIONS` in `jev/client.py`).

## Layout

```
run.py                    CLI and batch runner
scenarios/definitions.py  scenarios, expected outcomes, rationale
generator/server_state.py synthetic observations
generator/app_logs.py     synthetic application logs
jev/client.py             Jev adapter (the only Jev-specific code)
evaluation/evaluator.py   comparison, aggregation, summary text
tests/                    offline unit tests
docs/jev-api-notes.md     Jev API notes
openspec/                 specs, design and tasks for this project
```
