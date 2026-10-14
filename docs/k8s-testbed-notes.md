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

## Host (task 1.1, 2026-10-14)

30 GB RAM, about 9.2 GB available with the owner's other work running; 16 cores, load about 1.2; NVMe SSD, 359 GB free; Docker 29.8.2; Tier 2 stopped. Swap is zram (compressed RAM), so memory pressure costs CPU, not disk. The pre-check was lowered from 12 to 8 GB after trimming the demo (below); the measured footprint is recorded under task 1.4.

## Pinned versions (tasks 1.2-1.4)

| Component | Pin | Verified |
|---|---|---|
| kind | `v0.29.0` | installed to `~/.local/bin`, SHA-256 checked against the release file (2026-10-14). Newer releases exist (v0.33.0); kept the pin |
| node image | `kindest/node:v1.33.1@sha256:0500722...b34f` | the default image listed in the v0.29.0 release notes |
| kubectl | `v1.33.1` | from dl.k8s.io, SHA-256 checked |
| helm | `v3.22.0` | from get.helm.sh, SHA-256 checked (Helm 4 exists; v3 kept) |
| CNI | kindnet (kind default) | **enforces NetworkPolicy** (task 1.3): kind has shipped `kube-network-policies` since v0.24.0 |
| Demo chart | `open-telemetry/opentelemetry-demo` `0.42.4` (app 3.1.0) | 0.42.0-0.42.4 all carry app 3.1.0; newest taken |

## NetworkPolicy check (task 1.3, 2026-10-14)

busybox `httpd` pod on jev-worker2, client on jev-worker3. Before: `wget` gets the page. With a deny-all ingress policy on the server: `wget: download timed out` (packets dropped, not refused). After deleting the policy: the page again. So `network_partition` makes calls to the target **time out**; callers should show latency and timeouts rather than immediate connection errors.

## Chart facts (task 1.4, checked with `helm template` before install)

- Every demo service is a Deployment named after it (`cart`, `valkey-cart`, `load-generator`, ...). Pods carry `opentelemetry.io/name`, `app.kubernetes.io/component` and `app.kubernetes.io/name` all equal to the service name.
- Subchart pods carry only `app.kubernetes.io/name` and `/component`, with component values such as `server` (Prometheus) and `all-in-one` (Jaeger). The pod-to-service mapping therefore reads `opentelemetry.io/name` first (fixed 2026-10-14; it read `component` first).
- The collector is a DaemonSet `otel-collector-agent` (presets: hostMetrics, kubeletMetrics, kubernetesAttributes, clusterMetrics). It is pinned to `jev-worker`; applications reach it through its Service, so it does not need a pod per node.
- Placement keys: `default.schedulingRules.nodeSelector`, `components.<name>.schedulingRules.nodeSelector`, `opentelemetry-collector.nodeSelector`, `jaeger.jaeger.nodeSelector` (Jaeger chart 4.13.1), `prometheus.server.nodeSelector`, `opensearch.nodeSelector`. The render puts every application Deployment on `jev-role=app` and `jaeger`, `prometheus`, `opensearch`, the collector, `flagd`, `load-generator` and `opamp-server` on `jev-role=observability`.
- Host NodePorts: `frontend-proxy` pods (`opentelemetry.io/name=frontend-proxy`, port 8080), Prometheus (`app.kubernetes.io/name=prometheus, component=server`, 9090), OpenSearch (`app.kubernetes.io/name=opensearch`, 9200). The selectors in `nodeports.yaml` match.
- Demo 3.1.0 in the chart adds `agent`, `chatbot`, `mcp` (LLM assistant), `astronomy-db` (Postgres for product-catalog), `opamp-server` and `telemetry-docs`.

### Trimmed for memory

Disabled in `values/demo.yaml`: `kafka`, `accounting` and `fraud-detection` (Kafka consumers), `agent`, `chatbot`, `mcp` (also not run in Tier 2: they live in `compose.agent.yaml`), `telemetry-docs` and Grafana. About 3 GB of memory limits. None is on the path of any Tier 3 scenario. `checkout` publishes to Kafka only when `KAFKA_ADDR` is set (`src/checkout/main.go`), so its `KAFKA_ADDR` is overridden to empty and its `wait-for-kafka` init container removed. Kept: `astronomy-db` and `opamp-server` (product-catalog depends on both).

Tier 3 therefore has its own service list (`tier3/vocab.py`, 15 services): not Tier 2's, which has `kafka`, `accounting`, `fraud-detection` and `postgresql`.

## Install and measured footprint (task 1.4, 2026-10-14)

`install.sh` with chart 0.42.4 took about 5 minutes (image pulls inside the kind nodes). Placement after install matched the render: every application pod on jev-worker2 or jev-worker3, every observability, flag, load and OpAMP pod on jev-worker, nothing on the control plane. `python -m tier3 health`: all eight checks ok.

Problems found and fixed in `values/demo.yaml`:

1. `ad` (Java) was OOMKilled 5 times in its first 5 minutes with the chart's 300Mi limit. Raised to 500Mi; no restart since.
2. **No application telemetry arrived.** Span metrics had only `flagd` and `frontend-web`, both on jev-worker. The collector is a DaemonSet, and in daemonset mode the chart gives its Service `internalTrafficPolicy: Local`. Pinned to jev-worker it has no pod on the application nodes, so their spans, metrics and logs were dropped. Set `opentelemetry-collector.service.internalTrafficPolicy: Cluster`; afterwards Jaeger lists every application service and span metrics cover the services under load.
3. The collector logged errors every few seconds (kafkametrics without Kafka; kubeletstats TLS on kind; DNS for the disabled firepit) and ships its own logs to OpenSearch as service `otelcol-contrib`: 461 warn/error lines in 5 minutes, which would have topped every observation's `error_logs`. Removed the kafkametrics receiver and the kubeletMetrics preset, and `tier3/collect.py` now drops `otelcol-contrib`, `jaeger` (self-traces) and `opamp-server` from logs, traces, edges and service stats. The firepit DNS warning remains in the collector's own logs only.

Baseline after the fixes, 10 users: span metrics for ad, cart, currency, frontend, frontend-proxy, image-provider, product-catalog, quote, recommendation and shipping (checkout, payment and email appear when orders are placed), all with error rate 0.000; frontend about 11 req/s, p95 about 37 ms.

Measured after settling (`docker stats`, 17:51):

| Node | Memory | CPU |
|---|---|---|
| jev-control-plane | 774 MiB | 10% of a core |
| jev-worker (observability, load) | 2.5 GiB | 16% |
| jev-worker2 (app) | 888 MiB | 8% |
| jev-worker3 (app) | 598 MiB | 15% |
| **total** | **about 4.7 GiB** | **about half a core** |

Startup peaked at load average 8.2 (16 cores) for a few minutes. Docker volumes grew by about 11 GB (images stored inside the kind nodes). The 8 GB pre-check leaves about 3 GB of headroom.

## Fault behaviour on the cluster (tasks 1.6-1.9, open)

For each fault, record what shows in span metrics, Jaeger, OpenSearch, deployments, pods, nodes and events, how long it takes, and that exact restore works. Open questions:

- **Rolling updates** (`memory_limit`, `readiness_probe_fail`, `config_corruption`): with one replica, does the old pod keep serving? Decide `expected.incident` for K003, K005 and K006 with a rationale.
- **`config_corruption` on cart**: does cart read `DATABASE_HOST`? If not, drop or retarget K006 and tell the group, since their matrix uses it.
- **`kill_pod`** (K002): is the symptom still visible at the first poll, 15 s after injection?
- **`pvc_full`** (K010): does the cart image have `sh` and `dd`? Does 500 MB in the writable layer cause any symptom on kind?
- Capture real Warning events as leak-test fixtures (task 1.10) and list every string that names a fault or a harness object.

## Dropped or changed scenarios

None yet.
