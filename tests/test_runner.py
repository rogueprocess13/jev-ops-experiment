import json

import pytest
from tests.helpers import FakeClient, ok_decision

import run
from generator.server_state import generate
from jev.client import Decision
from scenarios.definitions import get_scenario, scenario_names


def perfect_client(n):
    return FakeClient([ok_decision(**get_scenario(s).expected.to_dict()) for s in scenario_names()] * n)


def test_plan_is_deterministic_and_balanced():
    a = run.plan_runs(None, 100, 1000)
    assert a == run.plan_runs(None, 100, 1000)
    counts = {n: sum(1 for s, _ in a if s == n) for n in scenario_names()}
    assert set(counts.values()) == {20}
    assert [seed for _, seed in a] == list(range(1000, 1100))


def test_named_and_random_plans():
    assert {s for s, _ in run.plan_runs("critical", 5, 1)} == {"critical"}
    assert run.plan_runs("random", 20, 5) == run.plan_runs("random", 20, 5)
    assert len(run.plan_runs(None, 1, 5)) == 1


def test_unknown_scenario_exits_nonzero():
    with pytest.raises(SystemExit) as e:
        run.parse_args(["--scenario", "bogus"])
    assert e.value.code != 0


def test_batch_writes_files_and_summary_matches(tmp_path):
    fake = perfect_client(1)
    lines = []
    records, summary = run.run_experiment(fake, None, 10, 7, tmp_path, out=lines.append)
    assert len(records) == 10 and len(fake.calls) == 10
    jsonl = next(tmp_path.glob("*.jsonl"))
    rows = [json.loads(x) for x in jsonl.read_text().splitlines()]
    assert len(rows) == 10
    saved = json.loads(next(tmp_path.glob("*-summary.json")).read_text())["summary"]
    assert saved == summary
    assert summary["runs"] == 10


def test_replay_from_batch_record(tmp_path):
    fake = perfect_client(1)
    records, _ = run.run_experiment(fake, None, 6, 50, tmp_path, out=lambda *_: None)
    r = records[3]
    assert generate(r["scenario"], r["seed"]).to_dict() == r["observations"]


def test_error_does_not_stop_batch(tmp_path):
    fake = FakeClient([Decision(status="error", message="boom"), ok_decision()])
    records, summary = run.run_experiment(fake, "healthy", 3, 1, tmp_path, out=lambda *_: None)
    assert len(records) == 3 and summary["errored"] == 1


def test_single_run_output_pass_and_fail(tmp_path):
    exp = get_scenario("degraded").expected.to_dict()
    lines = []
    run.run_experiment(FakeClient([ok_decision(**exp)]), "degraded", 1, 1234, tmp_path, out=lines.append)
    text = "\n".join(lines)
    assert "Scenario: degraded" in text and "Seed: 1234" in text and "Result: PASS" in text

    lines.clear()
    run.run_experiment(FakeClient([ok_decision("normal", "observe", "no")]), "degraded", 1, 1234, tmp_path, out=lines.append)
    assert "Result: FAIL (severity, action)" in "\n".join(lines)


def test_errored_single_run_is_not_pass(tmp_path):
    lines = []
    run.run_experiment(FakeClient([Decision(status="error", message="down")]), "healthy", 1, 1, tmp_path, out=lines.append)
    text = "\n".join(lines)
    assert "PASS" not in text and "ERROR" in text


def test_main_missing_key_exits_before_any_request(monkeypatch, capsys):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    assert run.main(["--scenario", "healthy"]) == 2
    assert "JEV_API_KEY" in capsys.readouterr().err


def test_recommended_action_is_only_recorded(tmp_path):
    # Runner must never act on a 'restart' recommendation; it only stores it.
    recs, _ = run.run_experiment(FakeClient([ok_decision("critical", "restart", "yes")]), "critical", 1, 1, tmp_path, out=lambda *_: None)
    assert recs[0]["decision"]["action"] == "restart"
