## ADDED Requirements

### Requirement: Named, versioned observation layouts
Tier 3 and Tier 4 SHALL support named observation layouts registered in `tier3/layouts.py`, selected with `--observation <name>` on `python -m tier3` and `python -m tier4` (`run`, `batch`, `replay`), defaulting to `raw`. A layout SHALL be a function from the observation built by `build_observation` to the observation sent to the engine. An unknown name SHALL exit before any run or call and list the layouts.

#### Scenario: Unknown layout
- **WHEN** `python -m tier3 replay results/tier4/6.2-combined --observation summary` runs and no `summary` layout exists
- **THEN** the command exits non-zero before any engine call and prints the available layouts

### Requirement: raw is today's observation
The `raw` layout SHALL return its input unchanged, so a `raw` request is byte for byte the request sent before this change. Records without an `observation` field SHALL be read as `raw` v1.

#### Scenario: raw equals the stored request
- **WHEN** every stored Tier 3 fixture poll observation is passed through `raw`
- **THEN** the result serialises to exactly the same bytes as the input

### Requirement: Layouts are recorded
Every live and replay record SHALL store `observation: {name, version, sha256}`, where `sha256` is over the layout function's source. Compare SHALL group by `(engine, prompt, observation)` and SHALL refuse to merge one layout name with two hashes.

#### Scenario: Changed layout code without a version bump
- **WHEN** two record sets both say `facts` v1 with different hashes
- **THEN** compare exits with an error naming both hashes

### Requirement: facts adds no information
The `facts` layout SHALL be a pure, deterministic function of the observation dict. It SHALL NOT read the clock, the cluster, the collectors, the scenario, the fault ledger or any record field. Every name (service, deployment, pod, node) in its output SHALL already appear in its input. It SHALL compute and place only:
- per-service ratio and difference statements against the baseline values already in the row;
- readiness as "ready N of M, baseline N of M" from the deployment rows;
- for each service, its callees from `dependencies` with each callee's own readiness and error statements;
- for every timestamped item, the seconds between it and the window end, in place of the bare timestamp.

#### Scenario: No new tokens
- **WHEN** `facts` runs on every Tier 3 fixture observation
- **THEN** every identifier-like token in the output appears in the input or in the layout's fixed vocabulary of words, and no scenario ID, fault name or `jev-fault` term appears

#### Scenario: Callee state next to the caller
- **WHEN** the observation has a dependency `frontend -> cart` and the `cart` deployment is ready 0 of 1
- **THEN** the `frontend` entry lists `cart` as a callee with "ready 0 of 1, baseline 1 of 1"

### Requirement: No suspect field
A layout SHALL NOT rank, flag, highlight or name a likely cause, origin or component. It SHALL apply the same computation to every service and SHALL keep the input's row order. Statements SHALL describe one entity's own values only.

#### Scenario: Review guard
- **WHEN** the layout test scans the `facts` output keys and fixed words
- **THEN** none of "suspect", "likely", "root", "cause", "origin", "culprit" or "probable" appears

### Requirement: Leak tests cover every layout
The whole-path leak tests in `tests/tier3/test_runner.py` and `tests/tier4/test_runner.py`, and the replay leak test, SHALL run every scenario under every layout. `tier3/layouts.py` SHALL NOT import `tier3.scenarios` or `tier3.faults`.

#### Scenario: New layout added
- **WHEN** a layout is registered
- **THEN** the parametrised leak tests include it without further edits

### Requirement: Every engine gets the same layout
The Jev adapter and the Claude Opus baseline (`tier3/claude_engine.py`) SHALL receive the same laid-out observation for the same poll.

#### Scenario: Opus replay under facts
- **WHEN** `python -m tier3 replay <dir> --engine claude-opus --observation facts` runs
- **THEN** the observation in each Opus prompt equals the one the Jev adapter would send for that poll
