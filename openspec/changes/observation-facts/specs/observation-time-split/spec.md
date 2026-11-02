## ADDED Requirements

### Requirement: Recent and earlier windows
When the `time-split` layout is selected on a live run, the collectors SHALL query service metrics, dependencies, error logs and failing traces twice per poll: the recent window (the last `recent_window_s`, default 60 s) and the earlier part of the observation window. Kubernetes state SHALL stay a single snapshot at the poll time. The layout SHALL show the two as separate blocks, each with its length in seconds computed in code.

#### Scenario: A failure that has recovered
- **WHEN** errors occurred 150 s before the poll and none in the last 60 s
- **THEN** the earlier block shows the errors and the recent block shows an error rate of 0 for that service

### Requirement: Live only
`time-split` SHALL be refused by replay, because stored records lack the per-window data. Replay SHALL exit with a message naming the layout.

#### Scenario: Replay attempt
- **WHEN** `python -m tier3 replay <dir> --observation time-split` runs
- **THEN** it exits before any engine call with "time-split needs live collection"

### Requirement: Null, not invented
A value that cannot be computed for a block, such as a latency percentile with no requests in the recent window, SHALL be `null`. It SHALL NOT be copied from the other block or the baseline.

#### Scenario: Idle recent window
- **WHEN** a service has no requests in the recent window
- **THEN** its recent request rate is 0 and its recent latency and error rate are `null`

### Requirement: Byte budget holds
The two-block observation SHALL stay within the Tier 3 byte budget (`BYTE_BUDGET`), trimming as today and recording trims in `trim_notes`.

#### Scenario: Large observation
- **WHEN** the two blocks together exceed the budget
- **THEN** items are trimmed in the existing order, and `trim_notes` records each trim per block
