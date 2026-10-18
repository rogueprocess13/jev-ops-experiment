from tier2.observation import ServiceStats
from tier3.observation import KubeState
from tier4.recovery import (NOT_RECOVERED, RECOVERED_BY_ACTION, RECOVERED_WITHOUT_ACTION,
                            RecoveryConfig, outcome, problems, watch)

OK = {"frontend": ServiceStats(5.0, 0.0, 20, 250)}
BAD = {"frontend": ServiceStats(5.0, 0.3, 20, 300)}
DEP = {"cart": {"desired": 1, "available": 1, "rollout": "complete"}}


def ks(avail=1, rollout="complete", pods=None):
    return KubeState(deployments={"cart": {"desired": 1, "available": avail, "rollout": rollout}},
                     pods=pods if pods is not None else [{"name": "cart-a", "phase": "Running", "ready": True}])


BASE = ks()


def test_replaced_and_terminating_pods_pass():
    pods = [{"name": "cart-new", "phase": "Running", "ready": True, "restarts": 3},
            {"name": "cart-old", "phase": "Running", "ready": False, "deleting": True}]
    assert problems(OK, OK, ks(pods=pods), BASE) == []


def test_missing_telemetry_fails():
    assert problems({}, OK, ks(), BASE) == ["no service telemetry in the window"]


def test_errors_or_missing_replicas_fail():
    assert problems(BAD, OK, ks(), BASE) == ["service frontend deviates"]
    assert problems(OK, OK, ks(avail=0), BASE)
    assert problems(OK, OK, ks(rollout="progressing"), BASE)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0)


def run(seq, prior=None, start=0.0):
    """seq: per-check booleans in time order."""
    clock, i = Clock(), [0]

    def stats(at, w):
        ok = seq[min(i[0], len(seq) - 1)]
        i[0] += 1
        return OK if ok else BAD
    return watch(start, stats, lambda: BASE, OK, BASE, clock, clock.sleep, RecoveryConfig(), prior=prior)


def test_hold_of_60s_needed():
    w = run([False, True, True, True, True, True])
    assert w["t_recovered"] == 15.0 and w["t_recovery_verified"] == 75.0


def test_pass_then_fail_resets_the_run():
    w = run([True, False, True, True, True, True, True])
    assert w["t_recovered"] == 30.0


def test_window_ends():
    w = run([False])
    assert w["t_recovered"] is None and len(w["checks"]) == 25  # 0..360 s every 15 s


def test_prior_passing_check_counts_as_already_recovered():
    w = run([True] * 5, prior={"t": -5.0, "ok": True, "problems": []}, start=10.0)
    assert w["t_recovered"] == -5.0 and w["before_action"]
    assert outcome(True, True, w["before_action"]) == RECOVERED_WITHOUT_ACTION


def test_failing_check_after_prior_means_by_action():
    w = run([False] + [True] * 5, prior={"t": -5.0, "ok": True, "problems": []}, start=10.0)
    assert not w["before_action"] and outcome(True, True, w["before_action"]) == RECOVERED_BY_ACTION


def test_outcomes():
    assert outcome(True, True, False) == RECOVERED_BY_ACTION
    assert outcome(False, True, False) == RECOVERED_WITHOUT_ACTION
    assert outcome(True, False, False) == NOT_RECOVERED
