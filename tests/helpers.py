

from jev.client import Decision


def ok_decision(severity="normal", action="observe", human_review="no", confidence=0.9, latency=100.0,
                probable_cause="none"):
    return Decision(status="ok", severity=severity, action=action, human_review=human_review,
                    probable_cause=probable_cause,
                    confidence=confidence, human_review_probability=0.2 if human_review == "no" else 0.8,
                    latency_ms=latency, model_version="fake-1")


class FakeClient:
    """Returns scripted decisions in order (last one repeats). Never touches the network."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def decide(self, observations):
        self.calls.append(observations)
        i = min(len(self.calls) - 1, len(self.decisions) - 1)
        return self.decisions[i]
