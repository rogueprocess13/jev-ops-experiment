#!/usr/bin/env python3
"""Turn a results JSONL file into a Markdown report.

    python report.py                 latest file in results/
    python report.py results/X.jsonl a specific file

Everything is computed from the records. Nothing is hard-coded.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from evaluation.evaluator import ALL_FIELDS, aggregate, format_summary


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest(results_dir: Path) -> Path:
    files = sorted(results_dir.glob("*runs*.jsonl"))
    if not files:
        raise SystemExit(f"no *runs.jsonl files in {results_dir}. Run run.py first.")
    return files[-1]


def choices(records: list[dict], field: str) -> str:
    c = Counter(r["decision"].get(field) or r["status"] for r in records)
    return ", ".join(f"{k} x{v}" for k, v in c.most_common())


def render(records: list[dict], source: str) -> str:
    s = aggregate(records)
    logs = "yes" if all(r.get("include_logs", True) for r in records) else "no (metrics only)"
    out = ["# Jev ops experiment report", "", f"Source: `{source}`", "",
           f"Application logs sent to Jev: {logs}", "",
           "```text", format_summary(s), "```", "",
           "## What Jev chose, by scenario", "",
           "Expected value first, then everything Jev returned for that scenario.", ""]
    for name in dict.fromkeys(r["scenario"] for r in records):
        rs = [r for r in records if r["scenario"] == name]
        exp = rs[0]["expected"]
        out += [f"### {name} ({len(rs)} runs)", "",
                "| Field | Expected | Jev returned |", "|---|---|---|"]
        out += [f"| {f} | {exp.get(f, 'n/a')} | {choices(rs, f)} |" for f in ALL_FIELDS]
        out.append("")

    bad = [r for r in records if r["status"] != "ok" or not r["match"]["overall"]]
    out += [f"## Misses ({len(bad)})", "", "A miss is a wrong operational decision. Cause is shown but does not decide PASS/FAIL.", ""]
    if bad:
        out += ["| Run | Scenario | Seed | Status | Severity (exp/got) | Action (exp/got) | Human (exp/got) | Cause (exp/got) | Conf |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in bad:
            d, e = r["decision"], r["expected"]
            conf = d.get("confidence")
            out.append(
                f"| {r['run']} | {r['scenario']} | {r['seed']} | {r['status']} | "
                f"{e['severity']}/{d.get('severity') or '-'} | {e['action']}/{d.get('action') or '-'} | "
                f"{e['human_review']}/{d.get('human_review') or '-'} | "
                f"{e.get('probable_cause', 'n/a')}/{d.get('probable_cause') or '-'} | "
                f"{'n/a' if conf is None else f'{conf:.2f}'} |")
        out += ["", "Replay one: `python run.py --scenario <scenario> --seed <seed>`"]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="results JSONL (default: latest in results/)")
    p.add_argument("--results-dir", default="results")
    a = p.parse_args(argv)
    path = Path(a.file) if a.file else latest(Path(a.results_dir))
    text = render(load(path), path.name)
    report = path.with_name(path.name.replace(".jsonl", "-report.md"))
    report.write_text(text)
    print(text)
    print(f"Report saved: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
