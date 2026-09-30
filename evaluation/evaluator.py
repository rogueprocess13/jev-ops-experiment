"""Compare decisions to expected outcomes and aggregate results.

Pure functions over plain data. Every figure is computed from the records.
"""
from __future__ import annotations

from statistics import mean

FIELDS = ("severity", "action", "human_review")  # the operational decision: PASS needs all three
DIAGNOSIS_FIELDS = ("probable_cause",)  # scored, but not part of PASS/FAIL
ALL_FIELDS = FIELDS + DIAGNOSIS_FIELDS


def compare(expected, decision) -> dict:
    """Per-field correctness plus overall. Invalid and error decisions are all wrong."""
    exp = expected.to_dict() if hasattr(expected, "to_dict") else dict(expected)
    dec = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    ok = dec.get("status") == "ok"
    match = {f: bool(ok and exp.get(f) is not None and dec.get(f) == exp[f]) for f in ALL_FIELDS}
    match["overall"] = all(match[f] for f in FIELDS)
    return match


def make_record(run: int, scenario: str, seed: int, observations: dict, expected, decision) -> dict:
    dec = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    exp = expected.to_dict() if hasattr(expected, "to_dict") else dict(expected)
    return {
        "run": run,
        "scenario": scenario,
        "seed": seed,
        "observations": observations,
        "expected": exp,
        "decision": dec,
        "status": dec.get("status"),
        "match": compare(exp, dec),
    }


def _mean(xs):
    xs = list(xs)
    return mean(xs) if xs else None


def _pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def aggregate(records: list[dict]) -> dict:
    """Errored runs are excluded from accuracy; invalid runs count as incorrect."""
    errored = [r for r in records if r["status"] == "error"]
    scored = [r for r in records if r["status"] != "error"]
    invalid = [r for r in scored if r["status"] == "invalid"]
    correct = [r for r in scored if r["match"]["overall"]]

    by_field = {}
    for f in ALL_FIELDS:
        c = sum(1 for r in scored if r["match"].get(f))
        by_field[f] = {"correct": c, "total": len(scored)}

    by_scenario: dict[str, dict] = {}
    for r in records:
        s = by_scenario.setdefault(r["scenario"], {"correct": 0, "total": 0, "errored": 0})
        if r["status"] == "error":
            s["errored"] += 1
        else:
            s["total"] += 1
            s["correct"] += int(r["match"]["overall"])

    def conf(rs):
        return [r["decision"]["confidence"] for r in rs
                if r["status"] == "ok" and r["decision"].get("confidence") is not None]

    latencies = [r["decision"]["latency_ms"] for r in scored
                 if r["decision"].get("latency_ms") is not None]

    return {
        "runs": len(records),
        "scored": len(scored),
        "correct": len(correct),
        "incorrect": len(scored) - len(correct),
        "invalid": len(invalid),
        "errored": len(errored),
        "accuracy": len(correct) / len(scored) if scored else None,
        "by_field": by_field,
        "by_scenario": by_scenario,
        "confidence": {
            "mean": _mean(conf(scored)),
            "mean_correct": _mean(conf(correct)),
            "mean_incorrect": _mean(conf([r for r in scored if not r["match"]["overall"]])),
        },
        "latency_ms": {
            "mean": _mean(latencies),
            "p50": _pct(latencies, 0.5),
            "p95": _pct(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
    }


def _fmt(x, spec=".2f", suffix=""):
    return "n/a" if x is None else f"{x:{spec}}{suffix}"


def format_summary(s: dict) -> str:
    lines = ["Overall", "-------",
             f"Runs:          {s['runs']}",
             f"Correct:       {s['correct']}",
             f"Incorrect:     {s['incorrect']}"]
    if s["invalid"]:
        lines.append(f"  of which invalid replies: {s['invalid']}")
    if s["errored"]:
        lines.append(f"Errored:       {s['errored']} (excluded from accuracy)")
    lines.append(f"Accuracy:      {_fmt(s['accuracy'] * 100 if s['accuracy'] is not None else None, '.1f', '%')}")

    lines += ["", "By decision type", "----------------"]
    for f, v in s["by_field"].items():
        note = "  (diagnosis, not in PASS/FAIL)" if f in DIAGNOSIS_FIELDS else ""
        lines.append(f"{f:<15} {v['correct']}/{v['total']}{note}")

    lines += ["", "By scenario", "-----------"]
    for name, v in s["by_scenario"].items():
        extra = f"  ({v['errored']} errored)" if v["errored"] else ""
        lines.append(f"{name:<14} {v['correct']}/{v['total']}{extra}")

    c, lat = s["confidence"], s["latency_ms"]
    lines += ["", "Confidence (mean of severity and action confidence)", "----------",
              f"All:           {_fmt(c['mean'])}",
              f"Correct:       {_fmt(c['mean_correct'])}",
              f"Incorrect:     {_fmt(c['mean_incorrect'])}",
              "", "Latency", "-------",
              f"Mean:          {_fmt(lat['mean'], '.0f', ' ms')}",
              f"p50 / p95:     {_fmt(lat['p50'], '.0f')} / {_fmt(lat['p95'], '.0f', ' ms')}",
              f"Max:           {_fmt(lat['max'], '.0f', ' ms')}"]
    return "\n".join(lines)
