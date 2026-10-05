# jev-ops-experiment

This project tests whether Jev AI can make bounded operational decisions from synthetic server-state information. Server conditions are generated from predefined scenarios with independently defined expected outcomes. Jev receives the observations and selects from a bounded set of operational decisions. The experiment then compares Jev's decisions against the expected outcomes and records accuracy and confidence.

> **This is an experimental benchmark, not a production autonomous remediation system.** It only generates data, asks Jev for a decision, and records the answer. It never restarts, changes or escalates anything.

Prepared for discussion in the LF Edge AIOps forum.

[![tests](https://github.com/rogueprocess13/jev-ops-experiment/actions/workflows/tests.yml/badge.svg)](https://github.com/rogueprocess13/jev-ops-experiment/actions/workflows/tests.yml)

## Two tiers

| | Tier 1: synthetic | Tier 2: OpenTelemetry Demo |
|---|---|---|
| Input | Seeded random server statistics | Real metrics, logs and traces from a running distributed application |
| Tests | Basic decision reasoning | AIOps reasoning against realistic telemetry |
| Ground truth | Hand-written expected decision per scenario | The fault the harness injected, hidden from Jev |
| Infrastructure | None (Python only) | Docker Compose |
| Run with | `./run-all.sh` (this page, below) | `./run-experiment F001` ([Tier 2](#tier-2-opentelemetry-demo)) |

The two tiers share only the Jev client (`jev/client.py`). Everything from "Quick start" down to "Docker (optional)" describes Tier 1. Tier 2 has its own section.

## Quick start

You need Python 3.10 or newer and git. Linux and macOS work as shown. On Windows, use WSL or see [Manual setup](#manual-setup).

```bash
git clone https://github.com/rogueprocess13/jev-ops-experiment.git
cd jev-ops-experiment
./run-all.sh --check      # sets up .venv, installs, runs the tests. No key, no API calls.
```

Then get a Jev API key from the TypeSafe console at <https://console.typesafe.ai/>, put it in `.env` (the check created it for you):

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

### Compare with an LLM (`--engine`)

Is Jev better than asking a general-purpose LLM? `--engine` sends the same observation, with the same questions and the same allowed options, to a baseline model instead of Jev. Scenarios, expected outcomes and scoring do not change.

| Engine | Model | Needs |
|---|---|---|
| `jev` (default) | Jev (`jev-latest`) | `JEV_API_KEY` |
| `claude-sonnet` | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | `ANTHROPIC_API_KEY`, or the `claude` CLI |
| `claude-opus` | Claude Opus 5.5 (`claude-opus-5-5`) | `ANTHROPIC_API_KEY`, or the `claude` CLI |
| `ollama:<model>` | any local Ollama model, for example `ollama:qwen3:8b` | Ollama running locally |

Use the same `--seed` and `--runs` for every engine, then compare:

```bash
python run.py --runs 70 --seed 1000
python run.py --runs 70 --seed 1000 --engine claude-sonnet
python run.py --runs 70 --seed 1000 --engine ollama:qwen3:8b
python report.py --compare results/A.jsonl results/B.jsonl results/C.jsonl
```

Things to know:

- **Claude without an API key.** If `ANTHROPIC_API_KEY` is not set, the Claude engines use the `claude` CLI (`claude -p`) instead and print a warning first. It runs in an empty temporary directory with no tools, settings, hooks or MCP servers, but it is still the Claude Code harness, not the bare API. Those results are labelled `transport=claude-cli`, and the comparison report says so. Set the key for the cleanest comparison.
- **Confidence.** Only Jev returns probabilities. The LLMs return none, and none is made up, so confidence is not compared.
- **Cost.** Claude API cost is `n/a` unless you set the `CLAUDE_*_PRICE_*` variables (`.env.example` lists Anthropic's prices on 2026-10-05 as commented examples). The CLI reports a cost itself; on a subscription plan that figure is notional. Ollama is local, so cost is `n/a`.
- **Repeatability.** Ollama runs use temperature 0 and the run seed, so they repeat exactly. Claude models do not accept a temperature, so repeat runs (10 per scenario) and look at the spread.
- **Refusals.** A Claude refusal counts as `invalid` (wrong). No other model is asked in its place.
- `./run-all.sh 70 --seed 1000 --engine claude-sonnet` works too. It only asks for `JEV_API_KEY` when the engine is Jev.

API details for the baseline engines are in [docs/llm-baseline-notes.md](docs/llm-baseline-notes.md).

### Metrics report (F1, p95, detection rate...)

```bash
python report.py --metrics results/A.jsonl [results/B.jsonl ...]
```

Writes `results/<timestamp>-metrics-report.md` with one column per file: accuracy with 95% confidence intervals, precision/recall/F1 per class plus macro and weighted F1, incident detection (recall, false positive rate, miss rate), human-review F1, over- and under-reaction, Brier score (Jev only), latency p50/p90/p95/p99, availability and error rates, tokens and cost per run and per correct decision, and confusion matrices. It ends with a glossary, and a section on metrics that do not apply here (MTTD, MTTR, MTBF, uptime) and why.

## Prerequisites

- Python 3.10 or newer (CI tests 3.10, 3.11, 3.12 and 3.13)
- A Jev API key from the TypeSafe console, <https://console.typesafe.ai/>. (thejevai.com is a separate site, not affiliated with TypeSafe. See [docs/jev-api-notes.md](docs/jev-api-notes.md).) Not needed for `./run-all.sh --check` or the tests.
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
| `JEV_API_URL` | no | `https://api.typesafe.ai/v1/systemone` |
| `JEV_MODEL` | no | `jev-latest` |
| `JEV_TIMEOUT_S` | no | `30` |
| `JEV_MAX_RETRIES` | no | `3` |
| `JEV_PRICE_INPUT_PER_MTOK` | no | none (USD per million input tokens, to estimate cost) |
| `JEV_PRICE_OUTPUT_PER_MTOK` | no | none (USD per million output tokens) |
| `ANTHROPIC_API_KEY` | only for `--engine claude-*` via the API | none (without it, the `claude` CLI is used) |
| `LLM_EFFORT` | no | `medium` (Claude effort: `low`, `medium`, `high`, `xhigh`, `max`) |
| `OLLAMA_URL` | no | `http://localhost:11434` |
| `CLAUDE_SONNET_PRICE_INPUT_PER_MTOK`, `CLAUDE_SONNET_PRICE_OUTPUT_PER_MTOK` | no | none (USD per million tokens, to estimate cost) |
| `CLAUDE_OPUS_PRICE_INPUT_PER_MTOK`, `CLAUDE_OPUS_PRICE_OUTPUT_PER_MTOK` | no | none |

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

First full comparison (Jev, Claude Sonnet, Claude Opus, qwen3:8b; 70 runs each): [docs/results-2026-10-05-tier1-baselines.md](docs/results-2026-10-05-tier1-baselines.md).

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

## Tier 2: OpenTelemetry Demo

### What it tests

Whether Jev can detect, locate and diagnose a real incident, and recommend an acceptable action, from the telemetry a distributed application produces. A controller injects a known fault into the [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) (the "Astronomy Shop"), collects the metrics, logs and traces it generates, builds a normalized observation, asks Jev, and then scores the answer against the fault it injected. Jev never sees the fault.

Four things are scored separately, as PASS, FAIL or UNKNOWN:

| Dimension | Question |
|---|---|
| detection | Did Jev see an incident when there was one (and none when there was not)? |
| localization | Did it name the service where the problem starts? |
| diagnosis | Did it name the failure mode? |
| action | Is its recommended action in the scenario's acceptable list? |

There is no combined score. A run can find the right service and still fail on the action, and the results show that.

### Why the OpenTelemetry Demo

It is a maintained, widely known application with about 20 services in many languages, real telemetry through OpenTelemetry, a load generator, and a built-in fault mechanism (feature flags). Using it means we do not write our own app or fake telemetry, and anyone can pull the same version. Pinned to release **3.1.0**.

### Architecture

```
scenario (YAML) ──► Experiment controller (tier2/runner.py)
                          │ inject fault via flagd flag       ▲ reset (always)
                          ▼                                   │
                  OpenTelemetry Demo 3.1.0  ◄── Locust load
                          │ OTLP
                          ▼
         Prometheus (metrics) · Jaeger (traces) · OpenSearch (logs)
                          │ HTTP, tier2/collectors/
                          ▼
              Observation builder + scrubber  (no scenario, fault or ground truth in scope)
                          │
                          ▼
              AIOpsEngine ──► JevAdapter ──► Jev
                          │ Decision (raw response kept)
                          ▼
                  Evaluator: Decision vs GroundTruth ──► results/tier2/<run-id>/<ID>.json
```

### Prerequisites

- Docker with the Compose plugin
- About 8 GB of free memory for the full stack (`TIER2_PROFILE=minimal` needs about 4 GB and drops Kafka, accounting and fraud-detection)
- Python 3.10+, git, and a Jev API key in `.env`

### Start the demo

```bash
./setup.sh --start        # creates .venv, clones the demo at 3.1.0, pulls images, starts it
./health-check.sh         # wait ~3 minutes after start; all checks must pass
```

Stop it with `tier2/testbed/stop.sh` (this also removes its volumes).

The demo's own `.env` says `DEMO_VERSION=latest`. The scripts set `DEMO_VERSION=3.1.0` as an environment variable on every Compose call, so the images match the tag and the checkout stays unmodified.

### Verify telemetry

`./health-check.sh` checks, in order: the frontend, Prometheus, span metrics, Jaeger, OpenSearch, that every flag is `off`, and that the load generator is running. It exits non-zero and names the failing check. Span metrics appear a couple of minutes after the stack starts.

You can also look by hand through Envoy: <http://localhost:8080> (shop), `/jaeger/ui/`, `/grafana/`, `/loadgen/` (Locust), and Prometheus on <http://localhost:9090>.

### How faults are injected

Only through the demo's own **flagd** feature flags, never by killing containers. The injector reads the flag config from the flagd-ui API, changes one variant, writes it back and reads it back to confirm; flagd reloads the file within about a second. Two flag shapes exist: most are enabled by setting `defaultVariant`, but `productCatalogFailure` has a targeting rule, so the injector sets the rule's matched branch instead (and only product `OLJCESPC7Z` fails).

`./run-experiment` always resets in a `finally` block. If a run is interrupted, `python -m tier2 reset-faults` turns every flag off.

### How Jev receives observations

Jev receives one JSON object, the same shape every run, built only from collected telemetry:

| Field group | Contents |
|---|---|
| `window`, `baseline_window` | start and end timestamps of the observation and of the baseline before the fault |
| `services` | per service: request rate, error rate, p50 and p95 latency, baseline values and the change from baseline. Ranked by change, top 12 |
| `dependencies` | caller to callee edges with call and error counts (from traces), top 20 |
| `error_logs` | WARN and ERROR lines, deduplicated with a count, at most 3 per service for 8 services, 240 characters each |
| `failing_traces` | up to 5 failing traces: the service path, duration, and the failed spans with the error text |

The whole observation is capped at 60,000 bytes; the lowest-ranked items are trimmed first, and what was trimmed is recorded in the result file only. Jev is asked four fixed questions (`incident_detected`, `affected_service`, `diagnosis`, `recommended_action`) with the same answer vocabulary every time, including `unknown`, `none` and `no_action` so it is never forced to guess.

**What Jev does not receive:** the experiment ID, the flag name or variant, the target service as a label, the expected diagnosis or action, any evaluation, or `feature_flag` data. A scrubber removes flag names, `flagd` and `feature_flag` attributes from all telemetry, and the collectors exclude `flagd`, `flagd-ui`, `telemetry-docs` and `load-generator` entirely. Tests run every scenario through the full path with deliberately contaminated fixtures and fail if any of these reaches the engine.

Limit: service names and error messages are evidence and are sent. A model could in principle recognise the demo and know its flags from training data. That cannot be removed, only noted.

### Run experiments

```bash
./run-experiment list            # experiment IDs
./run-experiment F000            # healthy control: any incident reported is a false positive
./run-experiment F003            # one fault
./run-all-experiments            # the whole catalogue
./run-all-experiments --repeats 3
```

Each run follows the same lifecycle: check health, wait for steady load, take a baseline, inject, wait for the fault to show up, collect, build the observation, ask Jev, store the raw answer, evaluate, **reset the fault**, and check the system returned to baseline. If it did not, the run is marked `contaminated` and the batch stops, because later experiments would be invalid. Each run makes one Jev call and takes about 8 to 10 minutes.

| ID | Fault (flagd flag) | What it tests |
|---|---|---|
| F000 | none | healthy control, false positives |
| F001 | `productCatalogFailure` | direct failure of one product in product-catalog |
| F003 | `paymentFailure` | transaction failure, symptom in checkout |
| F004 | `paymentUnreachable` | misleading symptoms: checkout errors, payment healthy |
| F005 | `imageSlowLoad` | latency only, no errors, origin in the proxy |
| F006 | `productCatalogLockContention` | database-level degradation |

`F002` (`cartFailure`) and the first `F005` (`intlShippingSlowdown`) were dropped: neither produced a measurable effect in 3.1.0.

See `docs/otel-demo-notes.md` for how each flag was verified and which ones behaved differently from the demo's documentation.

### How results are evaluated

`tier2/evaluate.py` is a pure function of the stored Jev decision and the hidden ground truth, run after the answer is stored. Detection compares the incident flag; localization the service; diagnosis the failure mode; action checks the recommendation against the scenario's acceptable list. UNKNOWN means Jev's reply was invalid or the call failed, and is never counted as PASS or FAIL. Aggregates give counts per dimension and a false-positive rate over control runs. Ground truth is hand-written in each scenario file with a rationale; it is never derived from Jev or from the collected telemetry.

Results are written to `results/tier2/<run-id>/<ID>.json` (git-ignored) with the fault, ground truth, Jev's normalized answer and **raw response**, the four verdicts, timing (`null` when not measurable), the exact request sent, the demo image versions and the git commit.

### Add a new experiment

1. Pick a flag from `tier2/testbed/opentelemetry-demo/src/flagd/demo.flagd.json` and check it produces a visible effect (see `docs/otel-demo-notes.md`).
2. Copy a file in `tier2/scenarios/`, set a new `experiment_id`, the `fault` (flag and variant), the `expected` block and a `rationale` explaining why that is the right answer.
3. `./run-experiment list` shows it. Loading checks the vocabulary, the service names and that the flag and variant exist in the pinned flag file.

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
llm/                      baseline engines: Claude (API or claude CLI), Ollama
evaluation/evaluator.py   comparison, aggregation, summary text
tests/                    offline unit tests
docs/jev-api-notes.md     Jev API notes
docs/llm-baseline-notes.md API notes for the baseline engines
docs/results-2026-10-05-tier1-baselines.md  first four-engine comparison, with test machine
openspec/                 specs, design and tasks for this project
```

## License

MIT. See [LICENSE](LICENSE). This project is not affiliated with or endorsed by TypeSafe AI (Jev) or LF Edge.
