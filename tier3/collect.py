"""Assemble Tier 3 collector output for one window: Tier 2's service telemetry
(Prometheus, Jaeger, OpenSearch through the Tier 3 NodePorts) plus Kubernetes state."""
from __future__ import annotations

from tier2.collect import collect as collect_services
from tier3.collectors.kube import deployment_rows, event_rows, node_rows, pod_rows
from tier3.observation import KubeState


def kube_state(kube, start_s: float | None = None, end_s: float | None = None) -> KubeState:
    """Current deployments, pods and nodes; Warning events in [start_s, end_s)."""
    pods = pod_rows(kube.list_pods())
    events = event_rows(kube.list_warning_events(), start_s, end_s) if start_s is not None else []
    return KubeState(deployments=deployment_rows(kube.list_deployments()), pods=pods,
                     nodes=node_rows(kube.list_nodes(), pods), events=events)


def collect(prom, jaeger, logs, kube, *, window_end: float, window_s: int, baseline_end: float,
            baseline_s: int):
    telemetry = collect_services(prom, jaeger, logs, window_end=window_end, window_s=window_s,
                                 baseline_end=baseline_end, baseline_s=baseline_s)
    return telemetry, kube_state(kube, window_end - window_s, window_end)
