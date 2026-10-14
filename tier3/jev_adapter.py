"""Jev adapter for Tier 3. The only Tier 3 module that imports jev.client."""
from __future__ import annotations

from jev.client import ConfigError  # re-exported so callers need not import jev.client  # noqa: F401
from tier3.engine import STATUS_INVALID, STATUS_OK, Decision
from tier3.vocab import ACTIONS, COMPONENTS, DIAGNOSES, NO_COMPONENT, NODES

INCIDENT_THRESHOLD = 0.5

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


def parse_answers(body: object) -> Decision:
    """Strict parse of a Jev reply to QUESTIONS. Out-of-set answers are 'invalid'."""

    def bad(msg: str) -> Decision:
        return Decision(status=STATUS_INVALID, raw_response=body, message=msg)

    if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
        return bad("response has no 'answers' object")
    a = body["answers"]
    out = Decision(status=STATUS_OK, raw_response=body)

    inc = a.get("incident_detected")
    p = inc.get("noul") if isinstance(inc, dict) else None
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
        return bad(f"incident_detected: missing or out-of-range probability ({inc!r})")
    out.incident_detected = p >= INCIDENT_THRESHOLD

    confs = []
    allowed = {"affected_component": (NO_COMPONENT, *COMPONENTS), "diagnosis": DIAGNOSES,
               "recommended_action": ACTIONS}
    for qid, vals in allowed.items():
        ans = a.get(qid)
        if not isinstance(ans, dict) or ans.get("choice") not in vals:
            return bad(f"{qid}: missing or out-of-set choice ({ans!r})")
        setattr(out, qid, ans["choice"])
        c = ans.get("confidence")
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            confs.append(float(c))
    out.confidence = sum(confs) / len(confs) if confs else None
    r = body.get("reasoning")
    out.reasoning = r if isinstance(r, str) else None
    return out


class JevAdapter:
    """AIOpsEngine backed by JevClient. All Jev-specific handling stays here."""

    def __init__(self, client=None):
        if client is None:
            from jev.client import JevClient
            client = JevClient()
        self.client = client

    def build_request(self, observation: dict) -> dict:
        return self.client.build_request(observation, questions=QUESTIONS,
                                         state_key="observations")

    def decide(self, observation: dict) -> Decision:
        from jev.client import STATUS_OK as JEV_OK, apply_usage, Decision as JevDecision

        reply = self.client.send(self.build_request(observation))
        if reply.status == JEV_OK:
            d = parse_answers(reply.body)
            tele = JevDecision(status="ok")
            apply_usage(tele, reply.body, self.client.config)
            d.telemetry.update(input_tokens=tele.input_tokens, output_tokens=tele.output_tokens,
                               cost_usd=tele.cost_usd, cost_source=tele.cost_source,
                               server_elapsed_ms=tele.server_elapsed_ms, usage=tele.usage,
                               model=(reply.body or {}).get("model") if isinstance(reply.body, dict) else None)
        else:
            d = Decision(status=reply.status, message=reply.message)
        d.telemetry.update(latency_ms=reply.latency_ms, total_ms=reply.total_ms,
                           attempts=reply.attempts, http_status=reply.http_status,
                           request_bytes=reply.request_bytes, response_bytes=reply.response_bytes)
        return d
