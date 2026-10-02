"""Jev adapter for Tier 2. The only Tier 2 module that imports jev.client."""
from __future__ import annotations

from jev.client import ConfigError  # re-exported so callers need not import jev.client  # noqa: F401
from tier2.engine import STATUS_INVALID, STATUS_OK, Decision
from tier2.vocab import ACTIONS, DIAGNOSES, NO_SERVICE, SERVICES

INCIDENT_THRESHOLD = 0.5

QUESTIONS = {
    "incident_detected": {
        "type": "noul",
        "instructions": "Is there an operational incident in this application right now?",
        "criteria": {
            "true": "Yes, something is failing or clearly degraded compared with the baseline.",
            "false": "No, the application is operating normally.",
        },
    },
    "affected_service": {
        "type": "choice",
        "instructions": "Which single service or component is the origin of the problem?",
        "criteria": {
            NO_SERVICE: "No service is affected.",
            **{s: f"The problem originates in {s}." for s in SERVICES},
        },
    },
    "diagnosis": {
        "type": "choice",
        "instructions": "What is the most likely failure mode?",
        "criteria": {
            "none": "Nothing is wrong.",
            "application_failure": "The service itself is returning errors.",
            "latency_degradation": "Requests succeed but are much slower than normal.",
            "dependency_unreachable": "A service cannot reach something it depends on.",
            "database_contention": "A database or data store is slow or locked.",
            "resource_exhaustion": "CPU, memory or capacity is running out.",
            "unknown": "The evidence is too weak or conflicting to name a failure mode.",
        },
    },
    "recommended_action": {
        "type": "choice",
        "instructions": "What single operational action should be taken now?",
        "criteria": {
            "no_action": "Take no action. Keep watching.",
            "investigate": "Look into the cause before changing anything.",
            "restart_service": "Restart the affected service.",
            "rollback_change": "Roll back a recent change or configuration.",
            "scale_up": "Add capacity to the affected service.",
            "escalate": "Hand the incident to a human on-call engineer immediately.",
        },
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
    allowed = {"affected_service": (NO_SERVICE, *SERVICES), "diagnosis": DIAGNOSES,
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
                               server_elapsed_ms=tele.server_elapsed_ms, usage=tele.usage)
        else:
            d = Decision(status=reply.status, message=reply.message)
        d.telemetry.update(latency_ms=reply.latency_ms, total_ms=reply.total_ms,
                           attempts=reply.attempts, http_status=reply.http_status,
                           request_bytes=reply.request_bytes, response_bytes=reply.response_bytes)
        return d
