"""Tests the adapter's parsing/validation/retry with canned responses. Says nothing about Jev's real answers."""
import json

import pytest
import requests

from jev import client as jc
from jev.client import ConfigError, JevClient, JevConfig, parse_response


def body(sev="high", act="investigate", hr=0.2, conf=(0.8, 0.6)):
    return {"model": "jev-x", "answers": {
        "severity": {"type": "choice", "choice": sev, "probabilities": {sev: 1.0}, "confidence": conf[0]},
        "action": {"type": "choice", "choice": act, "probabilities": {act: 1.0}, "confidence": conf[1]},
        "human_review": {"type": "noul", "noul": hr}}}


class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def make(responses, retries=2):
    seq = list(responses)
    calls = []

    def post(url, headers, payload, timeout):
        calls.append((headers, payload))
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    cfg = JevConfig(api_key="SECRET-KEY", max_retries=retries)
    return JevClient(cfg, post=post, sleep=lambda s: None), calls


def test_parse_valid():
    d = parse_response(body())
    assert (d.status, d.severity, d.action, d.human_review) == ("ok", "high", "investigate", "no")
    assert d.confidence == pytest.approx(0.7)
    assert d.human_review_probability == 0.2 and d.model_version == "jev-x"


def test_human_review_threshold():
    assert parse_response(body(hr=0.5)).human_review == "yes"
    assert parse_response(body(hr=0.49)).human_review == "no"


def test_out_of_set_choice_is_invalid_not_coerced():
    d = parse_response(body(sev="catastrophic"))
    assert d.status == "invalid" and d.severity is None


def test_missing_fields_invalid():
    b = body()
    del b["answers"]["action"]
    assert parse_response(b).status == "invalid"
    assert parse_response({"nope": 1}).status == "invalid"
    assert parse_response(body(hr=1.5)).status == "invalid"


def test_confidence_absent_gives_none():
    b = body()
    del b["answers"]["severity"]["confidence"]
    del b["answers"]["action"]["confidence"]
    assert parse_response(b).confidence is None


def test_decide_records_latency_and_no_secret():
    c, calls = make([Resp(200, body())])
    d = c.decide({"cpu_pct": 1})
    assert d.status == "ok" and d.latency_ms is not None and d.latency_ms >= 0
    assert "SECRET-KEY" not in json.dumps(d.to_dict())
    assert calls[0][0]["Authorization"] == "Bearer SECRET-KEY"
    assert set(calls[0][1]["questions"]) == {"severity", "action", "human_review"}


def test_request_does_not_contain_scenario_or_expected():
    c, calls = make([Resp(200, body())])
    c.decide({"cpu_pct": 1})
    text = json.dumps(calls[0][1]).lower()
    assert "expected" not in text and "scenario" not in text


def test_retries_then_succeeds():
    c, calls = make([Resp(429), Resp(529), Resp(200, body())])
    assert c.decide({}).status == "ok" and len(calls) == 3


def test_persistent_failure_is_error_result_not_exception():
    c, calls = make([requests.ConnectionError("x")] * 3)
    d = c.decide({})
    assert d.status == "error" and len(calls) == 3


def test_auth_error_not_retried():
    c, calls = make([Resp(401, text="bad key")])
    assert c.decide({}).status == "error" and len(calls) == 1


def test_non_json_is_invalid():
    c, _ = make([Resp(200, None)])
    assert c.decide({}).status == "invalid"


def test_missing_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    with pytest.raises(ConfigError, match="JEV_API_KEY"):
        jc.load_config()
