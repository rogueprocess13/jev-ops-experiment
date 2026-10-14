"""Tier 3 command line: list, health, reset-faults, run, batch, scorecard,
export-lfedge, export-reasoning."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tier3 import testbed
from tier3.scenarios import ScenarioError, format_list, get_scenario, load_all
from tier3.vocab import FAULT_TYPES

DEFAULT_RESULTS = Path("results") / "tier3"


def _clients():
    from tier2.collectors.jaeger import Jaeger
    from tier2.collectors.opensearch import OpenSearch
    from tier2.collectors.prometheus import Prometheus
    from tier2.workload import Workload
    from tier3.collectors.kube import Kube
    from tier3.faults import FaultInjector

    kube = Kube.from_kubeconfig(testbed.kubeconfig(), testbed.namespace())
    return dict(kube=kube, injector=FaultInjector(kube), prom=Prometheus(testbed.prometheus_url()),
                jaeger=Jaeger(testbed.jaeger_url()), logs=OpenSearch(testbed.opensearch_url()),
                workload=Workload(testbed.base_url()))


def build_deps():
    from tier3.collect import collect, kube_state
    from tier3.deadman import Deadman
    from tier3.jev_adapter import ConfigError, JevAdapter
    from tier3.runner import Deps

    try:
        engine = JevAdapter()
    except ConfigError as e:
        raise SystemExit(f"error: {e}")
    c = _clients()

    def health():
        failed = [x for x in testbed.run_checks(c["kube"], c["prom"], c["jaeger"], c["workload"],
                                                c["injector"]) if not x.ok]
        if failed:
            raise RuntimeError("testbed unhealthy: " + "; ".join(f"{x.name} ({x.detail})" for x in failed))

    return Deps(engine=engine, injector=c["injector"], workload=c["workload"], health=health,
                stats=c["prom"].service_stats,
                kube_state=lambda start_s=None, end_s=None: kube_state(c["kube"], start_s, end_s),
                collect=lambda **kw: collect(c["prom"], c["jaeger"], c["logs"], c["kube"], **kw),
                deadman=Deadman())


def make_config(mode: str):
    from tier2.testbed import git_commit
    from tier3.runner import Config
    return Config(mode=mode, baseline_wait_s=180, recover_wait_s=60,
                  scrub_terms=("flagd", *FAULT_TYPES),
                  versions=testbed.versions(), git_commit=git_commit())


def print_record(rec: dict) -> None:
    print(f"{rec['experiment_id']}  status={rec['status']}  {rec.get('message', '')}".rstrip())
    for dim, v in rec["evaluation"].items():
        print(f"  {dim:<13} {v}")
    t, u = rec["timing"], rec["usage"]
    print(f"  polls         {len(rec['polls'])} (scored: {rec.get('scored_poll', 'n/a')}), "
          f"engine calls {u['engine_calls']}")
    print(f"  timing        mttd={t['mttd_seconds']} manifest={t['t_manifest']} total={t['total_seconds']}")
    if rec.get("false_positive"):
        fp = rec["false_positive"]
        print(f"  false alarms  {fp['false_positive_polls']}/{fp['answered_polls']} polls")


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text)
        print(f"wrote {out}")
    else:
        sys.stdout.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tier3", description="Tier 3: Kubernetes faults on kind")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list experiment IDs")
    sub.add_parser("health", help="check the cluster and the demo")
    sub.add_parser("reset-faults", help="restore from the fault ledger, remove every jev-fault object")
    r = sub.add_parser("run", help="run one experiment")
    r.add_argument("experiment_id")
    b = sub.add_parser("batch", help="run several experiments (default: the whole catalogue)")
    b.add_argument("experiment_ids", nargs="*")
    b.add_argument("--repeats", type=int, default=1)
    for p in (r, b):
        p.add_argument("--mode", choices=("poll", "single"), default="poll")
        p.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    for name, hlp in (("scorecard", "print the scorecard for a results directory"),
                      ("export-lfedge", "write JSONL in the LF Edge harness's field names"),
                      ("export-reasoning", "write a Markdown sheet for hand scoring")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("results")
        if name != "scorecard":
            p.add_argument("-o", "--output")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        print(format_list())
        return 0
    if args.cmd in ("scorecard", "export-lfedge", "export-reasoning"):
        from tier3.report import export_lfedge, export_reasoning, format_scorecard, load_records
        recs = load_records(args.results)
        if args.cmd == "scorecard":
            print(format_scorecard(recs))
        elif args.cmd == "export-lfedge":
            _write("".join(json.dumps(x) + "\n" for x in export_lfedge(recs)), args.output)
        else:
            _write(export_reasoning(recs), args.output)
        return 0
    if args.cmd == "health":
        c = _clients()
        checks = testbed.run_checks(c["kube"], c["prom"], c["jaeger"], c["workload"], c["injector"])
        for x in checks:
            print(f"{'ok  ' if x.ok else 'FAIL'} {x.name:<12} {x.detail}")
        return 0 if all(x.ok for x in checks) else 1
    if args.cmd == "reset-faults":
        from tier3.collectors.kube import Kube
        from tier3.faults import reset_faults
        changed = reset_faults(Kube.from_kubeconfig(testbed.kubeconfig(), testbed.namespace()))
        print("reset: " + ("; ".join(changed) if changed else "nothing to change"))
        return 0

    from tier3.runner import new_run_id, run_batch, run_experiment
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
    deps, cfg = build_deps(), make_config(args.mode)
    if args.cmd == "run":
        rec = run_experiment(scns[0], deps, cfg, new_run_id(), Path(args.results_dir))
        print_record(rec)
        print(f"result: {Path(args.results_dir) / rec['run_id']}")
        return 0 if rec["status"] == "ok" else 1
    summary = run_batch(scns, deps, cfg, Path(args.results_dir), repeats=args.repeats)
    from tier3.report import format_scorecard, load_records
    print(format_scorecard(load_records(Path(args.results_dir) / summary["run_id"])))
    if summary["stopped_early"]:
        print(f"stopped early: {summary['stopped_early']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
