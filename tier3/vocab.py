"""Tier 3 vocabularies. Separate from Tier 1 and Tier 2 on purpose (design D8)."""
from __future__ import annotations

from tier2.vocab import SERVICES as _DEMO_SERVICES

# The LF Edge harness's ten Kubernetes fault types, spelled as in their
# code/harness/run_harness.py (inject_k8s_fault).
FAULT_TYPES = (
    "scale_zero",
    "kill_pod",
    "memory_limit",
    "network_partition",
    "readiness_probe_fail",
    "config_corruption",
    "dependency_removal",
    "replica_overload",
    "node_taint",
    "pvc_full",
)

DIAGNOSES = (
    "none",
    "service_unavailable",
    "pod_restart",
    "oom_killed",
    "network_blocked",
    "readiness_failure",
    "misconfiguration",
    "node_eviction",
    "disk_full",
    "overload",
    "application_failure",
    "unknown",
)

ACTIONS = (
    "no_action",
    "investigate",
    "restart_service",
    "scale_up",
    "rollback_change",
    "escalate",
)

# kind node names (cluster "jev", tier3/testbed/kind.yaml).
CONTROL_PLANE = "jev-control-plane"
OBSERVABILITY_NODE = "jev-worker"
APP_NODES = ("jev-worker2", "jev-worker3")
NODES = (CONTROL_PLANE, OBSERVABILITY_NODE, *APP_NODES)

# Demo application and data services, the same list as Tier 2. Each is a
# deployment of the same name in the demo namespace (checked in task 1.4).
SERVICES = _DEMO_SERVICES

NO_COMPONENT = "none"
# Components the engine may name as affected. The same list in every run.
COMPONENTS = (*SERVICES, *NODES)
