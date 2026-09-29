# jev-ops-experiment

This project tests whether Jev AI can make bounded operational decisions from synthetic server-state information. Server conditions are generated from predefined scenarios with independently defined expected outcomes. Jev receives the observations and selects from a bounded set of operational decisions. The experiment then compares Jev's decisions against the expected outcomes and records accuracy and confidence.

> **This is an experimental benchmark, not a production autonomous remediation system.** It only generates data, asks Jev for a decision, and records the answer. It never restarts, changes or escalates anything.

Prepared for discussion in the LF Edge AIOps forum.

## How it works

```
Known scenario -> Known server state -> Jev -> Decision -> Compare with independent expected outcome
```

- **Scenarios** (`scenarios/definitions.py`): `healthy`, `degraded`, `critical`, `ambiguous`, `contradictory`. Each has an expected outcome written by hand in code, with a written rationale. No LLM is used to produce it. It does not depend on the generated numbers or the seed.
- **Generator** (`generator/server_state.py`): builds CPU, memory, disk, load, network errors, application error rate, API latency, service statuses and recent restarts/events. Metrics are derived from a shared stress level for the scenario, so they move together. `contradictory` deliberately breaks this, with two patterns: quiet hosts with a failing service, and a busy host with no symptoms.
- **Jev adapter** (`jev/client.py`): the only module that talks to Jev. Jev is asked three typed questions in one request:
  - severity: `normal`, `degraded`, `high`, `critical`
  - action: `observe`, `investigate`, `restart`, `escalate`
  - human review required: `yes` or `no`
- **Evaluator** (`evaluation/evaluator.py`): compares each field, then aggregates accuracy, confidence and latency. Every figure is calculated from the real results.

Jev sees only the server observations. It never sees the scenario name or the expected answer.

The API details used are in [docs/jev-api-notes.md](docs/jev-api-notes.md).

### The expected outcomes, and why

| Scenario | Severity | Action | Human review |
|---|---|---|---|
| healthy | normal | observe | no |
| degraded | high | investigate | no |
| critical | critical | escalate | yes |
| ambiguous | degraded | investigate | yes |
| contradictory | degraded | investigate | yes |

`healthy`, `degraded` and `critical` have fairly clear answers. `ambiguous` and `contradictory` are **judgment calls**: the evidence does not point cleanly to one action, so the expected outcome is our reasoned choice (do not restart or escalate on weak or conflicting evidence, investigate, and ask a human). A different but sensible answer there is not necessarily a model failure. Look at the per-field results and the raw responses, not only the pass rate. The reasoning for each is next to its definition.

## Prerequisites

- Python 3.10 or newer (developed on 3.13)
- A Jev API key from <https://thejevai.com/settings/apikeys>

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then edit .env and set JEV_API_KEY
```

### Environment variables

| Variable | Required | Default |
|---|---|---|
| `JEV_API_KEY` | yes | none |
| `JEV_API_URL` | no | `https://thejevai.com/v1/systemone` |
| `JEV_MODEL` | no | `jev-latest` |
| `JEV_TIMEOUT_S` | no | `30` |
| `JEV_MAX_RETRIES` | no | `3` |

`.env` is git-ignored. Never commit a key.

## Run everything

```bash
./run-all.sh            # 100 runs
./run-all.sh 20         # 20 runs
./run-all.sh 50 --scenario contradictory --seed 1234
```

This creates `.venv`, installs dependencies, runs the offline tests, checks your key, runs the batch, and prints a report. Set `SKIP_TESTS=1` to skip the tests. The report is also saved as `results/<timestamp>-<N>runs-report.md`. You can regenerate it at any time with `python report.py [results/file.jsonl]`.

## Run

```bash
python run.py                                   # one run, random scenario
python run.py --scenario degraded               # one run, named scenario
python run.py --scenario ambiguous --seed 1234  # reproducible input
python run.py --runs 100                        # batch, scenarios in rotation
python run.py --runs 50 --scenario contradictory
python run.py --runs 20 --verbose               # full detail for every run
```

One Jev request is sent per run, so `--runs 100` makes 100 API calls.

### Reproduce a run with a seed

The base seed is printed at the start of every run. A single run uses that seed as is. In a batch, run *i* uses `base_seed + i`, and each run's scenario and seed are saved in the results file. To replay one run from a batch:

```bash
python run.py --scenario contradictory --seed 1037
```

The seed fixes the **input**: the same scenario and seed always produce the same server observations. Jev's **answers** may still vary between runs, because the model may change (`jev-latest` is an alias) and its outputs are not guaranteed to be identical each time. The model version that answered is saved with every result.

## Results

Each run writes to `results/` (git-ignored):

- `<timestamp>-<N>runs.jsonl`: one JSON line per run: scenario, seed, observations, expected outcome, Jev's decision, per-field probabilities and confidence, latency, raw response, and match flags.
- `<timestamp>-<N>runs-summary.json`: the aggregate summary, with the base seed and model versions.

The summary reports total, correct and incorrect runs, accuracy by decision type and by scenario, mean confidence (all, correct, incorrect) and latency (mean, p50, p95, max).

How to read it:

- A run counts as correct only if **all three** fields match.
- A reply outside the allowed values is `invalid` and counts as incorrect. It is never adjusted.
- A failed API call is `errored`. It is shown but excluded from accuracy.
- Confidence is the mean of Jev's confidence for severity and action. Jev gives no confidence for the yes/no question, only a probability of "yes". That probability is saved, and human review is `yes` when it is 0.5 or more. That threshold is our choice, not part of the Jev API.

## Tests

```bash
pytest
```

The tests need no network and no API key. They cover scenario definitions, generation, seeds, comparison and aggregation, using a fake Jev client. They do not check what real Jev answers, because that is what the experiment measures.

## Docker (optional)

```bash
docker build -t jev-ops-experiment .
docker run --rm -e JEV_API_KEY=... -v "$PWD/results:/app/results" jev-ops-experiment --runs 20
```

The image contains no credentials. Pass them at run time.

## Limitations

- The data is synthetic, and the scenarios are simple. Good results here do not show fitness for real infrastructure.
- Each scenario has a single expected answer. For ambiguous cases more than one answer may be reasonable.
- Results depend on the Jev model version and on how the questions are worded (`QUESTIONS` in `jev/client.py`).

## Layout

```
run.py                    CLI and batch runner
scenarios/definitions.py  scenarios, expected outcomes, rationale
generator/server_state.py synthetic observations
jev/client.py             Jev adapter (the only Jev-specific code)
evaluation/evaluator.py   comparison, aggregation, summary text
tests/                    offline unit tests
docs/jev-api-notes.md     Jev API notes
openspec/                 specs, design and tasks for this project
```
