"""Tier 4 command line: list, reset-faults, run, batch, scorecard, export-lfedge.
The cluster, health check and scenarios are Tier 3's."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tier3 import testbed
from tier3.cli import _write, build_deps, make_config, print_record
from tier3.scenarios import ScenarioError, format_list, get_scenario, load_all
from tier4.runner import DEFAULT_RESULTS


def build_tier4_deps():
    from tier3.collectors.kube import Kube
    from tier4.executor import Executor, kubectl_undo
    from tier4.runner import Tier4Deps

    base = build_deps()
    kube = Kube.from_kubeconfig(testbed.kubeconfig(), testbed.namespace())
    undo = kubectl_undo(testbed.kubeconfig(), testbed.namespace())
    return Tier4Deps(base=base, executor=lambda: Executor(kube, undo=undo))


def print_remediation(rec: dict) -> None:
    rem = rec.get("remediation")
    if not rem:
        return
    a, t = rem["action"], rem["timing"]
    what = a.get("operation") or f"{a.get('action')} on {a.get('component')}: {a.get('not_executable')}"
    print(f"  action        {what}")
    print(f"  outcome       {rem['outcome']}  mttr={t['mttr_seconds']} verified={t['mttr_verified_seconds']} "
          f"self={t['self_recovery_seconds']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tier4", description="Tier 4: closed-loop remediation on kind")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list experiment IDs (Tier 3's catalogue)")
    sub.add_parser("reset-faults", help="undo a recorded action, then the fault; remove jev-fault objects")
    r = sub.add_parser("run", help="run one experiment")
    r.add_argument("experiment_id")
    b = sub.add_parser("batch", help="run several experiments (default: the whole catalogue)")
    b.add_argument("experiment_ids", nargs="*")
    b.add_argument("--repeats", type=int, default=1)
    for p in (r, b):
        p.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    for name, hlp in (("scorecard", "print the scorecard for a results directory"),
                      ("export-lfedge", "write JSONL in the LF Edge harness's field names")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("results")
        if name != "scorecard":
            p.add_argument("-o", "--output")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        print(format_list())
        return 0
    if args.cmd in ("scorecard", "export-lfedge"):
        from tier4.report import export_lfedge, format_scorecard, load_records
        recs = load_records(args.results)
        if args.cmd == "scorecard":
            print(format_scorecard(recs))
        else:
            _write("".join(json.dumps(x) + "\n" for x in export_lfedge(recs)), args.output)
        return 0
    if args.cmd == "reset-faults":
        from tier3.collectors.kube import Kube
        from tier3.faults import reset_faults
        changed = reset_faults(Kube.from_kubeconfig(testbed.kubeconfig(), testbed.namespace()))
        print("reset: " + ("; ".join(changed) if changed else "nothing to change"))
        return 0

    from tier4.runner import new_run_id, run_batch, run_experiment
    try:
        if args.cmd == "run":
            scns = [get_scenario(args.experiment_id)]
        elif args.experiment_ids:
            scns = [get_scenario(e) for e in args.experiment_ids]
        else:
            scns = list(load_all().values())
    except ScenarioError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    deps, cfg = build_tier4_deps(), make_config("poll")
    if args.cmd == "run":
        rec = run_experiment(scns[0], deps, cfg, new_run_id(), Path(args.results_dir))
        print_record(rec)
        print_remediation(rec)
        print(f"result: {Path(args.results_dir) / rec['run_id']}")
        return 0 if rec["status"] == "ok" else 1
    summary = run_batch(scns, deps, cfg, Path(args.results_dir), repeats=args.repeats)
    from tier4.report import format_scorecard, load_records
    print(format_scorecard(load_records(Path(args.results_dir) / summary["run_id"])), flush=True)
    if summary["stopped_early"]:
        print(f"stopped early: {summary['stopped_early']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
