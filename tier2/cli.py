"""Tier 2 command line: list, health, reset-faults, run, run-all."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tier2 import testbed
from tier2.scenarios import ScenarioError, format_list, get_scenario, load_all

DEFAULT_RESULTS = Path("results") / "tier2"


def build_deps():
    from tier2.collect import collect
    from tier2.collectors.jaeger import Jaeger
    from tier2.collectors.opensearch import OpenSearch
    from tier2.collectors.prometheus import Prometheus
    from tier2.faults import FaultInjector, HttpFlagStore
    from tier2.jev_adapter import ConfigError, JevAdapter
    from tier2.runner import Deps
    from tier2.workload import Workload

    try:
        engine = JevAdapter()
    except ConfigError as e:
        raise SystemExit(f"error: {e}")
    store = HttpFlagStore(testbed.base_url())
    prom, jaeger = Prometheus(testbed.prometheus_url()), Jaeger(testbed.base_url())
    logs = OpenSearch(testbed.opensearch_url())
    workload = Workload(testbed.base_url())

    def health():
        failed = [c for c in testbed.run_checks(store, prom, jaeger, workload) if not c.ok]
        if failed:
            raise RuntimeError("testbed unhealthy: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))

    return Deps(engine=engine, injector=FaultInjector(store), workload=workload, health=health,
                stats=prom.service_stats,
                collect=lambda **kw: collect(prom, jaeger, logs, **kw))


def make_config():
    from tier2.runner import Config
    return Config(
        baseline_wait_s=180, recover_wait_s=120,
        scrub_terms=("flagd", *testbed.flag_names()),
        versions={"demo_tag": testbed.DEMO_TAG, "images": testbed.image_versions()},
        git_commit=testbed.git_commit())


def print_record(rec: dict) -> None:
    print(f"{rec['experiment_id']}  status={rec['status']}  {rec.get('message', '')}".rstrip())
    for dim, v in rec["evaluation"].items():
        print(f"  {dim:<13} {v}")
    t = rec["timing"]
    print(f"  timing        detection={t['detection_seconds']} diagnosis={t['diagnosis_seconds']} "
          f"total={t['total_seconds']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tier2", description="Tier 2: OpenTelemetry Demo experiments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list experiment IDs")
    sub.add_parser("health", help="check the testbed")
    sub.add_parser("reset-faults", help="turn every flag off")
    r = sub.add_parser("run", help="run one experiment")
    r.add_argument("experiment_id")
    a = sub.add_parser("run-all", help="run the whole catalogue")
    a.add_argument("--repeats", type=int, default=1)
    for p in (r, a):
        p.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    args = ap.parse_args(argv)

    if args.cmd == "list":
        print(format_list())
        return 0
    if args.cmd == "health":
        checks = testbed.run_checks()
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.name:<13} {c.detail}")
        return 0 if all(c.ok for c in checks) else 1
    if args.cmd == "reset-faults":
        from tier2.faults import HttpFlagStore, reset_faults
        changed = reset_faults(HttpFlagStore(testbed.base_url()))
        print("reset: " + (", ".join(changed) if changed else "nothing to change"))
        return 0

    from tier2.runner import new_run_id, run_batch, run_experiment
    try:
        scns = [get_scenario(args.experiment_id)] if args.cmd == "run" else list(load_all().values())
    except ScenarioError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    deps, cfg = build_deps(), make_config()
    if args.cmd == "run":
        rec = run_experiment(scns[0], deps, cfg, new_run_id(), Path(args.results_dir))
        print_record(rec)
        print(f"result: {Path(args.results_dir) / rec['run_id']}")
        return 0 if rec["status"] == "ok" else 1
    summary = run_batch(scns, deps, cfg, Path(args.results_dir), repeats=args.repeats)
    print(json.dumps(summary["aggregate"], indent=2))
    if summary["stopped_early"]:
        print(f"stopped early: {summary['stopped_early']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
