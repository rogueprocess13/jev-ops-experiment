"""Jev adapter. The only module that knows about Jev's HTTP API.

API details are in docs/jev-api-notes.md (source: https://thejevai.com/docs).
One request per decision, three typed questions:
  severity      -> choice
  action        -> choice
  human_review  -> noul (probability of "yes"; yes if >= HUMAN_REVIEW_THRESHOLD)
  probable_cause -> choice (diagnosis; scored separately from the decision)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

from scenarios.definitions import ACTIONS, CAUSES, HUMAN_REVIEW, SEVERITIES

DEFAULT_URL = "https://thejevai.com/v1/systemone"
DEFAULT_MODEL = "jev-latest"
HUMAN_REVIEW_THRESHOLD = 0.5
RETRY_STATUSES = {429, 500, 502, 503, 504, 529}

STATUS_OK = "ok"
STATUS_INVALID = "invalid"
STATUS_ERROR = "error"

QUESTIONS = {
    "severity": {
        "type": "choice",
        "instructions": "How severe is the current condition of this server?",
        "criteria": {
            "normal": "Operating normally. No sign of a problem.",
            "degraded": "Minor or uncertain signs of trouble. Service still works.",
            "high": "Clear service impairment. Users are likely affected.",
            "critical": "Severe failure or imminent failure. Service is down or close to it.",
        },
    },
    "action": {
        "type": "choice",
        "instructions": "What single operational action should be taken now?",
        "criteria": {
            "observe": "Take no action. Keep watching.",
            "investigate": "Look into the cause before changing anything.",
            "restart": "Restart the affected service.",
            "escalate": "Hand the incident to a human on-call engineer immediately.",
        },
    },
    "probable_cause": {
        "type": "choice",
        "instructions": "What is the most likely cause of the current condition?",
        "criteria": {
            "none": "Nothing is wrong.",
            "resource_exhaustion": "CPU, memory, disk or capacity is running out.",
            "dependency_failure": "A service this one depends on is failing or unreachable.",
            "application_bug": "A defect in the application code.",
            "configuration": "A wrong or changed configuration setting.",
            "network": "Network connectivity or packet loss.",
            "unknown": "The evidence is too weak or conflicting to name a cause.",
        },
    },
    "human_review": {
        "type": "noul",
        "instructions": "Should a human review this situation before any action is taken?",
        "criteria": {
            "true": "A human should review it.",
            "false": "No human review is needed.",
        },
    },
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class JevConfig:
    api_key: str = field(repr=False)
    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = 30.0
    max_retries: int = 3


def load_config() -> JevConfig:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # dotenv is optional at runtime
        pass
    key = os.environ.get("JEV_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "JEV_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return JevConfig(
        api_key=key,
        url=os.environ.get("JEV_API_URL", DEFAULT_URL),
        model=os.environ.get("JEV_MODEL", DEFAULT_MODEL),
        timeout_s=float(os.environ.get("JEV_TIMEOUT_S", "30")),
        max_retries=int(os.environ.get("JEV_MAX_RETRIES", "3")),
    )


@dataclass
class Decision:
    status: str  # ok | invalid | error
    severity: str | None = None
    action: str | None = None
    human_review: str | None = None
    probable_cause: str | None = None
    confidence: float | None = None  # mean of severity and action confidence
    field_confidence: dict = field(default_factory=dict)
    human_review_probability: float | None = None
    probabilities: dict = field(default_factory=dict)
    latency_ms: float | None = None
    model_version: str | None = None
    raw_response: dict | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def parse_response(body: dict) -> Decision:
    """Validate a Jev response strictly. Anything unexpected is 'invalid'."""

    def bad(msg: str) -> Decision:
        return Decision(status=STATUS_INVALID, raw_response=body, message=msg,
                        model_version=body.get("model") if isinstance(body, dict) else None)

    if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
        return bad("response has no 'answers' object")
    answers = body["answers"]
    out = Decision(status=STATUS_OK, raw_response=body, model_version=body.get("model"))

    for qid, allowed in (("severity", SEVERITIES), ("action", ACTIONS), ("probable_cause", CAUSES)):
        a = answers.get(qid)
        if not isinstance(a, dict) or a.get("choice") not in allowed:
            return bad(f"{qid}: missing or out-of-set choice ({a!r})")
        setattr(out, qid, a["choice"])
        out.field_confidence[qid] = _num(a.get("confidence"))
        if isinstance(a.get("probabilities"), dict):
            out.probabilities[qid] = a["probabilities"]

    hr = answers.get("human_review")
    p = _num(hr.get("noul")) if isinstance(hr, dict) else None
    if p is None or not 0.0 <= p <= 1.0:
        return bad(f"human_review: missing or out-of-range probability ({hr!r})")
    out.human_review_probability = p
    out.human_review = HUMAN_REVIEW[0] if p >= HUMAN_REVIEW_THRESHOLD else HUMAN_REVIEW[1]

    # Overall confidence is for the operational decision only (severity, action).
    confs = [out.field_confidence[q] for q in ("severity", "action")
             if out.field_confidence.get(q) is not None]
    out.confidence = sum(confs) / len(confs) if confs else None
    return out


PostFn = Callable[[str, dict, dict, float], "requests.Response"]


def _default_post(url, headers, payload, timeout):
    return requests.post(url, headers=headers, json=payload, timeout=timeout)


class JevClient:
    def __init__(self, config: JevConfig | None = None, post: PostFn = _default_post,
                 sleep: Callable[[float], None] = time.sleep):
        self.config = config or load_config()
        self._post = post
        self._sleep = sleep

    def build_request(self, observations: dict) -> dict:
        return {
            "state": {"server_observations": observations},
            "model": self.config.model,
            "questions": QUESTIONS,
        }

    def decide(self, observations: dict) -> Decision:
        cfg = self.config
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        payload = self.build_request(observations)
        last = "no attempt made"
        for attempt in range(cfg.max_retries + 1):
            if attempt:
                self._sleep(min(2 ** (attempt - 1), 30))
            t0 = time.perf_counter()
            try:
                resp = self._post(cfg.url, headers, payload, cfg.timeout_s)
            except requests.RequestException as e:
                last = f"{type(e).__name__}"
                continue
            latency = (time.perf_counter() - t0) * 1000
            if resp.status_code in RETRY_STATUSES:
                last = f"HTTP {resp.status_code}"
                continue
            if resp.status_code != 200:
                return Decision(status=STATUS_ERROR, latency_ms=latency,
                                message=f"HTTP {resp.status_code}: {resp.text[:200]}")
            try:
                body = resp.json()
            except ValueError:
                return Decision(status=STATUS_INVALID, latency_ms=latency,
                                message="response body is not JSON")
            d = parse_response(body)
            d.latency_ms = latency
            return d
        return Decision(status=STATUS_ERROR, message=f"gave up after retries: {last}")
