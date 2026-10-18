"""Tier 3's question set and answer wording, shared by every engine.

No engine-specific code here: the Jev adapter and the Claude baseline both ask exactly
these four questions with these options.
"""
from __future__ import annotations

from tier3.vocab import ACTIONS, COMPONENTS, DIAGNOSES, NO_COMPONENT, NODES

_DIAGNOSIS_TEXT = {
    "none": "Nothing is wrong.",
    "service_unavailable": "A service has no running instances or cannot serve at all.",
    "pod_restart": "A service's instances were restarted or replaced.",
    "oom_killed": "Instances are killed for running out of memory.",
    "network_blocked": "Network traffic to or from a service is blocked.",
    "readiness_failure": "Instances run but are not ready to receive traffic.",
    "misconfiguration": "A service is running with wrong configuration.",
    "node_eviction": "Workloads were evicted from a node.",
    "disk_full": "A disk or filesystem is full.",
    "overload": "A service receives more load than it can handle.",
    "application_failure": "The service itself is returning errors.",
    "unknown": "The evidence is too weak or conflicting to name a failure mode.",
}
_ACTION_TEXT = {
    "no_action": "Take no action. Keep watching.",
    "investigate": "Look into the cause before changing anything.",
    "restart_service": "Restart the affected service.",
    "scale_up": "Add capacity or restore the replica count of the affected service.",
    "rollback_change": "Roll back a recent change or configuration.",
    "escalate": "Hand the incident to a human on-call engineer immediately.",
}
assert tuple(_DIAGNOSIS_TEXT) == DIAGNOSES and tuple(_ACTION_TEXT) == ACTIONS


def _component_text(c: str) -> str:
    return f"The problem originates in node {c}." if c in NODES else f"The problem originates in {c}."


QUESTIONS = {
    "incident_detected": {
        "type": "noul",
        "instructions": "Is there an operational incident in this application or cluster right now?",
        "criteria": {
            "true": "Yes, something is failing or clearly degraded compared with the baseline.",
            "false": "No, the application and cluster are operating normally.",
        },
    },
    "affected_component": {
        "type": "choice",
        "instructions": "Which single service or node is the origin of the problem?",
        "criteria": {NO_COMPONENT: "Nothing is affected.",
                     **{c: _component_text(c) for c in COMPONENTS}},
    },
    "diagnosis": {
        "type": "choice",
        "instructions": "What is the most likely failure mode?",
        "criteria": dict(_DIAGNOSIS_TEXT),
    },
    "recommended_action": {
        "type": "choice",
        "instructions": "What single operational action should be taken now?",
        "criteria": dict(_ACTION_TEXT),
    },
}
