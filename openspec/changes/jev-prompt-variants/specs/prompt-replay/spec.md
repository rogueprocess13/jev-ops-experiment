## ADDED Requirements

### Requirement: Replay stored observations
`python -m tier3 replay <records> --prompt <name> [--engine jev|claude-opus]` SHALL read Tier 3 and Tier 4 run records. It SHALL send each stored `polls[i].request`, in order, to the engine with the variant's questions. `python -m tier2 replay` SHALL do the same with each Tier 2 record's single `request`. Replay SHALL need no Docker, no cluster and no fault injection. It SHALL skip records whose status is not `ok`, and report how many it skipped.

#### Scenario: Replay a Tier 4 batch
- **WHEN** `python -m tier3 replay results/tier4/6.2-combined --prompt strict-incident` runs
- **THEN** each stored poll observation is sent once with the strict-incident questions, and no kubectl, kind or Docker command runs

#### Scenario: Errored source record
- **WHEN** a source record has status `contaminated`
- **THEN** it is skipped, and the replay summary counts it as skipped

### Requirement: Replay sends only the stored observation
The replay request SHALL be the variant's questions plus the stored `request`, unchanged. Replay SHALL NOT pass `ground_truth`, `evaluation`, `fault`, `remediation`, `experiment_id`, the earlier decision or any other record field to the engine. Scoring SHALL read `ground_truth` in a separate step, after the engine has answered.

#### Scenario: Leak test over fixtures
- **WHEN** the replay leak test runs every Tier 2, Tier 3 and Tier 4 fixture record under every variant
- **THEN** every captured request equals the stored `request` plus the variant's questions, and contains no scenario ID, fault name or ground-truth value

### Requirement: Replay scoring follows live scoring
Tier 3/4 replay SHALL score the first stored poll whose answer reports an incident, else the last stored poll. It SHALL compute detection, localization, diagnosis and action with `tier3/evaluate.py` against the stored `ground_truth`. On a no-incident record, every detecting poll SHALL be a false-positive poll. Tier 2 replay SHALL score with `tier2/evaluate.py`. Invalid replies SHALL be `invalid`, and failed calls SHALL be `error`, as in live runs.

#### Scenario: Variant detects later than baseline
- **WHEN** a control record has 15 stored polls and the variant reports an incident at polls 9 and 12 only
- **THEN** all 15 polls are asked, poll 9 is scored, and the run is a false-positive run with 2 false-positive polls out of 15

### Requirement: Censored fault runs
A fault record that stores fewer polls than its live window, where the variant reports no incident on any stored poll, SHALL be marked `censored: true`. It SHALL count as not detected on the stored polls. Reports SHALL show the censored count beside recall, and SHALL NOT call these runs confirmed misses.

#### Scenario: Stricter variant on a one-poll fault run
- **WHEN** a K001 record stored one poll and the variant answers no incident on it
- **THEN** the replay record has `censored: true`, and the report shows it in the censored count

### Requirement: Unmeasurable replay timings are null
Replay records SHALL set `mttd_seconds` and every remediation field to `null`. They SHALL store `detect_poll` and `replay_detect_seconds_since_inject`, the original `seconds_since_inject` of the scored detecting poll. Reports SHALL NOT combine `replay_detect_seconds_since_inject` with live MTTD.

#### Scenario: Timing in a replay record
- **WHEN** a variant first detects at stored poll 2 of a record whose poll 2 has `seconds_since_inject: 31.2`
- **THEN** the replay record has `mttd_seconds: null`, `detect_poll: 2` and `replay_detect_seconds_since_inject: 31.2`

### Requirement: Replay records are kept apart
Replay SHALL write to `results/<tier>/replay/<run-id>/`, one record per source record, with `mode: "replay"`, `source` (path and `run_id` of the original), `prompt`, `engine`, every request and reply, and the verdicts. It SHALL NOT modify the source records. The live scorecard commands SHALL refuse replay records unless asked with `--include-replay`.

#### Scenario: Source untouched
- **WHEN** a replay finishes
- **THEN** the source files are byte-identical to before
