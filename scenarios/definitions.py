"""Scenario catalogue and ground truth.

Expected outcomes are defined here by hand. They are never produced by Jev or
any other LLM, and they do not depend on the generated numbers or the seed.
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("normal", "degraded", "high", "critical")
ACTIONS = ("observe", "investigate", "restart", "escalate")
HUMAN_REVIEW = ("yes", "no")


@dataclass(frozen=True)
class Expected:
    severity: str
    action: str
    human_review: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity {self.severity!r}")
        if self.action not in ACTIONS:
            raise ValueError(f"bad action {self.action!r}")
        if self.human_review not in HUMAN_REVIEW:
            raise ValueError(f"bad human_review {self.human_review!r}")

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "action": self.action,
            "human_review": self.human_review,
        }


@dataclass(frozen=True)
class Profile:
    """How the generator builds one flavour of a scenario.

    Bands are (low, high) "stress" levels in 0..1. Resource metrics (CPU,
    memory, disk, load) follow resource_band; failure metrics (network errors,
    error rate, latency) follow failure_band. They are equal for ordinary
    scenarios and deliberately different for contradictory ones.
    """

    resource_band: tuple[float, float]
    failure_band: tuple[float, float]
    jitter: float = 0.0  # per-metric extra noise on the stress level
    services_down: tuple[int, int] = (0, 0)  # inclusive range
    services_degraded: tuple[int, int] = (0, 0)
    restarts: tuple[int, int] = (0, 0)  # restarts in the last hour
    events: tuple[str, ...] = ()  # pool of recent-event messages
    label: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    expected: Expected
    rationale: str
    profiles: tuple[Profile, ...]


SCENARIOS: dict[str, Scenario] = {
    "healthy": Scenario(
        name="healthy",
        description="Low resource use, no errors, all services up.",
        expected=Expected("normal", "observe", "no"),
        rationale="Every signal is in its normal range. Nothing needs doing.",
        profiles=(
            Profile(
                resource_band=(0.05, 0.25),
                failure_band=(0.0, 0.1),
                events=("scheduled backup completed", "log rotation completed"),
                label="quiet",
            ),
        ),
    ),
    "degraded": Scenario(
        name="degraded",
        description="High load and slow responses, one service degraded.",
        expected=Expected("high", "investigate", "no"),
        rationale=(
            "Several signals agree that service quality is falling, but nothing "
            "is down. Investigate the cause. A human does not need to be paged yet."
        ),
        profiles=(
            Profile(
                resource_band=(0.55, 0.72),
                failure_band=(0.5, 0.65),
                services_degraded=(1, 1),
                restarts=(0, 1),
                events=("worker queue depth rising", "slow query warning"),
                label="loaded",
            ),
        ),
    ),
    "critical": Scenario(
        name="critical",
        description="Resources near exhaustion, errors high, a service down.",
        expected=Expected("critical", "escalate", "yes"),
        rationale=(
            "A service is down, resources are close to exhaustion and errors are "
            "very high. A restart alone is unlikely to be safe or enough, so a "
            "human must take over."
        ),
        profiles=(
            Profile(
                resource_band=(0.88, 1.0),
                failure_band=(0.85, 1.0),
                services_down=(1, 1),
                services_degraded=(1, 1),
                restarts=(3, 8),
                events=("out of memory kill", "service crash loop detected"),
                label="failing",
            ),
        ),
    ),
    "ambiguous": Scenario(
        name="ambiguous",
        description="Middling, mixed signals. No service down, nothing clearly wrong.",
        expected=Expected("degraded", "investigate", "yes"),
        rationale=(
            "The evidence is weak and mixed, so it does not justify a restart or "
            "an escalation, but it is not clearly fine either. Investigate, and ask "
            "a human to look because the machine cannot be sure. This is a "
            "judgment call, not an objectively correct answer."
        ),
        profiles=(
            Profile(
                resource_band=(0.4, 0.6),
                failure_band=(0.25, 0.45),
                jitter=0.15,
                services_degraded=(0, 1),
                restarts=(0, 2),
                events=("deploy finished 2h ago", "cache hit rate dipped"),
                label="mixed",
            ),
        ),
    ),
    "contradictory": Scenario(
        name="contradictory",
        description="Signals that disagree: quiet hosts with failing service, or busy host with no symptoms.",
        expected=Expected("degraded", "investigate", "yes"),
        rationale=(
            "The data cannot all be true at once, or does not fit a known failure "
            "pattern. It is safest to investigate and get human review. Restart "
            "and escalate are not justified by contradictory evidence. This is a "
            "judgment call, not an objectively correct answer."
        ),
        profiles=(
            Profile(
                resource_band=(0.05, 0.2),
                failure_band=(0.8, 0.95),
                services_down=(1, 1),
                restarts=(0, 1),
                events=("health check failing", "no recent deploys"),
                label="quiet_but_failing",
            ),
            Profile(
                resource_band=(0.88, 0.97),
                failure_band=(0.0, 0.05),
                restarts=(0, 0),
                events=("no alerts firing",),
                label="busy_but_clean",
            ),
        ),
    ),
}

REQUIRED_SCENARIOS = ("healthy", "degraded", "critical", "ambiguous", "contradictory")


def scenario_names() -> list[str]:
    return list(SCENARIOS)


def get_scenario(name: str) -> Scenario:
    try:
        return SCENARIOS[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario {name!r}; valid names: {', '.join(SCENARIOS)}"
        ) from None
