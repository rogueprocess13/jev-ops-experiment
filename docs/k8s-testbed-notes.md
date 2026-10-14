# Tier 3 testbed notes (kind, LF Edge Kubernetes faults)

Facts Tier 3 depends on, where each came from, and what is still unverified. Task group 1 in `openspec/changes/k8s-faults-tier3/tasks.md` fills in the open items on a real cluster. Change `tier3/testbed/pins.env`, the scenarios or the code only together with this file.

## LF Edge harness (read 2026-10-14, task 1.5)

Source: `lfedgeai/AIOps`, `research/agentic_aiops_architectures/code/harness/run_harness.py`, commit `a408708` (2026-10-12). Read only; nothing from it is run here.

| Item | Their harness | Tier 3 |
|---|---|---|
| Fault selection | `--flag` is the fault type (default `scale_zero`), `--variant` the target deployment (default `cart`) | `fault.type`, `fault.target`; exported as `fault_flag`, `fault_variant` |
| Wait before the first poll | 15 s after injection (2 s without injection) | `telemetry_lag_s` 15 |
| Poll interval | `--poll-interval`, default 15 s | `poll_interval_s` 15 in every scenario |
| Detection window | `--detection-timeout`, default 1500 s (wall clock; skips a last poll that cannot finish) | `detection_window_s` 240: Jev answers in about a second, not minutes |
| Fault duration | `--fault-duration`, default 90 s, then recovery | fault held until detection or the window ends, then reset |
| MTTD | injection time to first alert (the agent's own timestamp if it reports one, else the harness clock) | `t_inject` to the decision time of the first detecting poll |
| Healthy control | `--skip-fault-injection` ("analyze existing telemetry only"); false alarms are not scored | `K000`, every poll scored for false alarms |

Per-run fields (`HarnessRun`) used by `python -m tier3 export-lfedge`: `run_id`, `fault_flag`, `fault_variant`, `fault_injection_time`, `first_alert_time`, `mttd_seconds`, `mttr_seconds`, `detected`, `suggested_remediations`, `suggested_root_cause`, `expected_root_cause`, `rca_correct`, `remediation_correct`, `remediation_declared`, `remediation_executed`, `recovery_verified`, `mttr_verified_seconds`, `approach`, `llm_invoked`, `agent_error`. Their MLflow logging writes `-1` for an unmeasured time; our export writes `null`.

### Their fault code, and what Tier 3 does differently

| Fault | Their inject (`inject_k8s_fault`) | Tier 3 |
|---|---|---|
| `scale_zero` | replicas 0 | same; restore the saved count (theirs restores 1) |
| `memory_limit` | every container's memory limit `10Mi` | same; a memory request above the limit is lowered too, or the API server rejects the change |
| `readiness_probe_fail` | every container: `exec: ["false"]` probe | same (period 5 s, threshold 1) |
| `config_corruption` | every container: `DATABASE_HOST=invalid-host-that-does-not-exist.local` **and `HARNESS_INJECTED_FAULT=config_corruption`** | `DATABASE_HOST` only; the second variable names the fault to any agent that reads the pod spec |
| `pvc_full` | `sh -c "dd ... of=/tmp/fill_disk bs=1M count=500 2>/dev/null \|\| true"` in a pod | same write to `/tmp/jev-fault-fill`, but a failed write fails the inject instead of being ignored |
| `node_taint` | taints the **first listed node** with `harness-fault=true:NoExecute`, replacing its taint list | adds `jev-fault=true:NoExecute` to an application worker only, keeps other taints, removes only its own |
| `replica_overload` | target replicas 0, `load-generator` replicas 3 | same; both saved counts restored |
| `dependency_removal` | target replicas 0 | same, target `valkey-cart` |
| `network_partition`, `kill_pod` | deny-ingress NetworkPolicy; delete the target's pods | same; policy named `jev-fault-np` |

## Pinned versions (tasks 1.2-1.4, not yet verified)

| Component | Pin | Status |
|---|---|---|
| kind | `v0.29.0` | to confirm on install |
| node image | `kindest/node:v1.33.1` | to confirm, record the digest |
| CNI | kindnet (`CNI=kindnet`) | **to verify**: does kindnet enforce NetworkPolicy? If not, `CNI=calico` with Calico `v3.29.3` |
| Demo chart | the `open-telemetry/opentelemetry-demo` release with `appVersion` 3.1.0 | `install.sh` resolves and records it; pin it in `pins.env` afterwards |

## Chart facts the code assumes (task 1.4, not yet verified)

- Each demo service is a Deployment named after the service (`cart`, `valkey-cart`, `load-generator`, ...). `python -m tier3 health` fails with "missing deployments" if not.
- Pods carry `opentelemetry.io/name: <service>`; `nodeports.yaml` and the pod-to-service mapping rely on it (`app.kubernetes.io/component` and `app.kubernetes.io/name` are fallbacks).
- Placement keys in `values/demo.yaml`: `default.schedulingRules.nodeSelector`, `components.<name>.schedulingRules.nodeSelector`, and the subcharts' own `nodeSelector` keys (`opentelemetry-collector`, `jaeger`, `prometheus.server`, `grafana`, `opensearch`). Check placement after install.
- Prometheus server pods: `app.kubernetes.io/name=prometheus, app.kubernetes.io/component=server`; OpenSearch pods: `app.kubernetes.io/name=opensearch`.
- Infrastructure deployments hidden from the engine are matched by name prefix (`INFRA_PREFIXES` in `tier3/collectors/kube.py`). Check the list against the real deployment names.
- Span metrics, Jaeger and OpenSearch field names as in Tier 2 (`docs/otel-demo-notes.md`), now reached through the NodePorts.

## Fault behaviour on the cluster (tasks 1.6-1.9, open)

For each fault, record what shows in span metrics, Jaeger, OpenSearch, deployments, pods, nodes and events, how long it takes, and that exact restore works. Open questions:

- **Rolling updates** (`memory_limit`, `readiness_probe_fail`, `config_corruption`): with one replica, does the old pod keep serving? Decide `expected.incident` for K003, K005 and K006 with a rationale.
- **`config_corruption` on cart**: does cart read `DATABASE_HOST`? If not, drop or retarget K006 and tell the group, since their matrix uses it.
- **`kill_pod`** (K002): is the symptom still visible at the first poll, 15 s after injection?
- **`pvc_full`** (K010): does the cart image have `sh` and `dd`? Does 500 MB in the writable layer cause any symptom on kind?
- Capture real Warning events as leak-test fixtures (task 1.10) and list every string that names a fault or a harness object.

## Dropped or changed scenarios

None yet.
