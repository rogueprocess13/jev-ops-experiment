"""Service-level recovery after a remediation (design D5-D8). Harness-side only:
nothing here reaches the engine.

Unlike Tier 3's manifestation check, replaced pods and restart counts do not count:
a restart or rollback always replaces pods. Recovered means every Deployment is back
at its baseline availability with its rollout complete, every application pod is
Running and Ready, and no service deviates from its baseline (Tier 2 rules).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tier2.manifest import any_deviation
from tier2.observation import ServiceStats
from tier3.observation import KubeState

RECOVERED_BY_ACTION = "recovered_by_action"
RECOVERED_WITHOUT_ACTION = "recovered_without_action"
NOT_RECOVERED = "not_recovered"


@dataclass
class RecoveryConfig:
    check_s: float = 15.0
    hold_s: float = 30.0
    window_s: float = 300.0
    stats_window_s: int = 30  # service stats over the time since the last check


def problems(cur_stats: dict[str, ServiceStats], base_stats: dict[str, ServiceStats],
             cur: KubeState, base: KubeState) -> list[str]:
    """Empty when the system counts as recovered."""
    out = []
    for name, b in base.deployments.items():
        c = cur.deployments.get(name)
        if c is None:
            out.append(f"deployment {name} missing")
        elif c["available"] < b["available"]:
            out.append(f"deployment {name} {c['available']} available, baseline {b['available']}")
        elif c["rollout"] != "complete":
            out.append(f"deployment {name} rollout {c['rollout']}")
    for p in cur.pods:
        if p.get("deleting"):
            continue  # an old pod on its way out after a restart or rollback
        if not (p["phase"] == "Running" and p["ready"]):
            out.append(f"pod {p['name']} not ready")
    out += [f"service {s} deviates" for s in any_deviation(cur_stats, base_stats)]
    return out


def watch(start: float, stats: Callable[[float, int], dict], kube_state: Callable[[], KubeState],
          base_stats: dict, base_kube: KubeState, clock: Callable[[], float],
          sleep: Callable[[float], None], cfg: RecoveryConfig,
          prior: dict | None = None) -> dict:
    """Check every `check_s` from `start` until checks pass for `hold_s` in a row or
    `window_s` ends. Returns every check, `t_recovered` (first check of the passing run)
    and `t_recovery_verified` (the check that completed the hold), as epoch seconds.
    `prior` is a check taken before the action; if it passed, a passing run starts there,
    so a system that was already back counts as recovered without the action (D7)."""
    checks = [prior] if prior else []
    run_start = prior["t"] if prior and prior["ok"] else None
    from_prior = run_start is not None
    deadline = start + cfg.window_s
    wait = start - clock()
    if wait > 0:
        sleep(wait)
    while True:
        now = clock()
        c = check(stats, kube_state, base_stats, base_kube, now, cfg)
        checks.append(c)
        if not c["ok"]:
            run_start, from_prior = None, False
        else:
            run_start = now if run_start is None else run_start
            if now - run_start >= cfg.hold_s:
                return {"checks": checks, "t_recovered": run_start, "t_recovery_verified": now,
                        "before_action": from_prior}
        nxt = now + cfg.check_s
        if nxt > deadline:
            return {"checks": checks, "t_recovered": None, "t_recovery_verified": None,
                    "before_action": False}
        sleep(nxt - clock())


def check(stats: Callable[[float, int], dict], kube_state: Callable[[], KubeState],
          base_stats: dict, base_kube: KubeState, now: float, cfg: RecoveryConfig) -> dict:
    why = problems(stats(now, cfg.stats_window_s), base_stats, kube_state(), base_kube)
    return {"t": now, "ok": not why, "problems": why}


def outcome(executed: bool, recovered: bool, before_action: bool) -> str:
    """D7: recovered by the action only when an action ran and the passing run did not
    begin before it (at the check taken just before acting)."""
    if not recovered:
        return NOT_RECOVERED
    if executed and not before_action:
        return RECOVERED_BY_ACTION
    return RECOVERED_WITHOUT_ACTION


def disturbed(checks: list[dict]) -> bool:
    """D8: any failing check after an action on a false alarm."""
    return any(not c["ok"] for c in checks)
