from statistics import mean

from generator.server_state import generate
from scenarios.definitions import scenario_names

import json
import random

SEEDS = range(200)


def test_all_fields_present_and_in_range():
    for name in scenario_names():
        for seed in range(50):
            d = generate(name, seed).to_dict()
            for f in ("cpu_pct", "memory_pct", "disk_pct"):
                assert 0 <= d[f] <= 100
            assert d["load_1m"] >= 0
            assert d["network_errors_per_min"] >= 0
            assert 0 <= d["app_error_rate_pct"] <= 100
            assert d["api_latency_ms"] > 0
            assert set(d["services"].values()) <= {"healthy", "degraded", "down"}
            assert d["restarts_last_hour"] >= 0
            assert isinstance(d["recent_events"], list)


def test_same_seed_same_output():
    for name in scenario_names():
        assert generate(name, 42) == generate(name, 42)


def test_different_seed_differs():
    assert generate("degraded", 1) != generate("degraded", 2)


def test_global_rng_untouched():
    random.seed(7)
    expected_next = random.random()
    random.seed(7)
    generate("critical", 1)
    assert random.random() == expected_next


def test_json_round_trip():
    d = generate("ambiguous", 3).to_dict()
    assert json.loads(json.dumps(d)) == d


def _means(name, field):
    return mean(generate(name, s).to_dict()[field] for s in SEEDS)


def test_severity_ordering_of_means():
    for f in ("cpu_pct", "app_error_rate_pct", "api_latency_ms"):
        assert _means("healthy", f) < _means("degraded", f) < _means("critical", f)


def test_healthy_is_healthy():
    for s in SEEDS:
        d = generate("healthy", s)
        assert set(d.services.values()) == {"healthy"}
        assert d.cpu_pct < 40 and d.app_error_rate_pct < 1


def test_critical_has_a_down_service():
    for s in SEEDS:
        assert "down" in generate("critical", s).services.values()


def test_contradictory_signals_conflict():
    seen = set()
    for s in SEEDS:
        d = generate("contradictory", s)
        quiet_but_failing = d.cpu_pct < 40 and (d.app_error_rate_pct > 5 or "down" in d.services.values())
        busy_but_clean = d.cpu_pct > 80 and d.app_error_rate_pct < 1 and set(d.services.values()) == {"healthy"}
        assert quiet_but_failing or busy_but_clean
        seen.add("q" if quiet_but_failing else "b")
    assert seen == {"q", "b"}  # both variants occur
