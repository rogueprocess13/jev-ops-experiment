## ADDED Requirements

### Requirement: Service-level recovery check
A recovery check SHALL pass only when every demo Deployment is at or above its baseline availability with its rollout complete, every application pod is Running and Ready, and no service deviates from its baseline by the Tier 2 deviation rules over the window since the last check. Replaced pods and restart counts SHALL NOT fail the check. Results SHALL go to the harness and the record only, never to the engine.

#### Scenario: Restarted pods after a rollback
- **WHEN** a rollback replaced cart's pods, all pods are Ready and no service deviates
- **THEN** the check passes

#### Scenario: Errors persist
- **WHEN** frontend's error rate is still above baseline by the deviation rule
- **THEN** the check fails

### Requirement: Recovery held for a period within a window
Checks SHALL run every 15 s, starting when the action completes or, with no executed action, at the detecting poll, for up to 300 s. Recovery SHALL count only when checks pass for 30 s in a row. The fault SHALL stay injected for the whole window.

#### Scenario: One passing check then a failure
- **WHEN** a check passes and the next fails
- **THEN** recovery is not counted and checking continues

#### Scenario: Window ends
- **WHEN** no 30 s run of passing checks occurs within 300 s
- **THEN** the outcome is `not_recovered` and `recovery_verified` is false

### Requirement: MTTR and timing fields
The record SHALL hold `t_inject`, `t_detect`, `t_action_start`, `t_action_done`, `t_recovered` (the first check of the passing run) and `t_recovery_verified` (the end of that run). As in the group's harness, `mttr_seconds` SHALL be `t_action_done - t_inject` (fault to remediation written) and `mttr_verified_seconds` SHALL be `t_recovered - t_inject` (fault to recovery verified), the latter only for `recovered_by_action`. `time_to_remediate_seconds` SHALL be `t_action_done - t_detect`. A value that cannot be measured SHALL be `null`.

#### Scenario: Recovered after a scale up
- **WHEN** inject is at 0 s, detection at 16 s, the action completes at 20 s and checks pass from 50 s to 80 s
- **THEN** `mttr_seconds` is 20, `mttr_verified_seconds` is 50, `t_recovery_verified` is 80 s after inject and `time_to_remediate_seconds` is 4

#### Scenario: Not recovered
- **WHEN** an action completed at 20 s and the outcome is `not_recovered`
- **THEN** `mttr_seconds` is 20, and `t_recovered`, `t_recovery_verified` and `mttr_verified_seconds` are `null`

### Requirement: Three recovery outcomes
Each fault run SHALL have one outcome: `recovered_by_action` (an action was executed and the passing run began after it completed), `recovered_without_action` (no action was executed, the action was not executable, or the passing run began before the action completed), or `not_recovered`. `recovery_verified` SHALL be true only for `recovered_by_action`. A `recovered_without_action` run SHALL set `self_recovered: true` and `self_recovery_seconds` (`t_recovered - t_inject`).

#### Scenario: Self-healing fault
- **WHEN** Jev says `investigate` on K002 and the system recovers on its own at 25 s
- **THEN** the outcome is `recovered_without_action`, `recovery_verified` is false, `self_recovered` is true and `self_recovery_seconds` is 25

### Requirement: False-alarm actions recorded
On a no-incident scenario or the `K000` control, a detecting poll with an executable action SHALL set `action_on_false_alarm: true`. If any recovery check fails after that action, the record SHALL set `disturbed_healthy_system: true`.

#### Scenario: Restart on the healthy control
- **WHEN** a `K000` poll reports an incident with `restart_service` on `frontend` and a later check fails
- **THEN** both `action_on_false_alarm` and `disturbed_healthy_system` are true
