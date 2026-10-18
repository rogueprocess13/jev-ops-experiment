## 1. Verify on the cluster before coding against it

- [ ] 1.1 Read the LF Edge harness (`lfedgeai/AIOps`, `research/agentic_aiops_architectures/code/harness/run_harness.py`) for how it sets `remediation_executed`, `recovery_verified`, `mttr_seconds` and `mttr_verified_seconds`, and whether its fault stays injected during recovery; record it in `docs/k8s-testbed-notes.md` and adjust the D6 export mapping if needed
- [ ] 1.2 Start the cluster (`tier3/testbed/start.sh`), confirm health, and record `revisionHistoryLimit` and the current revision of every demo Deployment
- [ ] 1.3 By hand, for each fault on its Tier 3 target, apply each allowlisted action on the right component (`scale_up`, `restart_service`, `rollback_change`) and record whether and when the service-level recovery check (D5) would pass; note which faults no allowlisted action can fix (expected: `network_partition`, `node_taint`)
- [ ] 1.4 By hand, apply `restart_service` and `rollback_change` to an unrelated healthy Deployment (`frontend`) and record the disturbance and the revision `rollout undo` picks after `rebalance.sh` has run
- [ ] 1.5 Confirm that `kubectl rollout undo` and a rollout restart leave no annotation or label that names the fault or the experiment, and that the harness's exact restore brings the Deployment back after each action
- [ ] 1.6 Measure the recovery check's noise on the healthy cluster: run it for 300 s with no fault and record any failing checks; tune nothing that the scenarios' expected answers depend on
- [ ] 1.7 Write the findings to `docs/k8s-testbed-notes.md` (a Tier 4 section: actions per fault, recovery times with the right action, history behaviour, noise)

## 2. Executor

- [ ] 2.1 `tier4/executor.py`: allowlist mapping (D2), target restrictions with reasons, replica cap, one call per run
- [ ] 2.2 `scale_up` and `restart_service` through the Tier 3 Kubernetes client (`patch`); `rollback_change` through pinned `kubectl rollout undo` with the cluster's kubeconfig, recording revisions before and after
- [ ] 2.3 Save the target Deployment's replicas and pod template to an `action` entry in the ledger before acting; read back after acting
- [ ] 2.4 Extend reset: restore the action entry first, then the fault (D4); make `python -m tier4 reset-faults` and the dead-man timer handle a ledger with an action
- [ ] 2.5 Offline tests: each action, each refusal reason, the cap, the second-call refusal, ledger before act, read-back mismatch, reverse-order restore, crash recovery from the ledger alone

## 3. Recovery

- [ ] 3.1 `tier4/recovery.py`: the service-level check (D5) from Kubernetes state and service stats, ignoring replaced pods and restarts
- [ ] 3.2 Hold period (30 s) and window (300 s); `t_recovered`, `t_recovery_verified`, MTTR, verified MTTR, time to remediate (D6); `null` when not measurable
- [ ] 3.3 Outcomes `recovered_by_action`, `recovered_without_action`, `not_recovered` (D7); `action_on_false_alarm` and `disturbed_healthy_system` (D8)
- [ ] 3.4 Offline tests with a virtual clock: early pass then fail, window end, self-healing, recovery before the action completes, false-alarm action that disturbs

## 4. Runner, results and reports

- [ ] 4.1 `tier4/runner.py`: Tier 3 lifecycle to the first detecting poll, Tier 3 verdicts on that poll, executor once, recovery, reset in `finally`, contamination stop, rebalance between runs
- [ ] 4.2 Results under `results/tier4/<run-id>/` with the action, every recovery check, outcome and timing fields
- [ ] 4.3 Whole-path leak test over every scenario: no fault name, `jev-fault`, expected answer, executor result or recovery result in any request
- [ ] 4.4 Isolation tests (D9): only `tier4/runner.py` and `tier4/cli.py` import the executor; nothing outside `tier4/` does; no Tier 4 module imports `jev.client`
- [ ] 4.5 `tier4/report.py`: scorecard (D10) and LF Edge export with measured remediation fields; MTTR from `recovered_by_action` runs only
- [ ] 4.6 `tier4/cli.py`: `list`, `run`, `batch`, `reset-faults`, `scorecard`, `export-lfedge`; root wrappers `run-remediation-experiment` and `run-all-remediation-experiments`

## 5. Policy and documentation

- [ ] 5.1 `CLAUDE.md`: narrow the "never act" rule to Tier 4 (D11), add a Tier 4 rules section, layout and commands; Tier 1 to 3 rules unchanged
- [ ] 5.2 `README.md`: Tier 4 section with the allowlist, what MTTR measures here, and what is and is not comparable with the group's agents
- [ ] 5.3 New settings, if any, in `.env.example` and the README table
- [ ] 5.4 Confirm `./run-all.sh --check` runs the Tier 4 tests and CI passes on Python 3.10 to 3.13; Tier 1 to 3 tests pass unchanged

## 6. Live runs

- [ ] 6.1 Run each scenario once with Jev through Tier 4; read each request by hand for leaks, and check every action's record and restore
- [ ] 6.2 Batch `K001` to `K010` with `--repeats 3`, plus at least 10 `K000` runs
- [ ] 6.3 Print the scorecard and the LF Edge export
- [ ] 6.4 Write `docs/results-<date>-tier4-jev.md` from the run records only, stating what is not comparable with the group's agents; stop the cluster
